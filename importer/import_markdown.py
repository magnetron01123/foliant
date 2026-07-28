"""Markdown -> Chunks in `eintraege`. Version ist PFLICHT (V1/Q3): kein Eintrag ohne
edition + Quelle. Quelle vorab in `quellen` anlegen (mit prioritaet für Q2).

Chunking (wichtigster Qualitaetshebel, Leitplanke): EIN logischer Eintrag pro Zeile,
heading-basiert getrennt. Die Split-Tiefe und Kategorie haengen vom KAPITEL ab
(SPLIT_REGELN je Quelle, an echten PDFs justiert - dt. SRD 5.2.1: Zauber/Zustaende/
Gegenstaende/Talente/Hintergruende sind H6, Monster H3/H4, Regeln H3-H5). Eltern-Headings
wandern als markierte Kontextzeile in den Body; Seitenmarker `<!-- seite:N -->` aus dem
PDF-Konverter werden ausgewertet und entfernt (F7).

PDF-Artefakt-Reparatur (dt. SRD, siehe bekannte_macken): Buchstaben mit Unterlaengen (g/p)
reissen aus Woertern und landen als eigenes `<u>g</u>`-Fragment am Zeilenende
('Zauber rad **<u>g</u>**' = 'Zaubergrad'). _repariere_fragmente setzt sie zurueck und
verifiziert das Ergebnis gegen den Dokumentbestand. <mark>-Headings sind Wertekaesten
(Statbloecke) -> kategorie 'monster'.

LABEL-PSEUDO-HEADINGS (Review-Fund 10.07.2026, siehe bekannte_macken): PyMuPDF4LLM macht
aus fettgedruckten Inline-Labels mitten im Eintrag teils Headings ('### **Kreaturentyp:**
Humanoide', '### **Reichweite:** 9 Meter') -> zerriss Spezies (Elf/Gnom/Halbling/Mensch
verloren ihren Eintrag) und ~110 Zauber. Erkennung: der ERSTE Fettblock des Headings endet
mit ':' -> Fortsetzungszeile, kein Eintragsbeginn. Echte Namen mit Doppelpunkt MITTEN im
Fettblock ('**Kämpfer-Unterklasse: Champion**', '**Schritt 1: Klasse auswählen**') bleiben
Headings.

MERGE_REGELN (Spezies-Kapitel): Tabellen-Kaesten ('Drakonische Ahnen', 'Unholdisches Erbe')
liegen im dt. SRD auf DERSELBEN Heading-Ebene wie die Speziesnamen und lassen sich nicht
per Split-Level trennen. Kapitel-Regel: eigenstaendig ist nur, was mit dem Struktur-Signal
'**Kreaturentyp:**' beginnt (jede Spezies-Beschreibung tut das); alles andere wird an den
vorherigen Eintrag des Kapitels angehaengt.

RE-IMPORT IDEMPOTENT UND VERLUSTSICHER (A7): Das Markdown wird VOLLSTAENDIG geparst,
BEVOR irgendetwas geloescht wird. Null Chunks oder ein unplausibler Schrumpf (unter
SCHRUMPF_SCHWELLE des Altbestands, ohne erlaube_schrumpfen) brechen ab - der alte
Bestand bleibt unangetastet. Die Funktion committet NICHT selbst: der AUFRUFER fuehrt
die Transaktion (z. B. `with con: importiere_markdown(...)`), damit Loeschen, Einfuegen
und FTS-Rebuild atomar zusammen landen oder zusammen zurueckrollen."""
from __future__ import annotations

import re
import sqlite3
import unicodedata

from importer import schwellen as _schwellen

SPLIT_STANDARD = 3       # ohne Quell-Regeln: Headings 1..3 eroeffnen neue Eintraege
# Kapitel-Koepfe, die selbst NIE ein Eintrag sind (claude DND-010: das 22-kB-Inhalts-
# verzeichnis stand als 'regel' im Bestand - die Kontext-Skip-Regel erfasst nur die
# KINDER eines Kapitels, nicht den Kopf). Muster auf den Eintragsnamen, je Quelle.
SKIP_NAMEN: dict[str, "re.Pattern[str]"] = {
    "srd-de": re.compile(r"^Verzeichnis der Wertekästen$"),
    # 2014-Scans: am Buchende versagt die Heading-Erkennung, der letzte Abschnitt
    # sammelt alles bis zum Dokumentende ein (im PHB 130 kB: Leseliste + Register).
    # Reiner Ballast im Volltextindex - der Regelinhalt der Baende steht davor.
    "phb-2014-de": re.compile(r"^ANHANG E\b|^INHALTSVERZEICHNIS$"),
    "xgte-2014-de": re.compile(r"^INHALTSVERZEICHNIS$"),
    "scag-2014-de": re.compile(r"^INHALT$"),
}
_MIN_BODY = 1            # leere Abschnitte (reine Kapitel-Deckblaetter) ueberspringen
# Die Plausibilitaets-Schwellen liegen seit Phase 4 gesammelt in importer/schwellen.py
# (Befund D3). Der Name bleibt hier als Re-Export, weil import_open5e ihn von hier holt.
SCHRUMPF_SCHWELLE = _schwellen.SCHRUMPF_SCHWELLE


