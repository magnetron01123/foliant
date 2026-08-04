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
from dataclasses import dataclass

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


class LlmFehler(RuntimeError):
    """Harter API-Fehler nach erschoepftem Retry - dieselbe Anfrage heilt das nicht."""


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
                         max_runden: int = 8, max_tokens: int = 4000,
                         system_cachen: bool = False) -> SchleifenErgebnis:
    """Tool-Use-Schleife ueber die Foliant-Tools.

    `verlauf` ist die komplette messages-Liste des Gespraechs (der Eval uebergibt
    genau eine Nutzerfrage, der Bot den Thread-Verlauf plus neue Frage); sie wird
    kopiert, nie mutiert. system_cachen=True setzt cache_control ephemeral auf den
    System-Block - das gecachte Praefix umfasst tools+system (zwischen den Runden
    einer Frage und zwischen Folgefragen im Cache-Fenster Reads statt Vollpreis).
    False haelt die Anfrageform byte-identisch zum gemessenen Eval-Stand.

    max_tokens 3000 -> 4000 (Rueckmeldung der Runde, 04.08.2026): Eine Uebersichtsantwort
    riss mitten im Satz ab, und der Hinweis darauf kommt NACH der bereits bezahlten
    Antwort - der Nutzer zahlt fuer etwas, das er nicht bekommt. Bewusst nur ein Schritt
    und nicht weit mehr: 3000 Tokens tragen deutsch schon rund vier Discord-Nachrichten,
    das Limit war also nicht zu klein - die Antwort war zu lang. Das eigentliche Gegenmittel
    steht deshalb in config/discord_zusatz.md (bei breiten Fragen gliedern statt
    ausschuetten); dieser Wert fangt nur die knappen Faelle ab."""
    messages = list(verlauf)
    tool_namen: list[str] = []
    bestandsauszuege: list[str] = []
    system_feld = ([{"type": "text", "text": system,
                     "cache_control": {"type": "ephemeral"}}]
                   if system_cachen else system)
    for _ in range(max_runden):
        daten = await api_aufruf(http, key, {
            "model": modell, "max_tokens": max_tokens, "system": system_feld,
            "messages": messages, "tools": werkzeuge})
        inhalt = daten.get("content", [])
        messages.append({"role": "assistant", "content": inhalt})
        if daten.get("stop_reason") != "tool_use":
            text = "".join(b.get("text", "") for b in inhalt
                           if b.get("type") == "text")
            return SchleifenErgebnis(text, tool_namen, bestandsauszuege,
                                     daten.get("stop_reason") or "end_turn")
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
    return SchleifenErgebnis("", tool_namen, bestandsauszuege, "runden_cap")
