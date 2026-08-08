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
  wie Website und Kanal-Sync-Test, eine Quelle, kein Duplikat. Die DC-Faelle fahren die
  Variante 'discord' (Projektanweisung + config/discord_zusatz.md), also den Prompt des
  Bots; alle uebrigen bleiben bei der reinen Projektanweisung.
- Report-Kopf = BACKLOG-§2-Pflichtfelder (Datum, Modell, Client, inhalts_hash) via
  admin.berechne_manifest. Ausgabe nach evals/ergebnisse/ (gitignored - die
  Vier-Dokumente-Regel gilt).

NICHT Teil von `make test` (kostet API-Tokens, ~23 Faelle x 3-5 Runden)."""
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
from evals.faelle import FAELLE, KOPF_ANKER

_PROJEKT = Path(__file__).resolve().parents[1]
_ERGEBNISSE = Path(__file__).resolve().parent / "ergebnisse"
# Belegzeile = '📖 ' + das 'zitat'-Feld der Tool-Ausgabe, z. B.
# '📖 Quelle: SRD 5.2.1 (Deutsch) · S. 139 · Regelversion: 2024' (Seite optional).
# Der Doppelpunkt ist optional: der Server baut das Zitat mit, die Prompt-Beispiele
# standen frueher ohne - der Volllauf 26.07.2026 lief genau in diese Luecke.
BELEG_RE = re.compile(r"📖 .+Regelversion:? \d{4}")
_RICHTER_MODELL = "claude-haiku-4-5-20251001"
# Explizit statt des llm.fahre_schleife-Defaults: die Rundenzahl ist Teil des
# Messaufbaus und soll im Eval sichtbar feststehen, nicht implizit mitwandern.
# (Bug-Fix 06.08.2026: der Name wurde benutzt, war aber nie definiert - JEDER Fall
# endete als NameError-'abbruch', der Harness konnte keinen einzigen Pass liefern.)
_MAX_RUNDEN = 8

# B13-Verbotsliste: NUR Feld- und Werkzeugnamen aus den Tool-Ausgaben. Kein legitimer
# Antworttext nennt je einen Payload-Schluessel - deshalb sind sie sicher zu bannen.
#
# Was hier bewusst NICHT steht, jeweils mit Beleg: 'Bestand' (steht in der ❌-, der ⚠️-
# und der 🌐-Pflichtphrase), 'Quelle' (in der Belegzeile), 'Werkzeug' (D&D-Fachbegriff,
# das Hintergrund-Geruest verlangt es), 'Suche/suchen' (die Suchen-Aktion ist eine
# 2024-Regel), 'Treffer' (Statblock-Schadenszeilen), 'deutsch/englisch/Uebersetzung/
# Fassung' (die *-Fussnote lautet woertlich "keine offizielle deutsche Uebersetzung",
# und Fall D3 VERLANGT, DE- und EN-Fassung zu nennen). Die snake_case-Form bannen, nie
# das Wort: 'abenteuer_setting' ja, 'Abenteuer-Setting' nein.
META_VERBOTEN = (
    r"foliant_[a-z_]+", r"hinweis_[a-z_]+", r"eintrag_id", r"quelle_kuerzel",
    r"regeltext_md", r"body_md", r"begriffe_deutsch", r"fremdsprachige_fassungen",
    r"konflikt_quellen", r"inhaltsart", r"abenteuer_setting", r"nur_im_text",
    r"weitere_fundstellen", r"anzeige_name", r"\*Kontext:",
    r"Datenbank", r"Unterabschnitt", r"Datenlage", r"(Werkzeug|Tool)-?[Aa]usgabe",
    r"[Ii]ch habe (nach)?ge(sucht|schaut)", r"[Ii]ch (suche|schaue nach)",
)
# Die eine Phrase, mit der eine Antwort weiterfuehrt (S14) - hoechstens einmal (B16).
ANGEBOT = "Sag Bescheid, wenn du"
FUSSNOTE = "keine offizielle deutsche Übersetzung"


def beleg_steht_zuletzt(text: str) -> bool:
    """Traegt die LETZTE nicht-leere Zeile den Beleg (B12 Slot 5)?

    Zeilenbasiert und nicht zeichengenau: Die Kalibrierung an echten Antworten
    (06.08.2026) zeigte eine Menue-Antwort mit DREI Belegzeilen, deren letzte je Quelle
    einen Zusatz traegt ('… Regelversion: 2024 (Untoter Schutzherr)'). Mehrere
    📖-Zeilen sind nach B12 ausdruecklich erlaubt; ein Anker, der ein Ende direkt nach
    der Jahreszahl verlangt, waere ein Fehlalarm der Klasse A3/B1/F2 gewesen."""
    zeilen = [z for z in text.splitlines() if z.strip()]
    return bool(zeilen) and "📖" in zeilen[-1]


def pruefe_geruest(text: str) -> list[str]:
    """Was fuer JEDE Antwort gilt (B12/B13/B16) - unabhaengig davon, was der Fall
    erklaert hat. Bewusst eine EIGENE Funktion neben pruefe_deterministisch: die
    Faelle dort beschreiben ihre eigenen Erwartungen, hier steht der Vertrag, den
    das Antwortgeruest allen Antworten auferlegt.

    Warum ueberhaupt deterministisch: Bis zum 06.08.2026 beurteilte das der
    LLM-Richter. Im Volllauf lag er bei zwei von drei Beanstandungen falsch, waehrend
    der tatsaechliche Verstoss unbemerkt in derselben Antwort stand (D1 eroeffnete mit
    einer Meta-Aussage vor der Kopfzeile, C3 zitierte einen Feldnamen). Struktur ist
    messbar - dann soll sie gemessen und nicht begutachtet werden."""
    gruende: list[str] = []
    if not re.match(KOPF_ANKER, text):
        gruende.append(f"Kopfzeile ohne Katalog-Emoji (B12 Slot 1): {text[:60]!r}")
    for muster in META_VERBOTEN:
        if re.search(muster, text):
            gruende.append(f"Werkzeug-/Feldname in der Antwort (B13): {muster!r}")
    if "📖" in text and not beleg_steht_zuletzt(text):
        gruende.append("Belegzeile ist nicht die letzte Zeile (B12 Slot 5)")
    if text.count(ANGEBOT) > 1:
        gruende.append(f"{text.count(ANGEBOT)} Angebote statt hoechstens einem (B16)")
    if FUSSNOTE in text and "📖" in text and text.index(FUSSNOTE) > text.index("📖"):
        gruende.append("*-Fussnote steht hinter der Belegzeile (B12 Slot 5)")
    return gruende


def projektanweisung() -> str:
    """Der Text aus config/projektanweisung.md - EINE Leseestelle fuer alle Nutzer
    (Website, Eval, deploy/projektanweisung.sh), damit keine veraltete Kopie umgeht."""
    text = stil.projektanweisung()
    if text is None:
        sys.exit("config/projektanweisung.md fehlt - ohne Projektanweisung kein Eval.")
    return text


def md_tabelle_ausserhalb_code(text: str) -> bool:
    """Trennzeile einer Markdown-Tabelle ('|---|---|') ausserhalb von Codebloecken?

    Discord rendert Markdown-Tabellen nicht - der Zusatzprompt verbietet sie deshalb.
    Gesucht wird NUR die Trennzeile: sie besteht ausschliesslich aus | - : und
    Leerzeichen und kommt in normalem Text nicht vor. Codebloecke sind ausgenommen,
    denn dort ist eine Spaltenlinie genau die erlaubte Darstellung (ASCII-Tabelle)."""
    im_code = False
    for zeile in text.split("\n"):
        if zeile.lstrip().startswith("```"):
            im_code = not im_code
            continue
        blank = zeile.strip()
        if (not im_code and "|" in blank and "-" in blank
                and set(blank) <= set("|-: ")):
            return True
    return False


# Wie breit eine Codeblock-Zeile in Discord sein darf. Der Block bricht dort NICHT um -
# am Handy muss man breitere Tabellen seitwaerts schieben, und am Tisch ist das Handy das
# Geraet. Gemessen an echten Bot-Antworten (08.08.2026): 39 bis 93 Zeichen, Median 51 -
# die Regel sagte bis dahin nur 'Codeblock mit festen Spalten' und nichts ueber Breite.
CODEBLOCK_MAX_BREITE = 45


def zu_breite_codeblock_zeilen(text: str, max_breite: int = CODEBLOCK_MAX_BREITE
                               ) -> list[str]:
    """Codeblock-Zeilen, die das Breitenbudget reissen (laengste zuerst).

    Nur INNERHALB von ```-Bloecken: Fliesstext bricht in Discord normal um, dort ist
    Laenge kein Problem. Die Zaunzeilen selbst zaehlen nicht mit."""
    im_code, zu_breit = False, []
    for zeile in text.split("\n"):
        if zeile.lstrip().startswith("```"):
            im_code = not im_code
            continue
        if im_code and len(zeile.rstrip()) > max_breite:
            zu_breit.append(zeile.rstrip())
    return sorted(zu_breit, key=len, reverse=True)