class Importbilanz:
    """Was ein Import STILL verwirft oder nicht repariert - gezaehlt statt verschwiegen.

    Befund D1: An mindestens 14 Stellen wurde Inhalt verworfen oder eine Reparatur
    uebersprungen, ohne Zaehler und ohne Meldung. Genau dieses Muster erzeugte die 46
    Eintraege namens 'Zeitaufwand: 1 Aktion', die erst Wochen spaeter per Handabfrage
    auffielen. Verwerfungs-Reports gab es nur bei den vier Bruecken-Modulen - deren Form
    ist hier das Vorbild: EINE Bilanzzeile am Ende, Details nur, wenn es etwas zu sagen
    gibt.

    Der eigentliche Zweck sind nicht die Zahlen an sich, sondern ihre VERAENDERUNG: ein
    PDF-Update, das einen Reparatur-Anker verschiebt, macht die Reparatur lautlos wirkungs-
    los. In der Bilanz steht sie dann als 'nicht gegriffen'."""

    def __init__(self) -> None:
        self.verworfen: dict[str, int] = {}
        self.wirkungslos: list[str] = []

    def verwirf(self, grund: str, anzahl: int = 1) -> None:
        if anzahl:
            self.verworfen[grund] = self.verworfen.get(grund, 0) + anzahl

    def greift_nicht(self, was: str) -> None:
        """Eine kuratierte Reparatur hat ihren Anker nicht gefunden - sie ist damit
        wirkungslos, ohne dass irgendwo ein Fehler entstuende."""
        self.wirkungslos.append(was)

    @property
    def auffaellig(self) -> bool:
        return bool(self.wirkungslos)

    def zeile(self) -> str:
        teile = [f"{n}x {grund}" for grund, n in sorted(self.verworfen.items())]
        text = "Bilanz: " + (", ".join(teile) if teile else "nichts verworfen")
        if self.wirkungslos:
            # Bewusst die vollstaendige Liste, nicht nur die Zahl: welche Reparatur
            # ausgefallen ist, entscheidet, ob es harmlos ist oder das Buch zerreisst.
            text += (f" | {len(self.wirkungslos)} Reparatur(en) ohne Anker - WIRKUNGSLOS: "
                     + ", ".join(self.wirkungslos))
        return text


_BILANZ = Importbilanz()


def letzte_bilanz() -> Importbilanz:
    """Die Bilanz des zuletzt gelaufenen Imports (Tests/Aufrufer)."""
    return _BILANZ

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
# Label-Pseudo-Heading: erster Fettblock endet mit ':' ('**Kreaturentyp:** Humanoide',
# '**_Riesische Abstammung:_** Du stammst von'). re.match ankert am Anfang; Doppelpunkte
# mitten im Fettblock ('**Schritt 1: Klasse auswählen**') matchen NICHT.
_LABEL_HEADING = re.compile(r"\*\*_?[^*\n]*?:_?\*\*")
# Dasselbe Symptom OHNE Fettschrift: die 2014-Scans setzen den Zauberkopf als blanke
# Ueberschrift ('###### Zeitaufwand: 1 Aktion'), weshalb _LABEL_HEADING nicht greift und
# die Metazeile zum Eintragsnamen wurde (46 Faelle in phb-2014-de, 27.07.2026). Bewusst
# eng auf die Zauberkopf-Schluesselwoerter begrenzt statt auf 'Wort:' allgemein - sonst
# verloeren echte Ueberschriften wie 'KAPITEL 3: KLASSEN' ihren Eintragsstatus. Am
# Bestand geprueft: kein Eintrag ausserhalb der 2014-Scans traegt so einen Namen.
KOPF_HEADING = re.compile(
    r"^(?:Zeitaufwand|Reichweite|Komponenten|Wirkungsdauer"
    r"|Casting Time|Range|Components|Duration)\s*:", re.IGNORECASE)
_SEITE = re.compile(r"<!--\s*seite:(\S+)\s*-->")
_FRAGMENT = re.compile(
    r"\s*\*{0,2}(?:<(?:u|mark)>)+([a-zäöüß](?: [a-zäöüß])*)(?:</(?:u|mark)>)+\*{0,2}")
_TAGS = re.compile(r"</?(?:mark|u)>")
_LUECKE = re.compile(r"([A-Za-zÄÖÜäöüß]) ([a-zäöüß])")

# Split-Regeln je Quelle: (Kontextpfad-Regex, Split-Level, Kategorie). Erste passende Regel
# gewinnt; Kategorie None = Abschnitt ueberspringen (z. B. Verzeichnisse). Kontextpfad =
# " > ".join(Eltern-Headings). An der echten Struktur des dt. SRD 5.2.1 justiert (10.07.2026).
SPLIT_REGELN: dict[str, list[tuple[str, int, str | None]]] = {
    "srd-de": [
        (r"^Verzeichnis der Wertekästen", 2, None),   # reines Inhaltsverzeichnis
        (r"^(Monster von A–Z|Tiere)\b", 4, "monster"),
        (r"^Regelglossar", 6, "regel"),               # Zustaende & Regeldefinitionen (H6!)
        (r"^Magische Gegenstände", 6, "gegenstand"),
        (r"^Ausrüstung", 6, "gegenstand"),
        (r"^Zauber\b", 6, "zauber"),
        (r"^Klassen", 5, "klasse"),                   # Klassen H3, Unterklassen H5
        (r"^Charakterherkunft.*Charakterspezies", 6, "spezies"),
        (r"^Charakterherkunft.*Charakterhintergründe", 6, "hintergrund"),
        (r"^Talente", 6, "talent"),
        (r"", 5, "regel"),                            # Spielregeln, Werkzeugkasten, ...
    ],
    # Deutsche 2014-Scans (PHB/Xanathar/SCAG): pymupdf4llm vergibt die Heading-Ebenen
    # relativ zur Schriftgroessen-Verteilung des GESAMTDOKUMENTS. In diesen Scans
    # besetzen die Kapitel-Titelseiten H1-H5, der komplette Inhalt liegt auf H6 -
    # mit dem Standard-Level 3 entstanden drei Riesen-Chunks von je ~300-500 kB
    # ('KAPITEL 1', 'KAPITEL 2'), in denen die Suche nichts findet (Befund 27.07.2026).
    # Level 6 trifft die Eintragsebene: ~840-1520 Zeichen im Schnitt.
    # Kategorie bewusst durchgehend 'regel': die Baende dienen als deutsche
    # BEGRIFFSQUELLE (S7/S8), nicht als strukturierter Zauber-/Monsterkatalog - eine
    # feinere Zuordnung waere an den OCR-verstuemmelten Kapitelnamen ('ANPASSUNOS-
    # MOEGLICHKEITEN') geraten, und geraten wird hier nichts.
    "phb-2014-de": [(r"", 6, "regel")],
    "xgte-2014-de": [(r"", 6, "regel")],
    "scag-2014-de": [(r"", 6, "regel")],
}





