"""Rückmeldungen der Runde: eine 👎-Reaktion auf eine Bot-Antwort wird ein
Kurations-Kandidat (O4/M5).

WOFUER: Die Feedback-Schleife lief bisher nur ueber Statistik - `admin suchbericht` sieht
Nulltreffer, Fuzzy-Landungen und Mehrdeutigkeiten. Was er NICHT sieht, ist die Antwort, die
technisch gefunden hat und trotzdem falsch war. Genau die erkennen aber die Spieler, sofort,
am Tisch - und hatten dafuer keinen Weg ausser "David sagen". Eine Reaktion ist der
kuerzeste denkbare Meldeweg: kein Befehl, keine API-Kosten, kein neuer State im Bot.

DER SCHNITT: Diese Datei ist discord-frei und arbeitet auf (ist_bot, inhalt)-Paaren wie
rebuild.py - damit vollstaendig ohne Discord testbar. Das Uebersetzen echter Reaktionen in
diese Paare macht bot.py, der duenne Kleber.

WAS PROTOKOLLIERT WIRD - und was bewusst nicht: Gespeichert werden die FRAGE (dieselbe
Datenklasse wie `suchbegriff`, den die Tools seit jeher loggen) und ein Nachrichten-LINK.
NICHT der Antworttext: das waere Gespraechsinhalt in einer Log-Datei, und der Link fuehrt in
einem Klick dorthin, wo die Antwort ohnehin steht. Keine Nutzerkennung - wer markiert hat,
ist fuer die Kuration ohne Bedeutung, und die Markierung soll kein Sozialprotokoll werden
(CONCEPT.md par. 13). Deshalb zaehlt auch nicht, WIE OFT markiert wurde: eine Antwort ist
markiert oder nicht.
"""
from __future__ import annotations

# Die eine Markierung. Bewusst nur eine: Zwei Emoji mit feinen Bedeutungsunterschieden
# muesste man erklaeren, und ein Meldeweg, den man erklaeren muss, wird nicht benutzt.
MARKIERUNG = "\N{THUMBS DOWN SIGN}"

# Was der Bot zurueckreagiert - "notiert", ohne eine Nachricht in den Kanal zu schreiben.
# Ohne diese Rueckmeldung weiss niemand, ob der Druck auf den Daumen etwas bewirkt hat,
# und ein Knopf ohne sichtbare Wirkung gilt nach zweimal als kaputt.
BESTAETIGUNG = "\N{MEMO}"

# Die Art, unter der die Zeile im Protokoll steht. Ein Feld (statt einer Tabelle je Art),
# damit eine spaetere zweite Markierung keine Migration braucht.
ART = "daumen_runter"


def ist_markierung(emoji: str) -> bool:
    """Nur die eine Markierung zaehlt - jede andere Reaktion ist Geplauder.

    Verglichen wird auf dem nackten Zeichen: Discord liefert dasselbe Emoji je Client mit
    oder ohne Variantenselektor (U+FE0F), und ein direkter Stringvergleich haette den
    Daumen von manchen Geraeten stillschweigend nicht erkannt."""
    return emoji.replace("\N{VARIATION SELECTOR-16}", "") == MARKIERUNG


def frage_aus_umgebung(vorlauf: list[tuple[bool, str]],
                       thread_titel: str | None = None) -> str | None:
    """Die Frage, auf die die markierte Antwort geantwortet hat.

    `vorlauf` sind die Nachrichten VOR der markierten, chronologisch, als
    (ist_bot, inhalt). Genommen wird die letzte menschliche - bei einer Folgefrage im
    Thread ist das genau die gestellte Frage, nicht die urspruengliche.

    Faellt das aus, greift der Thread-TITEL: Bei `/regel` steht die Frage nirgends im
    Kanal (Slash-Parameter), der Titel ist dort die einzige Spur - derselbe Grund wie fuer
    `rebuild.baue_verlauf(ersatzfrage=...)`.

    None ist ein zulaessiges Ergebnis und kein Grund, die Markierung zu verwerfen: der
    Link im Protokoll fuehrt trotzdem zur Antwort, und eine Markierung ohne Frage ist
    immer noch ein Befund. Sie zu verwerfen hiesse, ein Signal wegzuwerfen, weil ein
    Komfortfeld leer bleibt."""
    for ist_bot, inhalt in reversed(vorlauf):
        if ist_bot:
            continue
        text = (inhalt or "").strip()
        if text:
            return text
    titel = (thread_titel or "").strip()
    return titel or None


def verweis(guild_id: int, kanal_id: int, nachricht_id: int) -> str:
    """Ein anklickbarer Discord-Link auf die markierte Antwort.

    Der Link ist der Grund, warum der Antworttext nicht ins Protokoll muss: Beim Sichten
    des Berichts fuehrt ein Klick zur echten Nachricht - mit Thread, Nachfragen und dem
    Gesicht, das der Fragende danach gemacht hat. Ein abgeschriebener Auszug im Log haette
    weniger Kontext und mehr Inhalt."""
    return f"https://discord.com/channels/{guild_id}/{kanal_id}/{nachricht_id}"