def systeme() -> dict[str, str]:
    """Die Prompt-Varianten, gegen die gemessen wird.

    'standard' ist die reine Projektanweisung - der Stand, auf den sich alle bisherigen
    Messungen beziehen. 'discord' haengt config/discord_zusatz.md an, also genau den
    Prompt, den der Bot faehrt (haupt.py._system_prompt). Ohne diese Variante galt die
    Messung fuer den Bot nur unter der ANNAHME, der Zusatz aendere nichts Tragendes.
    Fehlt die Zusatz-Datei, fehlt der Schluessel - die DC-Faelle gelten dann als
    uebersprungen statt still gegen den falschen Prompt zu laufen."""
    basis = projektanweisung()
    varianten = {"standard": basis}
    zusatz = stil.discord_zusatz()
    if zusatz:
        varianten["discord"] = f"{basis}\n\n{zusatz}"
    return varianten


# Statblock-Sektionen, kuratiert statt generisch extrahiert. Das Vokabular deckt 100 %
# der echten Ueberschriften im Bestand ab (srd-de setzt '######', open5e '####') und
# ignoriert damit automatisch die rund 20 fehlgeparsten Zeilen der Art
# '###### **Resistenzen** Kaelte', die eine generische Header-Suche als Sektion zaehlte.
# Je Eintrag: (Ueberschrift im Auszug, im Antworttext akzeptierte Formen).
_STATBLOCK_SEKTIONEN = (
    ("Legendäre Aktionen", ("Legendäre Aktionen", "Legendary Actions")),
    ("Legendary Actions", ("Legendäre Aktionen", "Legendary Actions")),
    ("Bonusaktionen", ("Bonusaktionen", "Bonus-Aktionen", "Bonus Actions")),
    ("Bonus Actions", ("Bonusaktionen", "Bonus-Aktionen", "Bonus Actions")),
    ("Reaktionen", ("Reaktionen", "Reactions")),
    ("Reactions", ("Reaktionen", "Reactions")),
    ("Merkmale", ("Merkmale", "Eigenschaften", "Traits")),
    ("Traits", ("Merkmale", "Eigenschaften", "Traits")),
    ("Aktionen", ("Aktionen", "Actions")),
    ("Actions", ("Aktionen", "Actions")),
)
# Bewusst KLEIN: uebersprungen werden soll nur, was WIRKLICH leer ist (der verlorene
# Solar-Block hat null Zeichen). Ein grosszuegiger Wert - 20 Zeichen im ersten Entwurf -
# haelt eine echte kurze Sektion ('Bogen des Toetens.') faelschlich fuer leer und macht
# den Check an genau der Stelle blind, an der er greifen soll. Die drei Zeichen fangen
# uebrig gebliebene Auszeichnung ('**') ab.
_SEKTION_MIN_INHALT = 3