def _verschiebe(md: str, start_re: str, ende_re: str, ziel_re: str,
                ziel_naechstes_re: str | None = None) -> str:
    """Bewegt den Block [start..ende) VOR die Zielstelle - das Werkzeug fuer die
    Spalten-Verschraenkungen des srd-de-Drucks (SYN-P0-004: Zauber-/Regelabschnitte,
    deren Fortsetzung hinter einem FREMDEN Eintrag gelandet ist). ende_re wird ab dem
    Blockanfang gesucht (exklusive); ziel_naechstes_re verschiebt hinter die Zielstelle
    ("ans Ende des Eintrags X" = vor dessen naechstes Heading). DEFENSIV: fehlt ein
    Anker, bleibt der Text unveraendert - lieber unrepariert als falsch zerschnitten."""
    def ohne_wirkung(anker: str) -> str:
        # D1: Fehlt ein Anker, passiert die Reparatur lautlos NICHT. Ein PDF-Update
        # deaktiviert damit stillschweigend einen kuratierten Fix - genau deshalb wird
        # es gezaehlt statt verschwiegen.
        _BILANZ.greift_nicht(f"_verschiebe({anker[:40]})")
        return md

    m_start = re.search(start_re, md)
    if not m_start:
        return ohne_wirkung(start_re)
    m_ende = re.search(ende_re, md[m_start.end():])
    if not m_ende:
        return ohne_wirkung(ende_re)
    ende = m_start.end() + m_ende.start()
    block, rest = md[m_start.start():ende], md[:m_start.start()] + md[ende:]
    m_ziel = re.search(ziel_re, rest)
    if not m_ziel:
        return ohne_wirkung(ziel_re)
    einfuege = m_ziel.start()
    if ziel_naechstes_re:
        m_next = re.search(ziel_naechstes_re, rest[m_ziel.end():])
        if not m_next:
            return ohne_wirkung(ziel_naechstes_re)
        einfuege = m_ziel.end() + m_next.start()
    return rest[:einfuege] + block.strip() + "\n\n" + rest[einfuege:].lstrip("\n")


# Silbentrennungs-Risse des Drucks: NON-BREAKING HYPHEN (U+2011) + Blank mitten im Wort
# ('Geschick‑ lichkeitswurf', 273 Eintraege - claude DND-005). Legitime deutsche
# Ergaenzungsstriche ('Vor‑ oder Nachteile') schuetzt der Konjunktions-Lookahead; als
# zweite Leitplanke wird nur gekittet, wenn das zusammengesetzte Wort im Dokument belegt
# ist (dieselbe Vokabular-Leitplanke, mit der Druck-PDFs ihre Glyphenfugen-Risse heilen).
_WORTRISS = re.compile(
    r"([A-Za-zÄÖÜäöüß]{2,})‑ (?!und\b|oder\b|bzw\b|sowie\b|noch\b|als\b)([a-zäöüß]{2,})")


def _srd_de_wortrisse(markdown: str) -> str:
    vokabular = {w.lower() for w in re.findall(r"[A-Za-zÄÖÜäöüß]{4,}", markdown)}

    def kitte(m: re.Match) -> str:
        zusammen = m.group(1) + m.group(2)
        return zusammen if zusammen.lower() in vokabular else m.group(0)

    vorher = None
    while vorher != markdown:                 # Mehrfachrisse im selben Wort
        vorher = markdown
        markdown = _WORTRISS.sub(kitte, markdown)
    return markdown


