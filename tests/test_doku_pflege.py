"""Pflege-Waechter fuer die vier Doku-Dateien (CLAUDE.md: "genau vier, nichts Neues").

WARUM DIESER TEST EXISTIERT (Durchgang 03.08.2026): Die Doku war inhaltlich richtig -
keine falsche Aussage ueber die Architektur - aber die NAVIGATION dorthin war an zwoelf
Stellen kaputt: SPEC verwies fuenfmal auf ein "§17", das es nie gab (der
Charakterbogen-Uebersetzer ist §14, inklusive seiner eigenen Ueberschrift), P2 und P3
zeigten vertauscht auf Sprach- statt Versionskapitel, alle vier Stand-Angaben waren
zwischen zwei und neun Tage alt, und vier Anforderungen aus SPEC (S12, V9, V10, B11)
kamen in der BACKLOG-Bilanz gar nicht vor - hatten also keinen Status.

Jeder dieser Befunde war in Sekunden pruefbar und ist NIEMANDEM aufgefallen, weil kein
Test die Doku angesehen hat (geprueft am 03.08.2026: nur config/projektanweisung.md wurde
von einem Test gelesen). Das ist derselbe Fehlermodus wie bei den Qualitaets-Basiswerten
(CONCEPT.md §12: "Eine Kennzahl ohne Basiswert ist keine Warnung, sondern Rauschen") -
also dieselbe Loesung: eine Maschine, die es merkt.

WAS DIESER TEST NICHT KANN: Er prueft Konsistenz, nicht Wahrheit. Ein Verweis auf ein
EXISTIERENDES, aber inhaltlich falsches Kapitel faellt nicht auf (so rutschte "§5-Regeln"
durch - SPEC hat ein §5, es ist nur nicht das Sprachkapitel). Und ob eine Aussage noch
zum Code passt, sieht nur ein Mensch. Er haelt die mechanischen Fehler raus, damit die
Aufmerksamkeit fuer die inhaltlichen bleibt.
"""
from __future__ import annotations

import collections
import datetime
import pathlib
import re

import pytest

WURZEL = pathlib.Path(__file__).resolve().parents[1]

# Die vier Doku-Dateien plus CLAUDE.md, das laut README "kein fuenftes Dokument" ist,
# sondern der Einstiegspunkt - es verweist nur, traegt aber dieselben Verweis-Risiken.
DOKU = ("SPEC.md", "CONCEPT.md", "BACKLOG.md", "README.md")
ALLE = DOKU + ("CLAUDE.md",)


def lies(name: str) -> str:
    return (WURZEL / name).read_text(encoding="utf-8")


def kapitelnummern(text: str) -> set[int]:
    """Die Nummern der `## N. Titel`-Kapitel - das Ziel jedes §-Verweises."""
    return {int(n) for n in re.findall(r"^## (\d+)\.", text, re.M)}


# --------------------------------------------------------------------------------------
# 1. Bestand: genau vier Doku-Dateien
# --------------------------------------------------------------------------------------

def test_es_bleiben_genau_vier_doku_dateien():
    """CLAUDE.md: "Die Dokumentation besteht aus genau vier Dateien. Halte es dabei -
    nichts Neues anlegen." Ein fuenftes Markdown im Wurzelverzeichnis ist der erste
    Schritt zur Doku-Zersiedelung, und dann weiss niemand mehr, wo etwas hingehoert."""
    gefunden = {p.name for p in WURZEL.glob("*.md")}
    assert gefunden == set(ALLE), (
        f"Doku-Bestand im Wurzelverzeichnis abgewichen: {sorted(gefunden)}.\n"
        f"Erwartet genau: {sorted(ALLE)}. Neuer Inhalt gehoert in eine der vier Dateien "
        f"(Zuordnung: README.md, Abschnitt 'Dokumentation')."
    )


# --------------------------------------------------------------------------------------
# 2. Verweise: jedes §N muss ein Kapitel treffen
# --------------------------------------------------------------------------------------

