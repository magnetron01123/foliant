"""Antwort-Aufbereitung fuer Discord: 2000-Zeichen-Splitting, Thread-Titel, deutsche
Fehlertexte. Bewusst ohne discord.py-Import - reine Textlogik, vollstaendig testbar."""
from __future__ import annotations

# Discord-Hardlimit ist 2000; 100 Zeichen Reserve fuer Zaeune-Wiederoeffnung u. Ae.
LIMIT = 1900
THREAD_TITEL_LIMIT = 100

# Fehlertexte im Foliant-Ton (deutsch, ehrlich, kein Stacktrace in den Kanal).
FEHLER_API = ("❌ Die Regelsuche ist gerade nicht erreichbar - bitte in ein paar "
              "Minuten erneut versuchen.")
FEHLER_RUNDEN_CAP = ("❌ Die Frage brauchte mehr Nachschlage-Runden, als ich mir "
                     "erlaube - bitte enger stellen (z. B. einen konkreten Zauber "
                     "oder eine Regel nennen).")
FEHLER_MAX_TOKENS = ("⚠️ Die Antwort wurde laenger als mein Limit und ist abgeschnitten "
                     "- bitte die Frage in kleinere Teile aufteilen.")
FEHLER_REFUSAL = "🚫 Diese Anfrage beantworte ich nicht."
HINWEIS_VERGESSEN = ("⚠️ Ich habe den bisherigen Verlauf nach einem Neustart vergessen - "
                     "stell die Frage bitte noch einmal im Ganzen.")
# Ephemere Antworten koennen keinen Thread tragen (Discord-Grenze) - das sagt der Bot
# dazu, statt die fehlende Nachfrage-Moeglichkeit unerklaert zu lassen.
HINWEIS_PRIVAT = ("ℹ️ Diese Antwort sieht nur du - deshalb gibt es hier keinen Thread "
                  "fuer Nachfragen. Fuer ein Gespraech dieselbe Frage mit `/regel` "
                  "stellen.")
# Kontextmenue auf einer Nachricht ohne Text (nur Bild/Anhang/Embed).
HINWEIS_KEIN_TEXT = ("🚫 Diese Nachricht enthaelt keinen Text, den ich als Regelfrage "
                     "pruefen koennte.")
# Kontextmenue auf einer Bot-Nachricht: eine ganze Bot-Antwort als "Frage" waere nur
# ein teurer Selbstbezug.
HINWEIS_BOT_NACHRICHT = ("🚫 Bot-Nachrichten pruefe ich nicht - fuer Nachfragen einfach "
                         "im Thread antworten oder `/regel` nutzen.")
# Statischer /hilfe-Text: die Wege zum Bot stehen sonst nur im Code und auf der
# Website - ein Mitspieler in Discord sieht keinen davon. Ephemer und ohne API-Kosten.
HILFE = (
    "**So fragst du Foliant**\n"
    "- `/regel` - Regelfrage stellen; die Antwort steht im Kanal und oeffnet einen "
    "Thread fuer Nachfragen. Optional `fassung` waehlen (Standard: 2024).\n"
    "- `/regel-privat` - dieselbe Frage, aber die Antwort siehst nur du; dafuer ohne "
    "Thread fuer Nachfragen.\n"
    "- `@Foliant <Frage>` in einer normalen Nachricht - die Antwort landet in einem "
    "Thread unter deiner Frage.\n"
    "- In einem Foliant-Thread einfach weiterschreiben - Nachfragen brauchen keine "
    "Erwaehnung.\n"
    "- Rechtsklick auf eine Nachricht → Apps → **Foliant fragen** prueft deren "
    "Aussage als Regelfrage.\n"
    "- `/bestand` - welche Buecher im Bestand stehen, mit Sprache und Regelstand. "
    "Zeigt nur dir und kostet nichts.\n\n"
    "**War eine Antwort falsch?** Reagiere mit 👎 darauf. Foliant merkt sich die Frage "
    "als Korrektur-Kandidat (📝 heisst: notiert) - so wird der Bestand genau dort besser, "
    "wo er heute daneben liegt. Reaktion wieder wegnehmen loescht den Eintrag.\n\n"
    "Foliant antwortet nur aus dem Regelbestand der Runde, nennt immer Quelle und "
    "Regelversion und verraet nichts aus Abenteuern (Spoiler-Schutz)."
)


def fehlertext(stop_grund: str) -> str | None:
    """Nutzerfreundlicher Text zu einem nicht-normalen Schleifenende; None = normal."""
    return {"runden_cap": FEHLER_RUNDEN_CAP, "max_tokens": FEHLER_MAX_TOKENS,
            "refusal": FEHLER_REFUSAL}.get(stop_grund)