def _srd_de_reparatur(markdown: str) -> str:
    """Kuratierte Strukturreparaturen des dt. SRD 5.2.1 (Review-/Synthese-Funde
    2026-07-12, alle am gerenderten PDF bzw. am englischen SRD 5.2 gegengeprueft).
    Zwei Schadensklassen des Zwei-Spalten-Drucks: (a) VERLORENE/VERTAUSCHTE Headings
    (Umstoßen klebte in 'Zweihändig', Vampirbrut-Karte ohne Heading, 'Weitreichend'
    unter falschem Namen), (b) SPALTEN-VERSCHRAENKUNG (Eissturm/Symbol/Windwall/
    Göttliches Wort: Fortsetzung hinter fremdem Eintrag; Beeinflussen-Teilabsaetze im
    Regelglossar-'Attributswurf'). Reihenfolge der Schritte ist wesentlich."""
    # (a1) Umstoßen: der Spaltenumbruch schob 'Zweihändig' + dessen Absatz ZWISCHEN
    # Umstoßen-Heading und Umstoßen-Regeltext (KON-Rettungswurf -> Liegend). Vorher
    # behauptete der Bestand, JEDE Zweihandwaffe koenne umwerfen (claude DND-001 /
    # codex DND-004, verifiziert).
    markdown = re.sub(
        r"###### \*\*Umstoßen\*\*\s*\n+###### \*\*Zweihändig\*\*\s*\n+"
        r"(Waffen mit der Eigenschaft Zweihändig[^\n]*)\n+"
        r"(Wenn du eine Kreatur mit dieser Waffe triffst, kannst du sie zu einem "
        r"Konstitutionsrettungswurf[^\n]*)",
        "###### **Umstoßen**\n\n\\2\n\n###### **Zweihändig**\n\n\\1",
        markdown, count=1)
    # (a2) 'Weitreichend' verlor sein Heading - die Definition steht unter einem
    # zweiten 'Nahkampfreichweite'-Heading in der Eigenschaftenliste.
    markdown = re.sub(
        r"###### \*\*Nahkampfreichweite\*\*\s*\n+"
        r"(Bei Waffen mit der Eigenschaft Weitreichend)",
        "###### **Weitreichend**\n\n\\1", markdown, count=1)
    # (a3) Vampirbrut: das (fragmentierte) Karten-Heading strandete VOR den
    # Pirscher-Aktionen; die echte Karte (RK 16, TP 90) beginnt headinglos bei ihrer
    # Typzeile. Heading dorthin versetzen - repariert zugleich Pirscher (Aktionen
    # kehren zu ihm zurueck) und Vampir-Vertrauter (Karte endet wieder bei sich).
    markdown = re.sub(r"#### \*\*<mark>Vam irbrut</mark>\*\* \*\*<u><mark>p</mark></u>\*\*\s*\n",
                      "", markdown, count=1)
    # Anker enthaelt die RK-16-Kopfzeile: die blosse Typzeile teilt sich die Vampirbrut
    # mit dem Todesalb (erste Reparaturfassung setzte das Heading dort ein).
    markdown = re.sub(r"(?m)^(_Kleiner oder mittelgroßer Untoter, neutral böse_\s*\n+"
                      r"\*\*RK\*\* 16\b)",
                      "#### **<mark>Vampirbrut</mark>**\n\n\\1", markdown, count=1)
    # (a5) Mehrfach-g-Fragmente in Kapitel-Headings ('Übun im Um an mit Waffen' +
    # '<u>g g g</u>'): die generische Fragment-Reparatur kittet Einzel-g's; bei 3-4 g's
    # griff ihr blinder Fallback und erzeugte 'Übungim Umgangmit ...' als EINTRAGSNAMEN.
    for kaputt, richtig in (("Ausrüstun", "Ausrüstung"), ("Waffen", "Waffen"),
                            ("Werkzeu", "Werkzeug")):
        markdown = re.sub(
            rf"##### \*\*Übun im Um an mit {kaputt}\*\* \*\*<u>g( g)+</u>\*\*\s*",
            f"##### **Übung im Umgang mit {richtig}**\n", markdown, count=1)
    # (a4) 'Schild' unter Ruestungsvertrautheit ist nur der Vertrautheits-Satz - als
    # eigener gegenstand-Eintrag verdraengte er den vollstaendigen Shield-Steckbrief
    # (codex DND-003). Zum Eltern-Eintrag 'Ruestungsvertrautheit' zusammenlegen.
    markdown = re.sub(r"###### \*\*Schild\*\*\s*\n+(Du erhältst den Vorzug Rüstungsklasse)",
                      r"**Schild:** \1", markdown, count=1)
    # (b1) Eissturm: Fortsetzung (Reichweite/Komponenten/Hagel-Text) stand hinter dem
    # kompletten 'Einswerden mit der Natur'.
    markdown = _verschiebe(
        markdown,
        r"###### \*\*Reichweite:\*\* 90 Meter\s*\n+\*\*Komponenten:\*\* V, G, M \(ein Fausthandschuh\)",
        r"\n###### \*\*", r"###### \*\*Einswerden mit der Natur\*\*")
    # (b2) Symbol: Fortsetzung (Beruehrung/Diamantpulver/Glyphen-Text) stand hinter
    # 'Strahlendes Niederstrecken' und 'Sturm der Vergeltung'.
    markdown = _verschiebe(
        markdown,
        r"###### \*\*Reichweite:\*\* Berührung\s*\n+\*\*Komponenten:\*\* V, G, M \(Diamantpulver im Wert von mindestens 1\.000 GM",
        r"\n###### \*\*", r"###### \*\*Strahlendes Niederstrecken\*\*")
    # (b3) Windwall: Typzeile + Hauptteil standen hinter 'Windwandeln'; unter dem
    # Windwall-Heading lag nur der Schluss-Satz ('Belagerungsmaschinen ...').
    markdown = _verschiebe(
        markdown,
        r"_Hervorrufungszauber 3\. Grades \(Druide, Waldläufer\)_\s*\n+\*\*Zeitaufwand:\*\* Aktion \*\*Reichweite:\*\* 36 Meter",
        r"\n###### \*\*", r"Belagerungsmaschinen geschleudert werden")
    # (b4) Göttliche Gunst / Göttliches Wort: der Schlusssatz + die Effekt-Tabelle von
    # 'Göttliches Wort' standen direkt hinter dem Gunst-Heading (Gunst = 124-Zeichen-
    # Stub mit Fremdsatz, codex DND-003). Bloecke ans Ende von 'Göttliches Wort'.
    markdown = _verschiebe(
        markdown,
        r"können sie nur mit dem Zauber _Wunsch_ auf deine aktuelle Ebene zurückkehren\.",
        r"\n_Verwandlungszauber 1\. Grades \(Paladin\)_",
        r"###### \*\*Göttliches Wort\*\*", ziel_naechstes_re=r"\n###### \*\*")
    # (b5) Beeinflussen (Aktion): 'Nicht bereitwillig'/'Zögerlich' klebten im
    # Regelglossar-Eintrag 'Attributswurf' (ein Spezial-SG 15 sah wie eine allgemeine
    # Attributswurfregel aus, codex DND-004); die Tabellen-Ueberschrift stand leer vor
    # 'Ausströmung'. Beides an die richtige Stelle.
    markdown = _verschiebe(
        markdown,
        r"\*\*_Nicht bereitwillig:_\*\* Wenn deine Beeinflussung",
        r"\n###### \*\*Attributswürfe zum Beeinflussen\*\*",
        r"\*\*_Bereitwillig:_\*\* Wenn deine Beeinflussung mit den Interessen des Monsters übereinstimmt",
        ziel_naechstes_re=r"\n\|\*\*Attributswurf\*\*\|")
    markdown = re.sub(r"###### \*\*Attributswürfe zum Beeinflussen\*\*\s*\n", "",
                      markdown, count=1)
    markdown = re.sub(r"(?m)^(\|\*\*Attributswurf\*\*\|\*\*Interaktion\*\*\|)",
                      "###### **Attributswürfe zum Beeinflussen**\n\n\\1",
                      markdown, count=1)
    return markdown