def _sektionsinhalt(auszug: str, ab: int) -> str:
    """Was zwischen dieser Ueberschrift und der naechsten Grenze steht.

    Zwei Grenzen, beide noetig: die naechste Ueberschrift - und das Ende des
    JSON-Strings, in dem der Regeltext steckt. Ohne die zweite waere der 'Inhalt' der
    LETZTEN Sektion der ganze Rest des Payloads, und der leere Solar-Bonusaktionsblock
    saehe gefuellt aus.

    Das Feldende ist das erste NICHT maskierte Anfuehrungszeichen - nicht ein Trennzeichen
    wie '","'. Anfuehrungszeichen IM Regeltext stehen als '\\\"' und werden dadurch korrekt
    uebersprungen, und die Pruefung haengt nicht daran, ob der Serialisierer kompakt
    (FastMCP) oder mit Leerzeichen schreibt. Die literalen '\\n' zaehlen als Leerraum."""
    rest = auszug[ab:]
    feldende = re.search(r'(?<!\\)"', rest)
    if feldende:
        rest = rest[:feldende.start()]
    naechste = re.search(r"#{3,6}", rest)
    if naechste:
        rest = rest[:naechste.start()]
    return rest.replace("\\n", " ").strip()


def fehlende_statblock_sektionen(text: str, bestandsauszuege: list[str]) -> list[str]:
    """Welche Statblock-Abschnitte des gelieferten Eintrags fehlen in der Antwort?

    Drei Eigenheiten, an denen eine naive Fassung scheitert:

    1. Die Auszuege sind JSON, nicht Markdown - ein Zeilenumbruch steht dort als die
       ZWEI Zeichen '\\' und 'n'. Ein zeilenverankertes '^#{3,6}'-Muster faende null
       Ueberschriften, der Check bestuende immer, und niemand merkte es. Deshalb
       Literalsuche nach dem kuratierten Vokabular.
    2. LEERE Sektionen zaehlen nicht. Der srd-de-Solar traegt '###### Bonusaktionen' als
       letzte Zeile OHNE Inhalt (Zweispalten-Riss des Imports, 3 Faelle im Bestand) - was
       der Bestand nicht hat, kann keine Antwort liefern. Dieselbe Regel deckt den
       abgeschnittenen Auszug mit ab (llm._MAX_AUSZUG_ZEICHEN).
    3. 'Aktionen' ist Teilstring von 'Legendäre Aktionen' - die langen Formen werden im
       Antworttext zuerst ausgeblendet, sonst besteht eine Antwort ohne Aktionsblock,
       nur weil sie legendaere Aktionen nennt.

    Nur Detail-Auszuege werden gelesen: eine Trefferliste enthaelt Abschnitte fremder
    Kreaturen und wuerde Sektionen einfordern, die gar nicht gefragt waren."""
    detail = "\n".join(a for a in bestandsauszuege if a.startswith("[foliant_hol_eintrag]"))
    if not detail:
        return []
    rest = text
    for _, formen in _STATBLOCK_SEKTIONEN:                  # laengste Form zuerst
        for form in sorted(formen, key=len, reverse=True):
            if len(form.split()) > 1:
                rest = rest.replace(form, " ")
    fehlend: list[str] = []
    for ueberschrift, formen in _STATBLOCK_SEKTIONEN:
        treffer = re.search(rf"#{{3,6}}\s*{re.escape(ueberschrift)}\b", detail)
        if not treffer:
            continue
        if len(_sektionsinhalt(detail, treffer.end())) < _SEKTION_MIN_INHALT:
            continue                                        # leer oder abgeschnitten
        pruefraum = text if len(ueberschrift.split()) > 1 else rest
        if not any(form in pruefraum for form in formen) and ueberschrift not in fehlend:
            fehlend.append(ueberschrift)
    return [f"Statblock-Abschnitt fehlt in der Antwort: {s!r}" for s in fehlend]


