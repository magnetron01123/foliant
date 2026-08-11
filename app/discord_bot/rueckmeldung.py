"""Rückmeldungen der Runde: eine 👎- oder 👍-Reaktion auf eine Bot-Antwort wird ein
Kurations- bzw. Regressionsschutz-Kandidat (O4/M5).

WOFUER: Die Feedback-Schleife lief bisher nur ueber Statistik - `admin suchbericht` sieht
Nulltreffer, Fuzzy-Landungen und Mehrdeutigkeiten. Was er NICHT sieht, ist die Antwort, die
technisch gefunden hat und trotzdem falsch war. Genau die erkennen aber die Spieler, sofort,
am Tisch - und hatten dafuer keinen Weg ausser "David sagen". Eine Reaktion ist der
kuerzeste denkbare Meldeweg: kein Befehl, keine API-Kosten, kein neuer State im Bot.

DER SCHNITT: Diese Datei ist discord-frei und arbeitet auf (ist_bot, inhalt)-Paaren wie
wiederaufbau.py - damit vollstaendig ohne Discord testbar. Das Uebersetzen echter Reaktionen in
diese Paare macht bot.py, der duenne Kleber.

WAS PROTOKOLLIERT WIRD - und was bewusst nicht: Gespeichert werden die FRAGE (dieselbe
Datenklasse wie `suchbegriff`, den die Tools seit jeher loggen) und ein Nachrichten-LINK.
NICHT der Antworttext: das waere Gespraechsinhalt in einer Log-Datei, und der Link fuehrt in
einem Klick dorthin, wo die Antwort ohnehin steht. Keine Nutzerkennung - wer markiert hat,
ist fuer die Kuration ohne Bedeutung, und die Markierung soll kein Sozialprotokoll werden
(CONCEPT.md par. 13). Deshalb zaehlt auch nicht, WIE OFT markiert wurde: eine Antwort ist
je Art markiert oder nicht. Sind sich zwei Spieler uneins (👎 UND 👍 an derselben
Antwort), stehen zwei Zeilen da - das ist keine Panne, sondern der Befund.
"""
from __future__ import annotations

# Die Arten, unter denen eine Zeile im Protokoll steht. Ein FELD (statt einer Tabelle je
# Art), wie beim Bau von 👎 vorgesehen - die zweite Markierung kam damit ohne Migration aus.
ART_RUNTER = "daumen_runter"
ART_HOCH = "daumen_hoch"
# Selbstanzeige des Bots, keine Spieler-Reaktion: siehe ablehnung_ohne_werkzeug().
ART_AUTO_ABLEHNUNG = "auto_ablehnung_ohne_werkzeug"

# Die zaehlenden Reaktionen. Bis 04.08.2026 war es bewusst nur EINE, mit der Begruendung:
# zwei Emoji mit feinen Bedeutungsunterschieden muesste man erklaeren, und ein Meldeweg,
# den man erklaeren muss, wird nicht benutzt. Diese Begruendung gilt weiter - sie trifft 👍
# nur nicht: Ihr Gegenstand ist NUANCE (👎 gegen 😕 gegen 🤔: "welches nehme ich?"), und
# 👍/👎 ist keine Nuance, sondern Polaritaet. Das eine Emoji-Paar, das in jedem Chat
# dasselbe heisst und das niemand nachschlaegt. Dazu kommt: die Runde reagiert ohnehin
# schon mit 👍 - das Signal fiel bisher nur stumm auf den Boden.
ARTEN = {"\N{THUMBS DOWN SIGN}": ART_RUNTER, "\N{THUMBS UP SIGN}": ART_HOCH}

# Was der Bot zurueckreagiert - "notiert", ohne eine Nachricht in den Kanal zu schreiben.
# Ohne diese Rueckmeldung weiss niemand, ob der Druck auf den Daumen etwas bewirkt hat,
# und ein Knopf ohne sichtbare Wirkung gilt nach zweimal als kaputt.
# EIN Zeichen fuer beide Arten: Die Bestaetigung beantwortet genau eine Frage - "ist mein
# Druck angekommen?" -, und die ist fuer Lob und Tadel dieselbe. WELCHE Art notiert wurde,
# steht ohnehin sichtbar an der Nachricht: der eigene Daumen. Ein zweites
# Bestaetigungs-Emoji waere genau der feine Unterschied, gegen den oben argumentiert wird.
BESTAETIGUNG = "\N{MEMO}"