def _verweise(text: str):
    """Liefert (§-Nummer, Zieldatei-oder-None) je Verweis.

    Zieldatei ist die NAECHSTE VORANGEHENDE Dokument-Nennung im selben ABSATZ - als
    Link ("[CONCEPT.md](CONCEPT.md) §10"), in Backticks ("`CONCEPT.md` §14") oder blank
    ("CONCEPT §9"). Alle drei Formen kommen echt vor. Steht davor nichts, ist es ein
    Eigenverweis - so liest "siehe §4 und [CONCEPT.md](CONCEPT.md) §10" das §4 richtig.

    Absatz, nicht Zeile: Markdown-Prosa ist auf ~95 Zeichen umbrochen, die Dateinennung
    steht deshalb regelmaessig eine Zeile VOR ihrem §-Verweis.
    """
    namen = "|".join(n[:-3] for n in ALLE)
    for absatz in re.split(r"\n\s*\n", text):
        nennungen = [(m.end(), m.group(1) + ".md")
                     for m in re.finditer(rf"\b({namen})(?:\.md)?\b", absatz)]
        for m in re.finditer(r"§\s?(\d+)(?:\s*[–-]\s*(\d+))?", absatz):
            davor = [name for ende, name in nennungen if ende <= m.start()]
            ziel = davor[-1] if davor else None
            for gruppe in m.groups():
                if gruppe:
                    yield int(gruppe), ziel


@pytest.mark.parametrize("name", ALLE)
def test_paragraphenverweise_treffen_ein_kapitel(name):
    """Ein Verweis auf ein Kapitel, das es nicht gibt, ist eine Sackgasse - und genau
    das war der haeufigste Befund: fuenfmal §17 in SPEC, wo bei 14 Kapiteln Schluss ist.

    Toleranz mit Absicht: Steht die Nummer im verlinkten ODER im eigenen Dokument, gilt
    sie als getroffen. Sonst schlaegt der Test bei Zeilen an, die mehrere Dateien
    nennen - und ein Test, der auch bei korrekten Zeilen meckert, wird abgeschaltet."""
    text = lies(name)
    eigene = kapitelnummern(text)
    fehler = []
    for nummer, ziel in _verweise(text):
        erlaubt = set(eigene)
        if ziel in ALLE:
            erlaubt |= kapitelnummern(lies(ziel))
        if nummer not in erlaubt:
            fehler.append(f"§{nummer} (Ziel: {ziel or name})")
    assert not fehler, (
        f"{name} verweist auf Kapitel, die es nicht gibt: {sorted(set(fehler))}.\n"
        f"Kapitel in {name}: {sorted(eigene)}. Kapitel umnummeriert? Dann sind die "
        f"Verweise mitzuziehen - oder besser durch die stabilen Regel-IDs zu ersetzen "
        f"(S1-S12, V1-V10 ...), die nie renummerieren."
    )


# --------------------------------------------------------------------------------------
# 3. Stand-Angabe: der Kopf darf nicht aelter sein als der Inhalt
# --------------------------------------------------------------------------------------

def _datum(roh: str) -> datetime.date:
    tag, monat, jahr = (int(x) for x in roh.split("."))
    return datetime.date(jahr, monat, tag)


@pytest.mark.parametrize("name", DOKU)
def test_stand_ist_nicht_aelter_als_der_juengste_inhalt(name):
    """Alle vier Stand-Angaben waren am 03.08.2026 veraltet - CONCEPT.md um neun Tage
    und zwei Feature-Wellen. Eine Stand-Angabe, die luegt, ist schlimmer als keine: sie
    laedt dazu ein, den Rest fuer aktuell zu halten.

    Geprueft wird gegen die Datei selbst, nicht gegen die Uhr: Wer einen Absatz mit
    "(Review 02.08.2026)" einfuegt, muss den Kopf mitziehen. Ein reiner Tippfehler-Fix
    braucht dagegen kein neues Datum - das waere Buchfuehrung, nicht Pflege."""
    text = lies(name)
    kopf = re.search(r"Stand:?\s*\(?(\d{2}\.\d{2}\.\d{4})", text)
    assert kopf, f"{name} hat keine erkennbare Stand-Angabe ('Stand: TT.MM.JJJJ')."
    stand = _datum(kopf.group(1))

    # Der Kopf selbst zaehlt nicht mit: dort steht die Stand-Angabe ja schon.
    rest = text[kopf.end():]
    daten = [_datum(d) for d in re.findall(r"\d{2}\.\d{2}\.\d{4}", rest)]
    juengster = max(daten, default=stand)
    assert stand >= juengster, (
        f"{name}: Stand-Angabe {stand:%d.%m.%Y} ist aelter als der juengste im Text "
        f"genannte Vorgang ({juengster:%d.%m.%Y}). Kopfzeile nachziehen."
    )


# --------------------------------------------------------------------------------------
# 4. Anforderungen: jede SPEC-ID braucht einen Status im BACKLOG
# --------------------------------------------------------------------------------------