def thread_titel(frage: str) -> str:
    """Discord erlaubt max. 100 Zeichen; Whitespace kollabieren, hart kappen."""
    sauber = " ".join(frage.split()) or "Regelfrage"
    if len(sauber) <= THREAD_TITEL_LIMIT:
        return sauber
    return sauber[:THREAD_TITEL_LIMIT - 1] + "…"


def _zaun_zeile(zeile: str) -> bool:
    return zeile.lstrip().startswith("```")


def _absaetze_mit_belegbindung(text: str) -> list[str]:
    """Absaetze (\n\n-getrennt); eine Belegzeile (📖) wird an ihren Vorgaenger-Absatz
    gebunden - sie darf nie als Waise am Anfang einer Folge-Nachricht stehen."""
    absaetze: list[str] = []
    for absatz in text.split("\n\n"):
        if absaetze and absatz.lstrip().startswith("📖"):
            absaetze[-1] = f"{absaetze[-1]}\n\n{absatz}"
        else:
            absaetze.append(absatz)
    return absaetze


def _harte_stuecke(block: str, limit: int) -> list[str]:
    """Ein einzelner Ueberlaenge-Block: erst an Zeilen trennen, notfalls hart schneiden."""
    stuecke: list[str] = []
    aktuell = ""
    for zeile in block.split("\n"):
        while len(zeile) > limit:            # pathologisch lange Einzelzeile
            stuecke.append(zeile[:limit])
            zeile = zeile[limit:]
        if aktuell and len(aktuell) + 1 + len(zeile) > limit:
            stuecke.append(aktuell)
            aktuell = zeile
        else:
            aktuell = f"{aktuell}\n{zeile}" if aktuell else zeile
    if aktuell:
        stuecke.append(aktuell)
    return stuecke


def teile(text: str, limit: int = LIMIT) -> list[str]:
    """Antwort in Discord-taugliche Nachrichten schneiden.

    Regeln: bevorzugt an Absatzgrenzen; Belegzeilen (📖) wandern mit ihrem Absatz;
    Codeblock-Zaeune werden ueber Splitgrenzen geschlossen und im Folgeteil wieder
    geoeffnet (Statbloecke kommen laut Discord-Zusatzprompt als Codeblock - eine offene
    Splitgrenze wuerde den Rest der Nachricht als Code rendern)."""
    text = text.strip()
    if not text:
        return []

    bloecke: list[str] = []
    for absatz in _absaetze_mit_belegbindung(text):
        if len(absatz) > limit:
            bloecke.extend(_harte_stuecke(absatz, limit))
        else:
            bloecke.append(absatz)

    nachrichten: list[str] = []
    aktuell = ""
    zaun_offen: str | None = None            # die oeffnende Zaunzeile (z. B. ```text)
    for block in bloecke:
        kandidat = f"{aktuell}\n\n{block}" if aktuell else block
        if aktuell and len(kandidat) > limit:
            if zaun_offen:
                aktuell += "\n```"
            nachrichten.append(aktuell)
            aktuell = f"{zaun_offen}\n{block}" if zaun_offen else block
        else:
            aktuell = kandidat
        for zeile in block.split("\n"):      # Zaun-Zustand nach diesem Block
            if _zaun_zeile(zeile):
                zaun_offen = None if zaun_offen else zeile.strip()
    if aktuell:
        nachrichten.append(aktuell)
    return _belege_anheften(nachrichten, limit)


def _belege_anheften(nachrichten: list[str], limit: int) -> list[str]:
    """Nachlauf gegen den Restfall des harten Splits: passt Inhalt+Beleg zusammen nicht
    in eine Nachricht, landete die Belegzeile allein am Anfang der naechsten. Dann
    wandert die letzte Zeile des Vorgaengers mit zu ihr - der Beleg steht wieder unter
    Inhalt. Zeilen mit Zaunmarken werden nie bewegt (wuerde die Balance kippen)."""
    for i in range(1, len(nachrichten)):
        if not nachrichten[i].lstrip().startswith("📖"):
            continue
        # Trailing-Leerzeilen zuerst weg, sonst 'wandert' nur ein leeres Segment
        # (der Vorgaenger endete nach dem Zeilen-Split real mit '\n').
        vorher = nachrichten[i - 1].rstrip()
        kopf, trenner, letzte = vorher.rpartition("\n")
        beleg = nachrichten[i].lstrip()
        if (kopf and trenner and letzte.strip() and "```" not in letzte
                and len(letzte) + 1 + len(beleg) <= limit):
            nachrichten[i - 1] = kopf
            nachrichten[i] = f"{letzte}\n{beleg}"
    return nachrichten