# Zeichen, die den Daumen nur AUSSEHEN lassen, ihn aber nicht zu einem anderen Emoji
# machen: der Variantenselektor (Textform gegen Bildform) und die fuenf Hauttoene.
_SCHMUCK = ("\N{VARIATION SELECTOR-16}",
            *(chr(c) for c in range(0x1F3FB, 0x1F400)))  # U+1F3FB..U+1F3FF


def art_der_markierung(emoji: str) -> str | None:
    """Die Art der Rueckmeldung - oder None, wenn die Reaktion Geplauder ist.

    Verglichen wird auf dem NACKTEN Zeichen. Discord liefert denselben Daumen je nach
    Client und Profil unterschiedlich geschmueckt, und ein direkter Stringvergleich hat
    beide Formen stillschweigend verworfen:

    - Variantenselektor U+FE0F (Textform/Bildform) - iOS schickt 👍 praktisch immer damit.
    - Hauttoene U+1F3FB..U+1F3FF (Review-Befund 11.08.2026, am lebenden Bot gemessen):
      Wer den Ton einmal eingestellt hat, sendet auf iOS und Android IMMER 👍🏽 statt 👍.
      Fuer den bekam die Runde weder eine Zeile im Protokoll noch die 📝-Quittung - der
      einzige Eingang der Feedback-Schleife war fuer einen sehr haeufigen Fall zu.

    Der Hautton ist kein Bedeutungsunterschied: 👍🏽 heisst dasselbe wie 👍. Ihn zu
    speichern hiesse ausserdem, ein personenbezogenes Merkmal zu protokollieren
    (CONCEPT.md par. 13) - er wird deshalb weggeworfen, nicht ausgewertet."""
    nackt = emoji
    for zeichen in _SCHMUCK:
        nackt = nackt.replace(zeichen, "")
    return ARTEN.get(nackt)