# P = Leitprinzipien (uebergreifend, kein Einzelstatus). A = Ausbaustufen, die
# ausdruecklich NICHT jetzt gebaut werden und in BACKLOG §4 als Vorhaben stehen - ihre
# IDs kollidieren dort ausserdem mit den Kuerzeln der Abnahme-Checkliste (§2 fuehrt
# eigene A1-A4/B1-B5/C1-C3), weshalb ein Woertlich-Vergleich sie nur scheinbar findet.
FAMILIEN_OHNE_EINZELSTATUS = ("P", "A")


def _spec_anforderungen() -> list[str]:
    return re.findall(r"^- \*\*([A-Z]{1,2}\d+[a-z]?) —", lies("SPEC.md"), re.M)


def _backlog_abgedeckt() -> set[str]:
    """Die zwei Stellen, an denen der BACKLOG Status FUEHRT - bewusst nicht der ganze
    Text: dessen Abnahme-Checkliste (§2) nutzt dieselben Kuerzel fuer anderes."""
    text = lies("BACKLOG.md")
    abgedeckt: set[str] = set()

    # (a) die Sammel-Bilanz "Alles nicht Aufgefuehrte ist erfuellt (...)"
    bilanz = re.search(r"Alles nicht Aufgeführte ist erfüllt \(([^)]*)\)", text, re.S)
    assert bilanz, "BACKLOG: die Bilanzzeile 'Alles nicht Aufgeführte ist erfüllt (…)' fehlt."
    for stueck in re.split(r"[,\s/]+", bilanz.group(1)):
        stueck = stueck.strip()
        if not stueck:
            continue
        spanne = re.fullmatch(r"([A-Z]{1,2})(\d+)[–-](?:[A-Z]{1,2})?(\d+)", stueck)
        if spanne:                      # "F1–F7" / "V1–V6" ausschreiben
            praefix, von, bis = spanne.group(1), int(spanne.group(2)), int(spanne.group(3))
            abgedeckt.update(f"{praefix}{n}" for n in range(von, bis + 1))
        else:
            abgedeckt.add(stueck)

    # (b) die Statustabelle "| Anf. | Inhalt | Status | Zu |"
    tabelle = re.search(r"\| Anf\. \|.*?\n\|[-| ]+\|\n((?:\|.*\n)+)", text)
    assert tabelle, "BACKLOG: die Statustabelle '| Anf. | Inhalt | Status | Zu |' fehlt."
    for zeile in tabelle.group(1).splitlines():
        erste_spalte = zeile.split("|")[1]
        abgedeckt.update(re.findall(r"[A-Z]{1,2}\d+[a-z]?", erste_spalte))
    return abgedeckt


def test_jede_spec_anforderung_hat_einen_status_im_backlog():
    """S12, V9, V10 und B11 kamen am 03.08.2026 in der Bilanz nicht vor - die vier
    juengsten Anforderungen hatten damit keinen Status, und V9 ist sogar NICHT erfuellt
    (der Errata-Layer steht, die PDFs fehlen). Eine Anforderung ohne Status ist eine
    Anforderung, die niemand abnimmt.

    Loest der Test aus, ist die Frage nicht "Test anpassen", sondern: erfuellt oder
    offen? Erfuellt -> in die Bilanz-Klammer. Offen oder teilweise -> eigene Zeile in
    der Statustabelle, mit dem Milestone, der sie schliesst."""
    offen = [
        a for a in _spec_anforderungen()
        if not a.startswith(FAMILIEN_OHNE_EINZELSTATUS) and a not in _backlog_abgedeckt()
    ]
    assert not offen, (
        f"SPEC-Anforderungen ohne Status in BACKLOG.md: {sorted(set(offen))}.\n"
        f"Entweder in die Bilanz-Klammer ('Alles nicht Aufgeführte ist erfüllt (…)') "
        f"oder als eigene Zeile in die Statustabelle."
    )


# --------------------------------------------------------------------------------------
# 5. Dateiverweise: was die Doku in Backticks nennt, muss es geben
# --------------------------------------------------------------------------------------

# Absichtlich fehlend. Jede Zeile braucht einen Grund - sonst waechst hier die Ausrede
# statt der Doku.
PFADE_OHNE_DATEI = {
    # In CONCEPT.md §10 ausdruecklich als ENTFERNT dokumentiert (29.07.2026): ein
    # zentrales Macken-Modul, das kein Codepfad las. Der Eintrag ist die Begruendung,
    # warum es nicht wiederkommt - er muss den Namen nennen duerfen.
    "app/bekannte_macken.py",
    # Gitignored: privat aus gekauften Druck-PDFs abgeleitet (README "Oeffentlicher
    # Code, private Inhalte"). Auf dem Entwicklerrechner vorhanden, im Klon nicht.
    "importer/frhof_reparatur.py",
    "importer/reparatur_ddb_privat.py",
    "tests/test_ddb_druck_privat.py",
    # Gitignored: entsteht erst beim Einrichten bzw. Import.
    "config/foliant.toml",
    "data/foliant.sqlite",
    "data/foliant-protokoll.sqlite",
    "data/glossar_web.sqlite",
    "data/private/foliant-private.sqlite",
    "korpus-manifest.json",
}