BEREINIGUNG: dict[str, list] = {
    # srd-de (SYN-P0-004/P1-010, Synthese 2026-07-12): Strukturreparaturen als Callable,
    # danach Textpolitur. Reihenfolge: Struktur zuerst (Anker enthalten Laufkopf-freie
    # Absaetze nicht zwingend), dann Laufkopf/Risse.
    "srd-de": [
        _srd_de_reparatur,
        # Laufkopf 'Systemreferenzdokument 5.2.1' + fette Seitenzahl standen in 374
        # Eintraegen MITTEN im Regeltext (das Seitenzitat kommt aus den Markern).
        r"^\*\*\d{1,3}\*\* Systemreferenzdokument 5\.2\.1\s*$",
        r"^Systemreferenzdokument 5\.2\.1\s*$",
        r"^\*\*\d{1,3}\*\*\s*$",
        # Statblock-Kopftabellen: Zellrisse mitten in Wuerfelausdruecken/Woertern
        # ('TP150 (20W1|0+40)', '**I**|**nitiative**' - claude DND-004, verifiziert).
        (r"\((\d+W\d*)\|(\d[\d+\-−]*\))", r"(\1\2)"),
        (r"\*\*([A-ZÄÖÜ][a-zäöüß]{1,14})\*\*\|\*\*([a-zäöüß]{1,12})\*\*", r"**\1\2**"),
        # Kapitaelchen-Garbles in EINTRAGSNAMEN (claude DND-009; entgegen der alten
        # Macken-Notiz nicht nur Body-Kosmetik):
        ("Ausrüstung verKAufen", "Ausrüstung verkaufen"),
        ("improvisierte wAffen", "Improvisierte Waffen"),
        ("zAubern in rüstung", "Zaubern in Rüstung"),
        ("einen wirKenden zAuber identifizieren", "Einen wirkenden Zauber identifizieren"),
        ("regeln für mAgische gegenstände", "Regeln für magische Gegenstände"),
        ("FeuerelementarHerrschaft", "Feuerelementarherrschaft"),
        ("Übungim Umgangmit", "Übung im Umgang mit"),
        _srd_de_wortrisse,
    ],
}

# Merge-Regeln je Quelle (Modul-Doku oben). Jede Regel ist ein dict mit 'kontext' (Regex auf
# den Kontextpfad des Kapitels) und EINEM Fragment-Kriterium; matcht es, haengt der Chunk
# (Name als Fettzeile) an den vorherigen Eintrag DESSELBEN Kapitels statt eigenstaendig zu
# bleiben. Level-agnostisch. Kriterien:
#   'standalone'     - Body-Start-Regex: Chunk ist EIGENSTAENDIG, wenn sein Body damit beginnt,
#                      sonst Fragment (Spezies: nur '**Kreaturentyp:**' eroeffnet eine Spezies;
#                      Tabellen-Kaesten dazwischen wandern in die Spezies zurueck).
#   'fragment_name'  - Name-Regex: Chunk ist Fragment, wenn sein NAME matcht. Fuer die
#                      Kreatur-Statblocks IN Beschwoerungszaubern ('Merkmale'/'Aktionen'/... des
#                      herbeigerufenen Wesens landeten als eigene H6-Eintraege). Diese Labels
#                      sind NIE Zaubernamen -> sicher; verschont fehl-geheadete ECHTE Zauber
#                      (Shillelagh/Windwall), deren PDF-Text nur verschoben ist (QS-Fund 11.07.).
#   'fragment_body'  - Body-Start-Regex: Chunk ist Fragment, wenn sein Body damit beginnt. '^\|'
#                      faengt Tabellen-Fragmente (Material-/Omen-/Wetter-Tabellen); ein echter
#                      Zauber beginnt IMMER mit der kursiven Typzeile, nie mit einer Tabelle.
MERGE_REGELN: dict[str, list[dict[str, str]]] = {
    "srd-de": [
        # SYN-P0-003 (Solar): vollseitige Monster kommen als H3-Abschnitt PLUS
        # gleichnamigem <mark>-Wertekasten an - zwei Chunks desselben Monsters, von
        # denen die namensbasierte Dublettenlogik einen verschluckte (Steckbrief ohne
        # RK/TP). Gleichnamige Folge-Chunks werden zu EINEM Eintrag zusammengefuehrt.
        {"kontext": r"^(Monster von A–Z|Tiere)\b", "gleicher_name_wie_vorher": "1"},
        {"kontext": r"Beschreibungen der Spezies", "standalone": r"\*\*Kreaturentyp:\*\*"},
        {"kontext": r"Beschreibungen der Zauber",
         # Statblock-Labels + Statblock-/Tabellen-Reste (RK 15, 1W8 Strahl, 'Treffer-') -
         # allesamt NIE Zaubernamen (ein Zaubername ist ein grossgeschriebenes Substantiv,
         # endet nicht auf '-' und beginnt nicht mit Kennwert/Wuerfel).
         "fragment_name": r"^(Merkmale|Aktionen|Bonusaktionen|Reaktionen|Legendäre Aktionen)$"
                          r"|^RK \d|^\d+[Ww]\d+|.*-$",
         "fragment_body": r"^\|"},
    ],
    # Quellen ohne Merge-Bedarf (native Hierarchie) tragen hier schlicht keinen Eintrag;
    # BEREINIGUNG.get(quelle) liefert dann eine leere Liste.
}

