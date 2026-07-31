"""Schicht-3-Verhaltens-Evals (BACKLOG.md §2) werkzeuggestuetzt: fuehrt die Checklisten-
Fragen gegen die ECHTE Claude-API mit den ECHTEN Foliant-Tools aus und bewertet die
Antworten deterministisch (Marker/Format) plus optional per LLM-Richter.

    ANTHROPIC_API_KEY=... python -m evals.verhaltens_eval [--modell ...] [--nur A1,B3]
                                                          [--richter an|aus]

Architektur-Entscheidungen:
- Tools IN-PROCESS ueber fastmcp.Client(app.server.mcp): nutzt die echten generierten
  Schemas/Docstrings (Kanal 2), ohne Port/Token. Bewusste Untreue ggu. dem echten
  HTTP-Connector (Netz/Serialisierung) - das prueft Schicht 2.
- Die Tool-Use-Schleife lebt in app/llm.py (geteilt mit dem Discord-Bot - nie zwei
  driftende Kopien). Der Eval ruft sie mit system_cachen=False auf: die Anfrageform
  bleibt identisch zum gemessenen Stand vom 26.07.2026.
- System-Prompt = config/projektanweisung.md ueber config.stil - dieselbe Leseestelle
  wie Website und Kanal-Sync-Test, eine Quelle, kein Duplikat.
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
from datetime import datetime, timezone
from pathlib import Path

import httpx

from app import llm
from config import stil
from evals.faelle import FAELLE

_PROJEKT = Path(__file__).resolve().parents[1]
_ERGEBNISSE = Path(__file__).resolve().parent / "ergebnisse"
# Belegzeile = '📖 ' + das 'zitat'-Feld der Tool-Ausgabe, z. B.
# '📖 Quelle: SRD 5.2.1 (Deutsch) · S. 139 · Regelversion: 2024' (Seite optional).
# Der Doppelpunkt ist optional: der Server baut das Zitat mit, die Prompt-Beispiele
# standen frueher ohne - der Volllauf 26.07.2026 lief genau in diese Luecke.
BELEG_RE = re.compile(r"📖 .+Regelversion:? \d{4}")
_RICHTER_MODELL = "claude-haiku-4-5-20251001"


def projektanweisung() -> str:
    """Der Text aus config/projektanweisung.md - EINE Leseestelle fuer alle Nutzer
    (Website, Eval, deploy/projektanweisung.sh), damit keine veraltete Kopie umgeht."""
    text = stil.projektanweisung()
    if text is None:
        sys.exit("config/projektanweisung.md fehlt - ohne Projektanweisung kein Eval.")
    return text


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


async def _richter(http, key: str, richter_modell: str, rubrik: str, frage: str,
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
    daten = await llm.api_aufruf(http, key, {
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
            werkzeuge = await llm.lade_werkzeuge(mcp_client)
            async with httpx.AsyncClient(timeout=180.0) as http:
                for fall in FAELLE:
                    if nur and fall["id"] not in nur:
                        continue
                    if fall.get("uebersprungen"):
                        ergebnisse.append({"id": fall["id"], "status": "uebersprungen",
                                           "begruendung": fall["uebersprungen"]})
                        print(f"  ⏭️  {fall['id']}: uebersprungen")
                        continue
                    try:
                        # system_cachen=False: Anfrageform identisch zum gemessenen
                        # Stand (26.07.2026) - der Eval ist das Messinstrument.
                        erg = await llm.fahre_schleife(
                            mcp_client, http, key, argv.modell, system, werkzeuge,
                            [{"role": "user", "content": fall["frage"]}],
                            max_runden=_MAX_RUNDEN)
                        text, tool_namen, auszuege = (erg.text, erg.tool_namen,
                                                      erg.bestandsauszuege)
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
                               "antwort": text, "stop_grund": erg.stop_grund}
                    if gruende:
                        eintrag["status"] = "fail"
                    elif fall.get("richter") and argv.richter == "an":
                        urteil = await _richter(http, key, argv.richter_modell,
                                                fall["rubrik"], fall["frage"], text,
                                                auszuege)
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
    # Datum PLUS Uhrzeit: gleichtaegige Laeufe ueberschrieben sich sonst gegenseitig -
    # der 17-Faelle-Pi-Report ging real an einen 3-Faelle-Nachlauf verloren (26.07.2026).
    stamm = f"{kopf['datum'][:16].replace(':', '')}-{kopf['modell']}"
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
                        or llm.STANDARD_MODELL)
    parser.add_argument("--nur", help="nur diese Fall-IDs, z. B. A1,B3")
    parser.add_argument("--richter", choices=("an", "aus"), default="an",
                        help="LLM-Richter fuer weiche Kriterien (kostet extra Tokens)")
    parser.add_argument("--richter-modell", dest="richter_modell",
                        default=_RICHTER_MODELL)
    sys.exit(asyncio.run(_lauf(parser.parse_args())))


if __name__ == "__main__":
    main()