@pytest.mark.parametrize("name", ALLE)
def test_genannte_dateien_existieren(name):
    """Ein Verweis auf eine Datei, die es nicht mehr gibt, schickt den naechsten Leser
    ins Leere - und faellt sonst erst auf, wenn er sie sucht. Umgekehrt hat genau diese
    Pruefung gezeigt, dass die Doku vollstaendig ist: alle 13 Treffer waren
    Tabellen-Kurznamen oder erklaerte Ausnahmen."""
    fehlend = sorted({
        pfad for pfad in re.findall(r"`([A-Za-z_][\w./<>-]*/[\w./<>-]+\.\w{1,5})`", lies(name))
        # Platzhalter wie `quellen/md/<kuerzel>.md` sind Muster, keine Dateien.
        if "<" not in pfad and pfad not in PFADE_OHNE_DATEI and not (WURZEL / pfad).exists()
    })
    assert not fehlend, (
        f"{name} nennt Dateien, die es nicht gibt: {fehlend}.\n"
        f"Umbenannt oder entfernt? Dann die Doku mitziehen. Absichtlich fehlend "
        f"(gitignored, bewusst entfernt)? Dann mit Grund in PFADE_OHNE_DATEI."
    )


# --------------------------------------------------------------------------------------
# 6. Doppelungen: dieselbe Aussage nicht zweimal pflegen
# --------------------------------------------------------------------------------------

# Wortgleiche Saetze, die in zwei Dateien stehen DUERFEN - mit Grund.
ERLAUBTE_DOPPELUNGEN = {
    # README ist die oeffentliche Zusage an Mitlesende, CONCEPT.md §13 das
    # Sicherheitsmodell. Beide muessen fuer sich stehen: Wer die eine Datei liest, darf
    # nicht die andere brauchen, um zu wissen, dass der Server ohne die privaten Module
    # laeuft. Bewusst geduldet, nicht uebersehen.
    "Ohne sie bleibt der Server voll funktionsfähig — nur die kommerziellen "
    "Druck-Importe entfallen, die zugehörigen Tests überspringen sich selbst.",
}


def _lange_saetze(text: str):
    text = re.sub(r"```.*?```", " ", text, flags=re.S)       # Codebloecke sind Zitate
    text = re.sub(r"[`*_>#|]", "", text)
    text = re.sub(r"\s+", " ", text)
    for satz in re.split(r"(?<=[.!?:]) ", text):
        satz = satz.strip()
        if len(satz) >= 120:                                 # kurze Formeln sind kein Befund
            yield satz


def test_keine_wortgleichen_saetze_in_zwei_dateien():
    """Eine Aussage an zwei Stellen ist eine Aussage, die beim naechsten Mal an EINER
    Stelle geaendert wird. So stand die Provenienz-Zusage ("eine Quelle ohne sie bleibt
    gueltig, sie kann nur weniger ueber sich sagen") wortgleich in SPEC.md V10 und
    CONCEPT.md §3 - zwei Dateien, ein Gedanke, doppelte Pflege.

    Die Schwelle liegt bei 120 Zeichen: kurze Wiederholungen ("Editionen werden NIE
    geraten") sind gewollte Redundanz fuer die teuren Fehler. Was hier anschlaegt, ist
    lange Prosa - und die gehoert an EINE Stelle plus Verweis."""
    wo: dict[str, set[str]] = collections.defaultdict(set)
    for name in ALLE:
        for satz in _lange_saetze(lies(name)):
            if satz not in ERLAUBTE_DOPPELUNGEN:
                wo[satz].add(name)
    doppelt = {s: sorted(d) for s, d in wo.items() if len(d) > 1}
    assert not doppelt, (
        "Wortgleiche Absaetze in mehreren Doku-Dateien:\n"
        + "\n".join(f"  {dateien}: {s[:110]}…" for s, dateien in doppelt.items())
        + "\nEntscheide, WO die Aussage hingehoert (SPEC = was, CONCEPT = wie, "
          "BACKLOG = offen, README = Einstieg), und verweise von den anderen darauf. "
          "Bewusst doppelt? Dann mit Grund in ERLAUBTE_DOPPELUNGEN."
    )