# Aus DDB-Kaufbuechern (Eberron: Forge of the Artificer; FR: Heroes of Faerun)
# abgeleitete Druck-PDF-Reparaturen liegen in einem privaten, NICHT veroeffentlichten
# Modul (privater Eigenbedarf, DDB-ToS - siehe README.md / CONCEPT.md §13). Der oeffentliche
# Code enthaelt nur die srd-de-Pipeline (CC-BY 4.0) als vollstaendiges Referenzbeispiel.
# Ist das Privatmodul lokal vorhanden, ergaenzt es SPLIT_REGELN/BEREINIGUNG um seine
# Quellen; fehlt es (oeffentliches Repo, CI), bleibt die srd-de-Pipeline voll nutzbar.
try:
    from importer import reparatur_ddb_privat as _rddb
    _rddb.registriere(SPLIT_REGELN, BEREINIGUNG)
except ImportError:
    pass


def _repariere_fragmente(markdown: str) -> str:
    """Unterlaengen-Fragmente zuruecksetzen: fuer jedes `<u>x</u>` wird der Buchstabe in
    eine Wortluecke der Zeile eingesetzt; die Kandidatenluecke gilt, wenn das entstehende
    Wort irgendwo im Dokument vorkommt (sonst: erste Klein-auf-klein-Luecke)."""
    def repariere_zeile(zeile: str) -> str:
        m = _FRAGMENT.search(zeile)
        if not m:
            return zeile
        buchstaben = m.group(1).split()
        # Fuer die Positionsarbeit tag-frei machen (Tag-Namen enthalten Buchstaben und
        # verwirren die Wortsuche); das Statblock-Signal (<mark>) bleibt als leeres
        # Marker-Tag erhalten - _chunks fragt nur "<mark> in Zeile?" ab.
        hatte_mark = "<mark>" in zeile
        rest = _TAGS.sub("", _FRAGMENT.sub("", zeile, count=1))
        for b in buchstaben:
            kandidaten = list(_LUECKE.finditer(rest))
            gewaehlt = None
            for k in kandidaten:
                # Volles Kandidatenwort bilden (Wortstuecke links/rechts der Luecke) und als
                # GANZES Wort im Dokument verifizieren - ein blanker Substring-Check griff
                # daneben ('ngd' steckt in 'Jungdrache').
                links = re.search(r"[\wÄÖÜäöüß]+$", rest[:k.start() + 1])
                rechts = re.match(r"[\wÄÖÜäöüß]+", rest[k.end() - 1:])
                wort = (links.group(0) if links else k.group(1)) + b \
                    + (rechts.group(0) if rechts else k.group(2))
                if re.search(r"\b" + re.escape(wort) + r"\b", markdown, re.IGNORECASE):
                    gewaehlt = k
                    break
            if gewaehlt is not None:
                rest = rest[:gewaehlt.start()] + gewaehlt.group(1) + b + gewaehlt.group(2) \
                    + rest[gewaehlt.end():]
                continue
            # Unterlaenge am WORTENDE ('Ankhe' + g = 'Ankheg'): ans letzte Wort anhaengen,
            # wenn das Ergebnis im Dokument existiert; sonst WORTANFANG ('eübt' + g =
            # 'geübt' - Fund 10.07.2026: 'Rettungswürfe, in denen du geübt bist'); sonst
            # erste Luecke, sonst anhaengen.
            m_wort = re.search(r"([A-Za-zÄÖÜäöüß]+)([^A-Za-zÄÖÜäöüß]*)$", rest)
            if m_wort and re.search(r"\b" + re.escape(m_wort.group(1) + b) + r"\b",
                                    markdown, re.IGNORECASE):
                rest = rest[:m_wort.end(1)] + b + rest[m_wort.end(1):]
                continue
            anfang = next((w for w in re.finditer(r"[A-Za-zÄÖÜäöüß]+", rest)
                           if re.search(r"\b" + re.escape(b + w.group(0)) + r"\b",
                                        markdown, re.IGNORECASE)), None)
            if anfang is not None:
                rest = rest[:anfang.start()] + b + rest[anfang.start():]
            elif kandidaten:
                k = kandidaten[0]
                rest = rest[:k.start()] + k.group(1) + b + k.group(2) + rest[k.end():]
            elif m_wort:
                rest = rest[:m_wort.end(1)] + b + rest[m_wort.end(1):]
        return rest + ("<mark></mark>" if hatte_mark else "")

    return "\n".join(repariere_zeile(z) if ("<u>" in z or "<mark>" in z) else z
                     for z in markdown.splitlines())


def _regel_fuer(pfad: list[str], split_regeln: list[tuple[str, int, str | None]] | None,
                kategorie_standard: str) -> tuple[int, str | None]:
    if not split_regeln:
        return SPLIT_STANDARD, kategorie_standard
    kontext = " > ".join(pfad)
    for muster, level, kategorie in split_regeln:
        if re.search(muster, kontext, re.IGNORECASE):
            return level, kategorie
    return SPLIT_STANDARD, kategorie_standard


def _ist_fragment(regel: dict, c: dict, vorher_name: str | None = None) -> bool:
    """Ob Chunk c laut Merge-Regel ein Fragment ist (an den Vorgaenger anzuhaengen).
    Kriterien schliessen sich nicht aus; das erste passende gewinnt (Modul-Doku).
    'gleicher_name_wie_vorher': Fragment, wenn der Chunk denselben (normalisierten)
    Namen traegt wie der vorherige Eintrag des Kapitels (vollseitige Monster:
    H3-Abschnitt + gleichnamiger Wertekasten, SYN-P0-003)."""
    if regel.get("gleicher_name_wie_vorher"):
        from app.glossar import norm_begriff
        return vorher_name is not None and \
            norm_begriff(c["name"]) == norm_begriff(vorher_name)
    if "standalone" in regel:
        return not re.match(regel["standalone"], c["body"])
    return bool(regel.get("fragment_name") and re.match(regel["fragment_name"], c["name"])) or \
        bool(regel.get("fragment_body") and re.match(regel["fragment_body"], c["body"]))