def zu_fahrende_varianten(fall: dict, prompt_varianten: dict[str, str],
                          modus: str) -> list[tuple[str, str]]:
    """Welche (Variante, System)-Paare ein Fall faehrt.

    'fall' (Default): genau die Variante, die der Fall deklariert - der gemessene
    Normalzustand. 'beide': JEDER Fall laeuft gegen Konnektor- UND Discord-Prompt -
    die Paritaetsmessung. Der Eigentuemer-Anspruch (08.08.2026) ist, dass beide Wege
    moeglichst identisch antworten; bis dahin liess sich das nur von Hand vergleichen
    (Review-Skript), jetzt traegt der Harness es selbst. Fehlt der Discord-Zusatz,
    liefert systeme() nur 'standard' - dann faehrt 'beide' ehrlich nur diese."""
    if modus == "beide":
        return sorted(prompt_varianten.items())
    variante = fall.get("system", "standard")
    system = prompt_varianten.get(variante)
    return [] if system is None else [(variante, system)]


def pruefe_deterministisch(fall: dict, text: str, tool_namen: list[str],
                           bestandsauszuege: list[str] | None = None) -> list[str]:
    """Harte Marker-/Format-Pruefungen; leere Liste = bestanden.

    `bestandsauszuege` ist optional, damit die vorhandenen Drei-Argument-Aufrufe der
    Tests gueltig bleiben; gebraucht wird es nur von der Statblock-Pruefung."""
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
    # B12-Formpruefungen (Serie F) brauchen Anker (Antwortanfang, letzte Zeile) -
    # Substrings koennen das nicht ausdruecken, deshalb echte Muster.
    for muster in fall.get("muster_pflicht", []):
        if not re.search(muster, text):
            gruende.append(f"Pflicht-Muster fehlt: {muster!r}")
    for muster in fall.get("muster_verboten", []):
        if re.search(muster, text, re.IGNORECASE):
            gruende.append(f"Verbotenes Muster in der Antwort: {muster!r}")
    erwartet = fall.get("erwartete_tools")
    if erwartet and not set(erwartet) & set(tool_namen):
        gruende.append(f"Keines der erwarteten Tools aufgerufen: {erwartet} "
                       f"(aufgerufen: {tool_namen or 'keine'})")
    if fall.get("keine_md_tabelle") and md_tabelle_ausserhalb_code(text):
        gruende.append("Markdown-Tabelle ausserhalb eines Codeblocks (Discord "
                       "rendert sie nicht)")
    # Am selben Schalter wie das Tabellenverbot: Beides sind Discord-Darstellungsregeln
    # und beide gelten nur dort (im Konnektor sind Tabellen und lange Zeilen korrekt).
    if fall.get("keine_md_tabelle"):
        zu_breit = zu_breite_codeblock_zeilen(text)
        if zu_breit:
            gruende.append(
                f"{len(zu_breit)} Codeblock-Zeile(n) breiter als "
                f"{CODEBLOCK_MAX_BREITE} Zeichen (Discord bricht im Block nicht um, "
                f"am Handy Seitwaertsscrollen): {len(zu_breit[0])} Zeichen bei "
                f"{zu_breit[0][:40]!r}")
    if fall.get("statblock_vollstaendig"):
        gruende += fehlende_statblock_sektionen(text, bestandsauszuege or [])
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
    prompt_varianten = systeme()
    kopf = {"datum": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "modell": argv.modell, "client": "eval-harness (in-process, kein HTTP)",
            "richter": argv.richter, "prompts": sorted(prompt_varianten),
            **_manifest_kopf()}
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
                    paare = zu_fahrende_varianten(fall, prompt_varianten, argv.prompt)
                    if not paare:
                        ergebnisse.append({"id": fall["id"], "status": "uebersprungen",
                                           "begruendung": "Prompt-Variante fehlt "
                                                          "(config/discord_zusatz.md)"})
                        print(f"  ⏭️  {fall['id']}: Prompt-Variante fehlt")
                        continue
                    for variante, system in paare:
                      # Bei '--prompt beide' unterscheidet das Suffix die Zeilen im
                      # Report; im Normalmodus bleibt die ID unveraendert.
                      fall_id = (fall["id"] if argv.prompt != "beide"
                                 else f"{fall['id']}@{variante}")
                      # Kanalgebundene Kriterien gelten nur fuer die DEKLARIERTE
                      # Variante: 'keine_md_tabelle' ist eine Discord-Regel (der Zusatz
                      # verbietet Tabellen, weil Discord sie nicht rendert) - im
                      # Konnektor sind sie korrekt. Der erste Paritaetslauf (08.08.2026)
                      # warf DC3@standard genau dafuer als FAIL, obwohl die Antwort dort
                      # regelkonform war: ein Artefakt des Messmodus, kein Verhalten.
                      gefahren = fall
                      if variante != fall.get("system", "standard"):
                          gefahren = {k: v for k, v in fall.items()
                                      if k != "keine_md_tabelle"}
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
                        ergebnisse.append({"id": fall_id, "status": "abbruch",
                                           "begruendung": f"{type(ausnahme).__name__}: "
                                                          f"{ausnahme}"[:300]})
                        print(f"  💥 {fall_id}: {type(ausnahme).__name__}")
                        continue
                      gruende = (pruefe_deterministisch(gefahren, text, tool_namen, auszuege)
                               + pruefe_geruest(text))
                      eintrag = {"id": fall_id, "frage": fall["frage"],
                               "prompt": variante,
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
                      print(f"  {symbol[eintrag['status']]} {fall_id}"
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
              "", "| Fall | Prompt | Status | Anmerkung |", "|---|---|---|---|"]
    for e in ergebnisse:
        anmerkung = (e.get("deterministisch_gruende") or [""])[0] or \
            e.get("richter_urteil", {}).get("begruendung", "") or \
            e.get("begruendung", "")
        zeilen.append(f"| {e['id']} | {e.get('prompt', '—')} | {e['status']} "
                      f"| {anmerkung} |")
    (_ERGEBNISSE / f"{stamm}.md").write_text("\n".join(zeilen) + "\n", encoding="utf-8")
    print(f"\nReport: evals/ergebnisse/{stamm}.md")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--modell", default=os.environ.get("ANTHROPIC_MODEL")
                        or llm.STANDARD_MODELL)
    parser.add_argument("--nur", help="nur diese Fall-IDs, z. B. A1,B3")
    parser.add_argument("--prompt", choices=("fall", "beide"), default="fall",
                        help="'beide' faehrt JEDEN Fall gegen Konnektor- UND "
                             "Discord-Prompt (Paritaetsmessung, doppelte Kosten)")
    parser.add_argument("--richter", choices=("an", "aus"), default="an",
                        help="LLM-Richter fuer weiche Kriterien (kostet extra Tokens)")
    parser.add_argument("--richter-modell", dest="richter_modell",
                        default=_RICHTER_MODELL)
    sys.exit(asyncio.run(_lauf(parser.parse_args())))


if __name__ == "__main__":
    main()
