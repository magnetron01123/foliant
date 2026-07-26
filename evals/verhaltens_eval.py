"""Schicht-3-Verhaltens-Evals (BACKLOG.md §2) werkzeuggestuetzt: fuehrt die Checklisten-
Fragen gegen die ECHTE Claude-API mit den ECHTEN Foliant-Tools aus und bewertet die
Antworten deterministisch (Marker/Format) plus optional per LLM-Richter.

    ANTHROPIC_API_KEY=... python -m evals.verhaltens_eval [--modell ...] [--nur A1,B3]
                                                          [--richter an|aus]

Architektur-Entscheidungen:
- Tools IN-PROCESS ueber fastmcp.Client(app.server.mcp): nutzt die echten generierten
  Schemas/Docstrings (Kanal 2), ohne Port/Token. Bewusste Untreue ggu. dem echten
  HTTP-Connector (Netz/Serialisierung) - das prueft Schicht 2.
- API direkt per httpx (Muster app/charakterbogen/uebersetzer.py - das Projekt pinnt
  bewusst kein anthropic-SDK). Key NUR aus der Umgebung, nie geloggt.
- System-Prompt = der §8-Codeblock aus SPEC.md, mit demselben Extraktor wie
  tests/test_verhaltensregeln.py - eine Quelle, kein Duplikat.
- Report-Kopf = BACKLOG-§2-Pflichtfelder (Datum, Modell, Client, inhalts_hash) via
  admin.berechne_manifest. Ausgabe nach evals/ergebnisse/ (gitignored - die
  Vier-Dokumente-Regel gilt).

NICHT Teil von `make test` (kostet API-Tokens, ~15 Faelle x 3-5 Runden)."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from evals.faelle import FAELLE

_PROJEKT = Path(__file__).resolve().parents[1]
_ERGEBNISSE = Path(__file__).resolve().parent / "ergebnisse"
_API_URL = "https://api.anthropic.com/v1/messages"
_ANWEISUNG_RE = re.compile(r"```\n(Du hilfst unserer D&D-Runde.*?)```", re.S)
# Belegzeilen-Format aus stil.py: '📖 Quelle · S. X · Regelversion 2024' (Seite optional).
BELEG_RE = re.compile(r"📖 .+Regelversion \d{4}")
_MAX_RUNDEN = 8
_STANDARD_MODELL = "claude-sonnet-5"
_RICHTER_MODELL = "claude-haiku-4-5-20251001"


def projektanweisung() -> str:
    """Der §8-Codeblock aus SPEC.md - derselbe Extraktor wie test_verhaltensregeln.py."""
    bloecke = _ANWEISUNG_RE.findall((_PROJEKT / "SPEC.md").read_text(encoding="utf-8"))
    if len(bloecke) != 1:
        sys.exit("SPEC.md §8 muss genau EINEN Projektanweisungs-Block enthalten.")
    return bloecke[0]


def pruefe_deterministisch(fall: dict, text: str, tool_namen: list[str]) -> list[str]:
    """Harte Marker-/Format-Pruefungen; leere Liste = bestanden."""
    gruende = []
    for frag in fall.get("pflicht", []):
        if frag not in text:
            gruende.append(f"Pflicht-Fragment fehlt: {frag!r}")
    eine = fall.get("pflicht_eine")
    if eine and not any(f in text for f in eine):
        gruende.append(f"Keines der Pflicht-Alternativen vorhanden: {eine}")
    for frag in fall.get("verboten", []):
        if frag.lower() in text.lower():
            gruende.append(f"Verbotenes Fragment in der Antwort: {frag!r}")
    erwartet = fall.get("erwartete_tools")
    if erwartet and not set(erwartet) & set(tool_namen):
        gruende.append(f"Keines der erwarteten Tools aufgerufen: {erwartet} "
                       f"(aufgerufen: {tool_namen or 'keine'})")
    if "📖" in text and not BELEG_RE.search(text):
        gruende.append("Belegzeile ohne Format '📖 Quelle · … · Regelversion JJJJ'")
    if not text.strip():
        gruende.append("Leere Antwort (Runden-Cap erreicht oder Abbruch)")
    return gruende


def _api_aufruf(client: httpx.Client, key: str, body: dict) -> dict:
    """Ein Messages-Aufruf mit einfachem Retry (429/5xx); wirft bei hartem Fehler."""
    for versuch in range(3):
        antwort = client.post(_API_URL, json=body, headers={
            "x-api-key": key, "anthropic-version": "2023-06-01"})
        if antwort.status_code in (429, 500, 502, 503, 529) and versuch < 2:
            time.sleep(5 * (versuch + 1))
            continue
        antwort.raise_for_status()
        return antwort.json()
    raise RuntimeError("API-Retry erschoepft")


async def _fahre_fall(mcp_client, http, key: str, modell: str, system: str,
                      werkzeuge: list[dict], frage: str) -> tuple[str, list[str]]:
    """Tool-Use-Schleife fuer EINEN Fall: (finaler Text, aufgerufene Tool-Namen)."""
    messages: list[dict] = [{"role": "user", "content": frage}]
    tool_namen: list[str] = []
    bestandsauszuege: list[str] = []
    for _ in range(_MAX_RUNDEN):
        daten = _api_aufruf(http, key, {
            "model": modell, "max_tokens": 3000, "system": system,
            "messages": messages, "tools": werkzeuge})
        inhalt = daten.get("content", [])
        messages.append({"role": "assistant", "content": inhalt})
        if daten.get("stop_reason") != "tool_use":
            return ("".join(b.get("text", "") for b in inhalt
                            if b.get("type") == "text"), tool_namen, bestandsauszuege)
        ergebnisse = []
        for block in inhalt:
            if block.get("type") != "tool_use":
                continue
            tool_namen.append(block["name"])
            try:
                res = await mcp_client.call_tool(block["name"], block.get("input") or {})
                text_out = "\n".join(getattr(c, "text", "") or "" for c in res.content)
                fehler = False
            except Exception as ausnahme:
                # Ein fehlgeschlagener Tool-Aufruf (z. B. Schema-Verletzung) gehoert als
                # is_error-Ergebnis ZURUECK ans Modell - genau wie es ein echter
                # MCP-Client tut. Vorher riss die Ausnahme den ganzen Lauf ab und der
                # Report wurde nie geschrieben (Befund Erstlauf 26.07.2026).
                text_out, fehler = f"{type(ausnahme).__name__}: {ausnahme}", True
            ergebnisse.append({"type": "tool_result", "tool_use_id": block["id"],
                               "content": text_out[:20000], "is_error": fehler})
            if not fehler:
                bestandsauszuege.append(f"[{block['name']}]\n{text_out[:6000]}")
        messages.append({"role": "user", "content": ergebnisse})
    return ("", tool_namen, bestandsauszuege)


def _richter(http, key: str, richter_modell: str, rubrik: str, frage: str,
             text: str, bestandsauszuege: list[str]) -> dict:
    """LLM-Richter fuer weiche Kriterien - Urteil ist 'weich' gekennzeichnet.

    Der Richter bekommt die TOOL-AUSGABEN als einzige Sachgrundlage und wird
    ausdruecklich auf sie festgenagelt. Ohne das urteilte er aus D&D-Trainingswissen
    und produzierte genau die Halluzinationen, gegen die Foliant gebaut ist (Volllauf
    26.07.2026: erfand fehlende Solar-'Reaktionen' und nannte eine Seitenzahl
    'erfunden', die woertlich aus dem Bestand stammt)."""
    auszug = "\n\n".join(bestandsauszuege)[:24000] or "(keine Tool-Aufrufe)"
    prompt = (f"Du bewertest die Antwort eines D&D-Regelassistenten.\n\n"
              f"WICHTIG - Bewertungsgrundlage: AUSSCHLIESSLICH die unten stehenden "
              f"Bestandsauszuege (die echten Werkzeug-Ausgaben) und die Rubrik. Dein "
              f"eigenes D&D-Wissen ist KEINE Grundlage: Wenn du etwas vermisst, das in "
              f"den Auszuegen nicht vorkommt, ist das KEIN Fehler der Antwort - der "
              f"Bestand ist die Wahrheit, nicht die dir bekannte Regelfassung. "
              f"Seitenzahlen und Quellen gelten als korrekt, wenn sie so in den "
              f"Auszuegen stehen. Im Zweifel: bestanden.\n\n"
              f"FRAGE DES NUTZERS:\n{frage}\n\nANTWORT DES ASSISTENTEN:\n{text}\n\n"
              f"BESTANDSAUSZUEGE (Werkzeug-Ausgaben):\n{auszug}\n\n"
              f"BEWERTUNGSRUBRIK:\n{rubrik}\n\n"
              f"Antworte NUR mit JSON: {{\"bestanden\": true|false, "
              f"\"begruendung\": \"<ein Satz>\"}}")
    daten = _api_aufruf(http, key, {
        "model": richter_modell, "max_tokens": 300,
        "messages": [{"role": "user", "content": prompt}]})
    text_out = "".join(b.get("text", "") for b in daten.get("content", [])
                       if b.get("type") == "text")
    m = re.search(r"\{.*\}", text_out, re.S)
    if not m:
        return {"bestanden": False, "begruendung": "Richter lieferte kein JSON"}
    try:
        urteil = json.loads(m.group(0))
        return {"bestanden": bool(urteil.get("bestanden")),
                "begruendung": str(urteil.get("begruendung", ""))[:300]}
    except (json.JSONDecodeError, TypeError):
        return {"bestanden": False, "begruendung": "Richter-JSON unlesbar"}


def _manifest_kopf() -> dict:
    from app import db as _db
    from app.admin import berechne_manifest
    pfad = _db.standard_pfad()
    if not pfad.exists():
        sys.exit("Keine Bestands-DB gefunden - Eval braucht einen Korpus.")
    con = _db.connect_readonly(str(pfad))
    try:
        m = berechne_manifest(con)
    finally:
        con.close()
    return {"inhalts_hash": m["inhalts_hash"], "eintraege_gesamt": m["eintraege_gesamt"],
            # Heuristik: der Pi-Vollbestand liegt bei ~9500 Eintraegen (BACKLOG-Kopf).
            "korpus": ("voll" if m["eintraege_gesamt"] >= 9000
                       else f"lokal (Subset? {m['eintraege_gesamt']} Eintraege)")}


async def _lauf(argv) -> int:
    from fastmcp import Client
    from app.server import mcp

    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        sys.exit("ANTHROPIC_API_KEY fehlt (nur per Umgebung, nie in Dateien/argv).")
    nur = {t.strip().upper() for t in argv.nur.split(",")} if argv.nur else None
    system = projektanweisung()
    kopf = {"datum": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "modell": argv.modell, "client": "eval-harness (in-process, kein HTTP)",
            "richter": argv.richter, **_manifest_kopf()}
    ergebnisse: list[dict] = []

    try:
        async with Client(mcp) as mcp_client:
            tools = await mcp_client.list_tools()
            werkzeuge = [{"name": t.name, "description": t.description or "",
                          "input_schema": t.inputSchema} for t in tools]
            with httpx.Client(timeout=180.0) as http:
                for fall in FAELLE:
                    if nur and fall["id"] not in nur:
                        continue
                    if fall.get("uebersprungen"):
                        ergebnisse.append({"id": fall["id"], "status": "uebersprungen",
                                           "begruendung": fall["uebersprungen"]})
                        print(f"  ⏭️  {fall['id']}: uebersprungen")
                        continue
                    try:
                        text, tool_namen, auszuege = await _fahre_fall(
                            mcp_client, http, key, argv.modell, system, werkzeuge,
                            fall["frage"])
                    except Exception as ausnahme:
                        # Ein einzelner Fall darf den Lauf nicht kosten - er faellt
                        # ehrlich als 'abbruch' durch, die uebrigen laufen weiter.
                        ergebnisse.append({"id": fall["id"], "status": "abbruch",
                                           "begruendung": f"{type(ausnahme).__name__}: "
                                                          f"{ausnahme}"[:300]})
                        print(f"  💥 {fall['id']}: {type(ausnahme).__name__}")
                        continue
                    gruende = pruefe_deterministisch(fall, text, tool_namen)
                    eintrag = {"id": fall["id"], "frage": fall["frage"],
                               "tools": tool_namen, "deterministisch_gruende": gruende,
                               "antwort": text}
                    if gruende:
                        eintrag["status"] = "fail"
                    elif fall.get("richter") and argv.richter == "an":
                        urteil = _richter(http, key, argv.richter_modell,
                                          fall["rubrik"], fall["frage"], text, auszuege)
                        eintrag["richter_urteil"] = urteil
                        eintrag["status"] = ("pass_weich" if urteil["bestanden"]
                                             else "fail_weich")
                    elif fall.get("richter"):
                        eintrag["status"] = "pass_ungerichtet"  # Marker ok, Richter aus
                    else:
                        eintrag["status"] = "pass"
                    symbol = {"pass": "✅", "pass_weich": "✅(weich)", "fail": "❌",
                              "fail_weich": "❌(weich)",
                              "pass_ungerichtet": "✅(ohne Richter)"}
                    print(f"  {symbol[eintrag['status']]} {fall['id']}"
                          + (f" - {gruende[0]}" if gruende else ""))
                    ergebnisse.append(eintrag)
    finally:
        # Teilergebnisse sind wertvoll: der Report entsteht AUCH nach Strg-C oder einem
        # Fehler in der Rahmenlogik (sonst waeren die schon bezahlten Faelle verloren).
        if ergebnisse:
            _schreibe_report(kopf, ergebnisse)

    harte_fails = [e for e in ergebnisse if e["status"] in ("fail", "abbruch")]
    print(f"\n{len(ergebnisse)} Faelle, {len(harte_fails)} harte FAILs")
    return 1 if harte_fails else 0


def _schreibe_report(kopf: dict, ergebnisse: list[dict]) -> None:
    _ERGEBNISSE.mkdir(exist_ok=True)
    stamm = f"{kopf['datum'][:10]}-{kopf['modell']}"
    (_ERGEBNISSE / f"{stamm}.json").write_text(
        json.dumps({"kopf": kopf, "faelle": ergebnisse}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    zeilen = [f"# Verhaltens-Eval {kopf['datum']}", "",
              f"Modell: `{kopf['modell']}` · Client: {kopf['client']} · "
              f"Korpus: {kopf['korpus']} · `inhalts_hash: {kopf['inhalts_hash'][:16]}…`",
              "", "| Fall | Status | Anmerkung |", "|---|---|---|"]
    for e in ergebnisse:
        anmerkung = (e.get("deterministisch_gruende") or [""])[0] or \
            e.get("richter_urteil", {}).get("begruendung", "") or \
            e.get("begruendung", "")
        zeilen.append(f"| {e['id']} | {e['status']} | {anmerkung} |")
    (_ERGEBNISSE / f"{stamm}.md").write_text("\n".join(zeilen) + "\n", encoding="utf-8")
    print(f"\nReport: evals/ergebnisse/{stamm}.md")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--modell", default=os.environ.get("ANTHROPIC_MODEL")
                        or _STANDARD_MODELL)
    parser.add_argument("--nur", help="nur diese Fall-IDs, z. B. A1,B3")
    parser.add_argument("--richter", choices=("an", "aus"), default="an",
                        help="LLM-Richter fuer weiche Kriterien (kostet extra Tokens)")
    parser.add_argument("--richter-modell", dest="richter_modell",
                        default=_RICHTER_MODELL)
    sys.exit(asyncio.run(_lauf(parser.parse_args())))


if __name__ == "__main__":
    main()