def _merge_fragmente(chunks: list[dict], merge_regeln: list[dict] | None) -> list[dict]:
    """MERGE_REGELN anwenden: als Fragment erkannte Kapitel-Chunks an den vorherigen Eintrag
    DESSELBEN Kapitels anhaengen (Name wird Fettzeile im Body). Ohne passenden Vorgaenger
    bleibt der Chunk eigenstaendig (Sicherheitsnetz)."""
    if not merge_regeln:
        return chunks
    ergebnis: list[dict] = []
    for c in chunks:
        regeln = [r for r in merge_regeln if re.search(r["kontext"], c["kontext"])]
        vorher = ergebnis[-1] if ergebnis else None
        regel = next((r for r in regeln
                      if vorher is not None
                      and re.search(r["kontext"], vorher["kontext"])
                      and _ist_fragment(r, c, vorher_name=vorher["name"])), None)
        if regel is not None:
            ergebnis[-1]["body"] += f"\n\n**{c['name']}**\n\n{c['body']}"
            continue
        ergebnis.append(c)
    return ergebnis


def _chunks(markdown: str, kategorie_standard: str = "regel",
            split_regeln: list[tuple[str, int, str | None]] | None = None,
            merge_regeln: list[tuple[str, str]] | None = None,
            skip_namen: "re.Pattern[str] | None" = None) -> list[dict]:
    """Zerlegt Markdown in logische Eintraege: {name, body, seite, kategorie}."""
    # PDF-Extraktion liefert teils NFD-dekomponierte Umlaute ('Einflüsterung' als
    # u+Kombinationszeichen), Soft-Hyphens (U+00AD, reines Druck-Layout) und <br>-Tags
    # in Tabellenzellen ('**Rettungswürfe, in**<br>**denen du geübt bist**') - alles
    # bricht Namensvergleiche/FTS-Token bzw. steht als HTML-Muell im Plain-Text-Body
    # (QS-Fund 11.07.2026). Einmal an der Wurzel normalisieren (bekannte_macken 'srd-de').
    # U+00A0 (geschuetztes Leerzeichen) ist KEIN Wortabstand fuer den Namensvergleich:
    # 'Classes\xa0Summary' != 'Classes Summary', die exakte Namenssuche geht damit ins
    # Leere (28 Faelle in ddb-basic-rules-2014-en, Befund D6). Reines Druck-Layout wie
    # der Soft-Hyphen daneben - an derselben Wurzel normalisieren.
    markdown = unicodedata.normalize("NFC", markdown).replace("­", "").replace("\u00a0", " ")
    markdown = re.sub(r"<br\s*/?>", " ", markdown, flags=re.IGNORECASE)
    # pymupdf4llm markiert in Bildern erkannten Text mit Kommentar-Klammern - der TEXT
    # bleibt (kann Inhalt sein), nur die Marker verschwinden (HTML-Muell im Plain-Body).
    markdown = re.sub(r"<!-- (?:Start|End) of picture text -->", "", markdown)
    markdown = _repariere_fragmente(markdown)
    eltern: dict[int, str] = {}          # level -> Heading-Text (Breadcrumb-Stack)
    fertig: list[dict] = []
    aktuell: dict | None = None
    seite: str | None = None

    def abschliessen() -> None:
        nonlocal aktuell
        if aktuell is None:
            return
        body = _TAGS.sub("", "\n".join(aktuell["zeilen"])).strip()
        # Kursive Pseudo-Headings im Body ('###### _Wundersamer Gegenstand,_') sind
        # Typzeilen, keine Ueberschriften -> Heading-Praefix entfernen, Kursiv behalten.
        body = re.sub(r"^#{4,6}\s+(_[^\n]+)$", r"\1", body, flags=re.MULTILINE)
        if aktuell["kategorie"] is None:
            _BILANZ.verwirf("Abschnitt ohne Kategorie (Kapitel-Kopf/Verzeichnis)")
        elif len(body) < _MIN_BODY:
            _BILANZ.verwirf("Abschnitt ohne Regeltext (leerer Body)")
        else:
            fertig.append({"name": aktuell["name"], "body": body,
                           "kontext": " > ".join(aktuell["pfad"]),
                           "seite": aktuell["seite"], "kategorie": aktuell["kategorie"]})
        aktuell = None

    for zeile in markdown.splitlines():
        m_seite = _SEITE.search(zeile)
        if m_seite:
            seite = m_seite.group(1)
            zeile = _SEITE.sub("", zeile)
            if not zeile.strip():
                continue
        m = _HEADING.match(zeile)
        roh_name = m.group(2).strip() if m else ""
        # Kursive Pseudo-Headings ('_Herkunftstalent_', '_Kosten: ..._') sind Metazeilen,
        # keine Eintragsgrenzen -> im Body belassen.
        ist_kursiv = roh_name.startswith("_") and not roh_name.strip("_*").startswith("**")
        # Label-Pseudo-Headings ('### **Reichweite:** 9 Meter') sind Fortsetzungszeilen
        # des laufenden Eintrags -> Heading-Praefix ab, Zeile in den Body (Modul-Doku).
        if m and not ist_kursiv and (_LABEL_HEADING.match(roh_name)
                                     or KOPF_HEADING.match(roh_name)):
            zeile = roh_name
            m = None
        if m and not ist_kursiv:
            level = len(m.group(1))
            pfad_kontext = [eltern[k] for k in sorted(eltern) if k < level]
            split_level, kategorie = _regel_fuer(pfad_kontext, split_regeln, kategorie_standard)
            ist_statblock = "<mark>" in roh_name
            name = _TAGS.sub("", re.sub(r"\*+", "", roh_name)).strip()
            if skip_namen and skip_namen.match(name):
                kategorie = None             # Kapitel-Kopf ohne Eintrags-Charakter
            if level <= split_level:
                abschliessen()
                # Statblock-Kaesten (<mark>) sind EINGESCHOBENE Wertekaesten, keine
                # Gliederung: nicht in den Eltern-Stack, sonst haengen Folge-Eintraege
                # faelschlich "unter" dem Kasten ('Feuerball' unter 'Drakonischer Geist').
                if not ist_statblock:
                    eltern[level] = name
                    for tiefer in [k for k in eltern if k > level]:
                        del eltern[tiefer]
                aktuell = {"name": name, "zeilen": [], "pfad": pfad_kontext, "seite": seite,
                           "kategorie": "monster" if ist_statblock else kategorie}
                continue
        if aktuell is not None:
            aktuell["zeilen"].append(zeile)
        elif zeile.strip():
            # Text VOR dem ersten Heading (Deckblatt/Praeambel) wird bewusst verworfen -
            # aber gezaehlt: schlaegt die Heading-Erkennung einer Quelle fehl, landet hier
            # plotzlich das halbe Buch, und genau das blieb bisher unsichtbar (D1).
            _BILANZ.verwirf("Zeile vor dem ersten Heading (Deckblatt/Praeambel)")
    abschliessen()
    # Merge NACH dem Chunken, Kontextzeile erst danach - sonst stuende sie mitten im
    # zusammengefuehrten Body.
    fertig = _merge_fragmente(fertig, merge_regeln)
    for c in fertig:
        kontext = c.pop("kontext")
        if kontext:
            c["body"] = f"*Kontext: {kontext}*\n\n{c['body']}"
    return fertig