def frage_aus_umgebung(vorlauf: list[tuple[bool, str]],
                       thread_titel: str | None = None) -> str | None:
    """Die Frage, auf die die markierte Antwort geantwortet hat.

    `vorlauf` sind die Nachrichten VOR der markierten, chronologisch, als
    (ist_bot, inhalt). Genommen wird die letzte menschliche - bei einer Folgefrage im
    Thread ist das genau die gestellte Frage, nicht die urspruengliche.

    Faellt das aus, greift der Thread-TITEL: Bei `/regel` steht die Frage nirgends im
    Kanal (Slash-Parameter), der Titel ist dort die einzige Spur - derselbe Grund wie fuer
    `wiederaufbau.baue_verlauf(ersatzfrage=...)`.

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


class Fragenspeicher:
    """Welche Frage eine gesendete Antwort beantwortet hat - nachricht_id -> Frage.

    Warum es das braucht (Durchgang 11.08.2026): `frage_aus_umgebung` rekonstruiert die
    Frage im Moment der REAKTION aus der Kanal-Historie. Das ging bei 4 von 6
    Rueckmeldungen schief - einmal landete ein GIF-Link im Protokoll, einmal eine zwei
    Tage alte Frage zu einem anderen Thema, zweimal blieb es leer. Kein Wunder: Bei
    `/regel` steht die Frage als Slash-Parameter NIRGENDS im Kanal, und zwischen Frage und
    Antwort liegen im Spiel schnell sechs Wuerfelwuerfe eines anderen Bots.

    Der Bot kennt die Frage aber, waehrend er antwortet. Hier gemerkt, ist die Zuordnung
    exakt statt geraten.

    FLUECHTIG und BEGRENZT, mit Absicht:
    - Im Speicher, nicht auf der Platte: Es ist ein Komfortfeld, keine Buchfuehrung. Nach
      einem Neustart greift `frage_aus_umgebung` weiter - deshalb bleibt der alte Weg als
      Rueckfallebene bestehen und wird nicht ersetzt.
    - Deckel gegen unbegrenztes Wachstum; die aeltesten fallen zuerst. Markiert wird
      erfahrungsgemaess binnen Minuten, nicht nach tausend Antworten.
    - Gespeichert wird NUR die Frage, die ohnehin ins Protokoll darf (CONCEPT.md par. 13),
      nie der Antworttext. Das ist strenger als vorher: Bisher konnte jede beliebige
      Kanal-Nachricht als 'Frage' im Log landen."""

    def __init__(self, deckel: int = 500) -> None:
        self._deckel = deckel
        self._fragen: dict[int, str] = {}

    def merke(self, nachricht_id: int, frage: str) -> None:
        if not (frage or "").strip():
            return
        self._fragen.pop(nachricht_id, None)     # ans Ende, damit der Deckel FIFO bleibt
        self._fragen[nachricht_id] = frage
        while len(self._fragen) > self._deckel:
            self._fragen.pop(next(iter(self._fragen)))

    def frage(self, nachricht_id: int) -> str | None:
        return self._fragen.get(nachricht_id)


def noch_markiert(reaktionen: list[tuple[str, int]], art: str) -> bool:
    """Haelt nach einer Ruecknahme noch jemand dieselbe Art an dieser Antwort?

    `reaktionen` sind (Emoji, Anzahl)-Paare der Nachricht, frisch geladen - also OHNE den,
    der eben zurueckgenommen hat.

    Review-Befund 11.08.2026: `loesche_rueckmeldung` loeschte bedingungslos. Weil
    UNIQUE(art, verweis) bewusst ohne Nutzerkennung entdoppelt, ergeben zwei Spieler mit 👎
    an derselben Antwort EINE Zeile - und nahm einer zurueck, verschwand der Befund, obwohl
    der andere ihn weiter markierte. Ausgerechnet die wertvollste Zeilensorte, still.

    Die Anzahl reicht dafuer und bleibt PII-frei: Sie sagt, DASS noch jemand markiert, nie
    wer. Genau die Grenze, an der die 📝-Quittung stehen bleibt - die wegzunehmen hiesse
    zu wissen, ob niemand mehr markiert, und das weiss nur diese Zahl, nicht der Bot."""
    return any(anzahl > 0 and art_der_markierung(emoji) == art
               for emoji, anzahl in reaktionen)


def verweis(guild_id: int, kanal_id: int, nachricht_id: int) -> str:
    """Ein anklickbarer Discord-Link auf die markierte Antwort.

    Der Link ist der Grund, warum der Antworttext nicht ins Protokoll muss: Beim Sichten
    des Berichts fuehrt ein Klick zur echten Nachricht - mit Thread, Nachfragen und dem
    Gesicht, das der Fragende danach gemacht hat. Ein abgeschriebener Auszug im Log haette
    weniger Kontext und mehr Inhalt."""
    return f"https://discord.com/channels/{guild_id}/{kanal_id}/{nachricht_id}"


def ablehnung_ohne_werkzeug(text: str, tool_namen: list[str]) -> bool:
    """Traegt eine fertige Antwort einen Ablehnungs-/Leerbefund-Marker, obwohl KEIN
    Werkzeug gerufen wurde?

    Discord-Befund 08.08.2026: Auf das nackte Wort 'verstecken' kam eine
    🚫-Spoiler-Ablehnung - ohne einen einzigen Werkzeugaufruf (Repro am Pi: 1 von 4
    Laeufen). Beide Prompt-Kanaele verbieten das seither ausdruecklich ('nie 🚫 ohne
    Werkzeugaufruf'; ein ❌ rechtfertigt ohnehin nur eine gueltige Anfrage ohne Treffer).
    Eine solche Antwort ist also per Definition regelwidrig - und zugleich die einzige
    Fehlerklasse, die das Abfrage-Protokoll strukturell NICHT sieht: protokolliere()
    haengt an den Werkzeugen, und genau die liefen nie. Deshalb meldet der Bot sie
    selbst als Kurations-Kandidat (O4/M5), statt auf ein 👎 der Runde zu warten."""
    return not tool_namen and ("\N{NO ENTRY SIGN}" in text or "\N{CROSS MARK}" in text)


def auto_verweis(frage: str) -> str:
    """Idempotenz-Schluessel der Selbstanzeige: je Frage EIN Befund, egal wie oft der
    Fehlalarm auftritt - dieselbe Entscheidung wie bei den Daumen (zweite Markierung
    derselben Sache ist derselbe Befund). Kein Nachrichten-Link: Die Erkennung faellt
    VOR dem Senden, eine Message-ID gibt es noch nicht."""
    return "auto:" + " ".join(frage.split()).lower()[:120]
