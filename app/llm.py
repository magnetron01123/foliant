"""EIN Anthropic-Tool-Use-Loop fuer alle Laufzeit-Nutzer (Eval-Harness, Discord-Bot).

Extrahiert aus evals/verhaltens_eval.py (26.07.2026), damit Bot und Messinstrument
nie zwei driftende Kopien fahren: derselbe Loop, dieselben Kappungen, dasselbe
Fehlerverhalten. Der Eval ruft mit system_cachen=False auf und stellt damit exakt
die Anfragen des gemessenen Standes; der Bot schaltet Prompt-Caching zu.

Bewusst NICHT hier: die Denk-Konfiguration des Charakterbogen-Uebersetzers
(_denk_konfig) - der Eval lief immer ohne thinking-Feld, und der Bot muss exakt so
anfragen wie das Messinstrument, sonst gilt die Messung nicht fuer ihn.

API direkt per httpx (Projektlinie: kein anthropic-SDK, requirements.txt-Kopf);
Key kommt vom Aufrufer und wird nie geloggt."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import httpx

API_URL = "https://api.anthropic.com/v1/messages"

# Das Modell, das Bot UND Eval fahren, wenn ANTHROPIC_MODEL nicht gesetzt ist. Es steht
# hier, weil die GLEICHHEIT der beiden eine Zusage ist: BACKLOG §1/M6 begruendet das
# Bot-Verhalten mit dem gemessenen Eval-Stand ("gleiche Schleife wie der Eval"). Driftet
# einer der beiden Defaults, misst der Eval still etwas anderes, als der Bot tut - und
# der Report behauptet weiter, er beschreibe den Bot.
# Der Charakterbogen-Uebersetzer hat bewusst KEINEN Default: dort kostet jede Konvertierung
# Geld, also soll ein fehlendes ANTHROPIC_MODEL auffallen statt still etwas zu waehlen.
STANDARD_MODELL = "claude-sonnet-5"

# Kappungen aus dem Eval-Erstlauf: tool_result begrenzt den Kontext je Runde,
# der Auszug haelt die Richter-/Anzeige-Grundlage kompakt.
_MAX_TOOL_RESULT_ZEICHEN = 20_000
_MAX_AUSZUG_ZEICHEN = 6_000

# Cache-Lebensdauer. Der Standard waeren 5 Minuten - zu kurz fuer diese Runde: das
# Abfrage-Protokoll (1997 Aufrufe, 26.07.-09.08.2026, zu 113 Fragen gebuendelt) zeigt
# einen MEDIAN von 14 Minuten zwischen zwei Fragen. Nur 27-31 % der Luecken liegen unter
# 5 Minuten, aber 59-71 % unter einer Stunde - der Standard-Cache waere also meistens
# schon abgelaufen, wenn die naechste Frage kommt. Eine Stunde kostet beim Schreiben
# 2x statt 1,25x und ist damit bei der ERSTEN Frage teurer; ab der zweiten ist sie
# billiger, weil Treffer die Frist kostenlos verlaengern.
_CACHE = {"type": "ephemeral", "ttl": "1h"}


class LlmFehler(RuntimeError):
    """Harter API-Fehler nach erschoepftem Retry - dieselbe Anfrage heilt das nicht."""


@dataclass
class Verbrauch:
    """Token-Zaehlung ueber ALLE Runden einer Frage, aus den usage-Feldern der API.

    Ohne sie ist jede Aussage ueber das Prompt-Caching geraten: ob ein Cache-Eintrag
    getroffen wird, meldet die API NICHT als Fehler oder Warnung - ein zu kurzes
    Praefix, ein verschobenes Byte oder eine abgelaufene TTL sehen von aussen
    identisch aus wie ein Volltreffer. Die drei Zahlen sind die einzige Auskunft."""
    cache_gelesen: int = 0
    cache_geschrieben: int = 0
    ungecacht: int = 0
    ausgabe: int = 0

    def addiere(self, usage: dict | None) -> None:
        usage = usage or {}
        self.cache_gelesen += usage.get("cache_read_input_tokens") or 0
        self.cache_geschrieben += usage.get("cache_creation_input_tokens") or 0
        self.ungecacht += usage.get("input_tokens") or 0
        self.ausgabe += usage.get("output_tokens") or 0

    @property
    def trefferquote(self) -> float:
        """Anteil der aus dem Cache gelesenen an allen Eingabe-Tokens (0.0 bis 1.0)."""
        gesamt = self.cache_gelesen + self.cache_geschrieben + self.ungecacht
        return self.cache_gelesen / gesamt if gesamt else 0.0


@dataclass
class SchleifenErgebnis:
    """Ausgang einer Tool-Use-Schleife.

    stop_grund macht das Ende EXPLIZIT ('end_turn' | 'max_tokens' | 'refusal' |
    'runden_cap' | ...): der alte Eval-Loop gab beim Runden-Cap stumm '' zurueck,
    und erst der Grader deutete das nachtraeglich als Fehler - ein Bot muss dem
    Nutzer stattdessen sofort einen ehrlichen Grund nennen koennen."""
    text: str
    tool_namen: list[str]
    bestandsauszuege: list[str]
    stop_grund: str
    verbrauch: Verbrauch = field(default_factory=Verbrauch)


async def lade_werkzeuge(mcp_client) -> list[dict]:
    """Die MCP-Tool-Schemas in Anthropic-Form - aus den ECHT generierten Schemas
    (fastmcp.Client), nie aus einer handgepflegten Kopie."""
    tools = await mcp_client.list_tools()
    return [{"name": t.name, "description": t.description or "",
             "input_schema": t.inputSchema} for t in tools]


async def api_aufruf(http: httpx.AsyncClient, key: str, body: dict) -> dict:
    """Ein Messages-Aufruf mit einfachem Retry (429/5xx/529); wirft bei hartem Fehler.
    await statt time.sleep: der alte Eval-Retry blockierte den Event-Loop - fuer das
    Eval egal, fuer einen Bot mit parallelen Discord-Events nicht."""
    for versuch in range(3):
        antwort = await http.post(API_URL, json=body, headers={
            "x-api-key": key, "anthropic-version": "2023-06-01"})
        if antwort.status_code in (429, 500, 502, 503, 529) and versuch < 2:
            await asyncio.sleep(5 * (versuch + 1))
            continue
        antwort.raise_for_status()
        return antwort.json()
    raise LlmFehler("API-Retry erschoepft")


async def fahre_schleife(mcp_client, http: httpx.AsyncClient, key: str, modell: str,
                         system: str, werkzeuge: list[dict], verlauf: list[dict], *,
                         max_runden: int = 8, max_tokens: int = 8000,
                         system_cachen: bool = False) -> SchleifenErgebnis:
    """Tool-Use-Schleife ueber die Foliant-Tools.

    `verlauf` ist die komplette messages-Liste des Gespraechs (der Eval uebergibt
    genau eine Nutzerfrage, der Bot den Thread-Verlauf plus neue Frage); sie wird
    kopiert, nie mutiert. system_cachen=True schaltet das Prompt-Caching zu und
    formt die Anfrage so, dass der Cache ueberlebt (drei Stellen, siehe unten);
    False haelt die Anfrageform byte-identisch zum gemessenen Eval-Stand.

    max_tokens deckt den TEUERSTEN erlaubten Fall ab: seit B15 setzt eine Auskunft ueber
    eine Unterklasse ihre fuenf Stufen-Merkmale aus Einzeleintraegen zu EINER Antwort
    zusammen. Genau dieser Fall riss am 06.08.2026 im Pi-Eval (F2) nacheinander bei 4000
    UND bei 6000 Tokens ab - jedes Mal kurz vor der Belegzeile, also an der Stelle, die
    B12 zwingend verlangt. Gegen zu lange Antworten wirkt nicht dieser Wert, sondern die
    Gliederungsregel in config/discord_zusatz.md; eine abgeschnittene Antwort kann sie
    nicht heilen, und Discord teilt lange Antworten ohnehin selbst auf."""
    messages = list(verlauf)
    tool_namen: list[str] = []
    bestandsauszuege: list[str] = []
    verbrauch = Verbrauch()
    # Caching-Stelle 1 - der FESTE Breakpoint auf dem System-Block. Er deckt das
    # unveraenderliche Praefix ab (tools+system, rund 7000 Token) und haelt es auch
    # ueber getrennte Fragen hinweg im Cache.
    system_feld = ([{"type": "text", "text": system, "cache_control": _CACHE}]
                   if system_cachen else system)
    # Caching-Stelle 2 - der REQUEST-WEITE Breakpoint. Er wandert automatisch auf den
    # letzten cachefaehigen Block und deckt damit den WACHSENDEN Teil ab: die
    # Tool-Ergebnisse (bis 20k Zeichen je Runde) und den Thread-Verlauf. Ohne ihn
    # zahlte jede Folgerunde diesen Teil voll, obwohl er byte-gleich zur Vorrunde ist -
    # bei acht Runden das Mehrfache des festen Praefixes. Beide zusammen sind zwei der
    # vier erlaubten Breakpoints.
    cache_feld = {"cache_control": _CACHE} if system_cachen else {}
    for _ in range(max_runden):
        daten = await api_aufruf(http, key, {
            "model": modell, "max_tokens": max_tokens, "system": system_feld,
            "messages": messages, "tools": werkzeuge, **cache_feld})
        verbrauch.addiere(daten.get("usage"))
        inhalt = daten.get("content", [])
        messages.append({"role": "assistant", "content": inhalt})
        if daten.get("stop_reason") != "tool_use":
            text = "".join(b.get("text", "") for b in inhalt
                           if b.get("type") == "text")
            return SchleifenErgebnis(text, tool_namen, bestandsauszuege,
                                     daten.get("stop_reason") or "end_turn",
                                     verbrauch)
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
                # Report wurde nie geschrieben (Befund Eval-Erstlauf 26.07.2026).
                text_out, fehler = f"{type(ausnahme).__name__}: {ausnahme}", True
            ergebnisse.append({"type": "tool_result", "tool_use_id": block["id"],
                               "content": text_out[:_MAX_TOOL_RESULT_ZEICHEN],
                               "is_error": fehler})
            if not fehler:
                bestandsauszuege.append(f"[{block['name']}]\n"
                                        f"{text_out[:_MAX_AUSZUG_ZEICHEN]}")
        messages.append({"role": "user", "content": ergebnisse})
    # Runden-Cap: EINE letzte Anfrage, in der das Modell keine Werkzeuge mehr aufrufen
    # kann, damit aus dem bereits Geholten noch eine Antwort wird. Bis zum 07.08.2026
    # kam hier ein leeres Ergebnis zurueck - der
    # Nutzer bekam nach 8 Runden bezahlter Recherche gar nichts, und im Discord nur den
    # Hinweis, die Frage enger zu stellen. Aufgefallen ist es am Eval-Fall DC3 (neun
    # Waffeneigenschaften, 12-28 Werkzeugaufrufe): dreimal in Folge eine leere Antwort.
    # Der Stop-Grund bleibt 'runden_cap' - die Auskunft kann unvollstaendig sein, und der
    # Bot sagt das weiterhin dazu; er sagt es nur nicht mehr STATT einer Antwort.
    #
    # Der AUFTRAG muss dabeistehen: Ohne ihn endet das Gespraech mit Werkzeug-Ergebnissen,
    # und das Modell lieferte gemessen (07.08.2026) einen Denkblock mit 157 Tokens und
    # einen LEEREN Text - es wartete auf den naechsten Werkzeugaufruf, den es nicht mehr
    # geben konnte. Der Satz haengt am letzten Nutzer-Turn statt als eigener: zwei
    # Nutzer-Turns hintereinander weist die API zurueck.
    if messages and messages[-1]["role"] == "user" and isinstance(
            messages[-1].get("content"), list):
        messages[-1]["content"] = messages[-1]["content"] + [{
            "type": "text",
            "text": ("Antworte JETZT abschliessend aus dem bereits Geholten - weitere "
                     "Werkzeugaufrufe sind nicht mehr moeglich. Halte das Antwortgeruest "
                     "ein und sag dazu, falls die Auskunft unvollstaendig bleibt.")}]
    # Caching-Stelle 3 - WIE die Werkzeuge entzogen werden. Die Werkzeuge einfach
    # wegzulassen entzieht sie zwar, wirft aber auch den gesamten Cache weg: die
    # Werkzeuge stehen ganz oben im Praefix (tools -> system -> messages), und wer dort
    # etwas aendert, invalidiert alles dahinter. 'tool_choice: none' erreicht dasselbe
    # eine Ebene tiefer - das Modell kann keine Werkzeuge aufrufen, das gecachte
    # tools+system-Praefix bleibt aber gueltig. Ohne Caching bleibt es beim Weglassen:
    # der Eval ist das Messinstrument und darf seine Anfrageform nicht aendern.
    schluss = {"tools": werkzeuge, "tool_choice": {"type": "none"}} if system_cachen \
        else {}
    daten = await api_aufruf(http, key, {
        "model": modell, "max_tokens": max_tokens, "system": system_feld,
        "messages": messages, **schluss, **cache_feld})
    verbrauch.addiere(daten.get("usage"))
    text = "".join(b.get("text", "") for b in daten.get("content", [])
                   if b.get("type") == "text")
    return SchleifenErgebnis(text, tool_namen, bestandsauszuege, "runden_cap",
                             verbrauch)