def _ersetze_bestand(con: sqlite3.Connection, quelle_id: int, zeilen: list[tuple]) -> None:
    """Loeschen + Einfuegen als EIN Schritt innerhalb der Aufrufer-Transaktion (A7) -
    eigene Funktion, damit Tests den Absturz 'nach dem Schreiben' simulieren koennen."""
    con.execute("DELETE FROM eintraege WHERE quelle_id = ?", (quelle_id,))  # idempotent
    con.executemany(
        "INSERT INTO eintraege (quelle_id, kategorie, name_de, name_en, sprache, edition, "
        "seite, body_md) VALUES (?,?,?,?,?,?,?,?)", zeilen)


def importiere_markdown(con: sqlite3.Connection, quelle_kuerzel: str, markdown: str,
                        edition: str, kategorie: str = "regel",
                        split_regeln: list[tuple[str, int, str | None]] | None = None,
                        erlaube_schrumpfen: bool = False) -> int:
    """Chunkt Markdown und schreibt Einträge mit Quelle/Seite/Version. edition Pflicht.
    split_regeln: explizit oder automatisch aus SPLIT_REGELN[quelle_kuerzel].
    A7: parst vollstaendig VOR dem Loeschen; 0 Chunks oder unplausibles Schrumpfen
    (< SCHRUMPF_SCHWELLE des Altbestands ohne erlaube_schrumpfen) -> ValueError, der
    alte Bestand bleibt. COMMITTET NICHT - der Aufrufer fuehrt die Transaktion
    (`with con: ...`). Gibt die Zahl importierter Einträge zurück."""
    if not edition:
        raise ValueError("edition ist Pflicht (V1/Q3) - kein Import ohne Regelversion")
    global _BILANZ
    _BILANZ = Importbilanz()               # je Import eine frische Bilanz
    quelle = con.execute("SELECT id, sprache FROM quellen WHERE kuerzel = ?",
                         (quelle_kuerzel,)).fetchone()
    if quelle is None:
        raise ValueError(f"Quelle '{quelle_kuerzel}' ist nicht registriert - erst in "
                         f"`quellen` anlegen (config/foliant.toml, Q2/Q3)")
    quelle_id, sprache = quelle[0], quelle[1]
    if split_regeln is None:
        split_regeln = SPLIT_REGELN.get(quelle_kuerzel)
    # Quell-spezifische Bereinigung (Druck-Kopfzeilen, Font-Reparaturen, Struktur-
    # Einsaetze) VOR dem Chunken: String = entfernen, Tupel = (Muster, Ersatz),
    # Callable = kompletter Markdown-Pass (z. B. _srd_de_reparatur).
    for eintrag in BEREINIGUNG.get(quelle_kuerzel, []):
        if callable(eintrag):
            markdown = eintrag(markdown)
            continue
        muster, ersatz = eintrag if isinstance(eintrag, tuple) else (eintrag, "")
        markdown = re.sub(muster, ersatz, markdown, flags=re.MULTILINE)

    chunks = _chunks(markdown, kategorie_standard=kategorie, split_regeln=split_regeln,
                     merge_regeln=MERGE_REGELN.get(quelle_kuerzel),
                     skip_namen=SKIP_NAMEN.get(quelle_kuerzel))
    if not chunks:
        raise ValueError(f"Quelle '{quelle_kuerzel}': kein einziger Eintrag aus dem "
                         f"Markdown gewonnen - der alte Bestand bleibt unangetastet "
                         f"(A7). Quelle/Konvertierung pruefen.")
    alt = con.execute("SELECT count(*) FROM eintraege WHERE quelle_id = ?",
                      (quelle_id,)).fetchone()[0]
    # Beide Richtungen (D3): zu wenig ist Datenverlust, zu viel ist ein Zerlegungsfehler.
    _schwellen.pruefe_umfang(quelle_kuerzel, len(chunks), alt, erlaubt=erlaube_schrumpfen)

    _ersetze_bestand(con, quelle_id, [
        (quelle_id, c["kategorie"],
         c["name"] if sprache == "de" else None,
         c["name"] if sprache != "de" else None,
         sprache, edition, c["seite"], c["body"]) for c in chunks])
    # FTS-Rebuild als Teil DERSELBEN Transaktion (Leitplanke + A7: Eintraege und Index
    # landen zusammen oder rollen zusammen zurueck).
    con.execute("INSERT INTO eintraege_fts(eintraege_fts) VALUES('rebuild')")
    return len(chunks)
