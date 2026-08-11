"""Waechter fuer den Rueckmeldungs-Durchgang: das Freigabe-Format und sein Gedaechtnis.

WARUM DIESER TEST EXISTIERT (11.08.2026): Der Durchgang legt David zweimal pro Woche
Vorschlaege zur Freigabe vor. Bis hierher stand das Format als achtspaltige Tabelle in der
Ablaufdatei und das Gedaechtnis als handgepflegte JSON - beides von KEINEM Test gesehen
(geprueft per grep ueber tests/, app/, evals/, Makefile). Zwei Fehlerklassen liefen damit
frei:

1. Das Format driftet. Die Tabelle hatte acht Spalten und vier Fliesstext-Zellen und
   verletzte damit die Regel, die Foliant seinem eigenen Bot gibt (config/discord_zusatz.md:
   ab drei Spalten oder Fliesstext in einer Zelle keine Tabelle). Niemandem aufgefallen.
2. Die JSON leakt. Sie ist die EINZIGE Datei, in die ein Durchgang schreibt, das Repo ist
   oeffentlich, und die Quelle jedes Befunds ist ein Discord-Permalink, der die Guild
   verriete. Im Diff sieht ein Mensch eine 18-stellige Zahl nicht zuverlaessig.

WAS DIESER TEST NICHT KANN: Er prueft die VORLAGE, nicht die Einhaltung. Ob die Ausgabe
eines echten Laufs dem Muster folgt, sieht kein Test - dafuer muesste er die Sitzung lesen.
Das ist die bewusste Grenze; mehr waere Formatpolizei. Driftet das Format im Betrieb, ist
der naechste Hebel ein zweites woertliches Beispiel, keine weitere Regel (CONCEPT.md §10,
DC4: wo eine Regel zweimal nicht wirkte, wirkte ein Muster-Beispiel).
"""
from __future__ import annotations

import datetime
import json
import pathlib
import re

import pytest

WURZEL = pathlib.Path(__file__).resolve().parents[1]
ABLAUF = WURZEL / ".claude/ablaeufe/rueckmeldungen.md"
STAND = WURZEL / "config/rueckmeldungen_stand.json"

# Die sechs Feldzeilen einer Freigabekarte. `Achtung` ist bedingt (nur bei einem der sechs
# Ausloeser) - dass es im Muster ueberhaupt vorkommt, ist trotzdem Pflicht: sonst weiss
# niemand, wie die Zeile aussieht, wenn sie faellig wird.
LABELS = ("Frage", "Befund", "Ursache", "Änderung", "Beleg", "Achtung")

# 78 statt 80: ueberlebt ein 80-Spalten-Terminal, das schmalste Fenster, das David
# plausibel offen hat. Bewusst NICHT die 45 aus config/discord_zusatz.md - anderes Medium,
# andere Begruendung.
MAX_BREITE = 78

# 2 Einzug + laengstes Label ("Änderung", 8) + 2 Trennung = Wert ab Spalte 13.
WERTSPALTE = 13


def _ablauf_text() -> str:
    return ABLAUF.read_text(encoding="utf-8")


def _muster() -> str:
    """Der eine `text`-Codeblock aus Abschnitt 4 - das Format selbst."""
    abschnitt = re.search(r"^## 4\..*?(?=^## )", _ablauf_text(), re.S | re.M)
    assert abschnitt, "Abschnitt '## 4.' nicht gefunden - wurde er umbenannt?"
    bloecke = re.findall(r"^```text\n(.*?)^```", abschnitt.group(0), re.S | re.M)
    assert len(bloecke) == 1, (
        f"Abschnitt 4 traegt {len(bloecke)} `text`-Bloecke, erwartet genau einen. "
        f"Zwei Muster sind zwei Formate, und dann folgt der Lauf dem falschen.")
    return bloecke[0]


def _stand() -> dict:
    return json.loads(STAND.read_text(encoding="utf-8"))


def _erlaubte_werte(schluessel: str, erwartet: int) -> set[str]:
    """Die Aufzaehlung aus einem selbstdokumentierenden `_*_format`-Schluessel.

    Bewusst AUS DER DATEI gelesen und nicht im Test hartkodiert: Sonst koennten die Prosa
    in der JSON, die Karte im Ablauf und dieser Test zu dritt auseinanderlaufen, und die
    Datei behauptete etwas, das nirgends mehr gilt."""
    werte = set(re.findall(r"'(\w+)' \(", _stand()[schluessel]))
    assert len(werte) == erwartet, (
        f"{schluessel} zaehlt {sorted(werte)} auf, erwartet {erwartet} Werte. "
        f"Wurde die Aufzaehlung umformuliert? Dann traegt sie das Muster "
        f"\"'wert' (Begruendung)\" nicht mehr, und dieser Test liest ins Leere.")
    return werte


# --------------------------------------------------------------------------------------
# 1. Das Format: die Vorlage, an die sich der Lauf haelt
# --------------------------------------------------------------------------------------

def test_muster_bleibt_in_der_terminalbreite():
    """Der Grund fuer die ganze Umstellung. Die alte Tabelle brach um, und eine Ausgabe,
    die man seitwaerts schieben muss, kostet bei jeder Freigabe Zeit."""
    zu_breit = [z for z in _muster().splitlines() if len(z) > MAX_BREITE]
    assert not zu_breit, (
        f"{len(zu_breit)} Zeile(n) ueber {MAX_BREITE} Zeichen:\n" +
        "\n".join(f"  ({len(z)}) {z}" for z in zu_breit))


@pytest.mark.parametrize("label", LABELS)
def test_muster_fuehrt_jedes_feld_auf_der_wertspalte(label):
    """Ausrichtung ist hier kein Schoenheitsfehler, sondern der Unterschied zwischen
    Scannen und Lesen: Wer immer an derselben Stelle sucht, findet ohne zu suchen."""
    zeilen = [z for z in _muster().splitlines() if re.match(rf"^  {label} ", z)]
    assert zeilen, (
        f"Das Muster zeigt kein Feld `{label}` - dann weiss niemand, wie es aussieht.")
    falsch = [z for z in zeilen if len(re.match(rf"^  {label} +", z).group(0)) + 1
              != WERTSPALTE]
    assert not falsch, (
        f"`{label}` beginnt nicht auf Spalte {WERTSPALTE}:\n" +
        "\n".join(f"  {z}" for z in falsch))


def test_muster_nennt_das_vollstaendige_freigabe_vokabular():
    """Ein Vokabular, das die Ausgabe nicht mitliefert, kennt nur, wer den Ablauf gelesen
    hat - und das ist beim Freigeben genau der Falsche."""
    muster = _muster()
    for wort in ("nein", "später", "alles", "nichts"):
        assert f"„{wort}" in muster or f"{wort}\"" in muster or f" {wort} " in muster, (
            f"Die Freigabezeile nennt `{wort}` nicht")


def test_muster_traegt_keine_echten_discord_spuren():
    """Das Muster ist erfunden und muss es bleiben. Echte Fragetexte gehoeren in die
    Sitzung, Links und IDs nirgendwohin (CONCEPT.md §13)."""
    muster = _muster()
    assert "http" not in muster, "Ein Link im Muster - das Muster ist erfunden"
    assert not re.search(r"\d{17,19}", muster), "Eine Discord-ID im Muster"


def test_ursache_werte_der_karte_stammen_aus_dem_gedaechtnis():
    """Der Bindeknoten: Die Karte rendert das Befund-Objekt der JSON. Fuehren beide
    verschiedene Vokabulare, wird das Eintragen in Schritt 6 zum Uebersetzen - und beim
    Uebersetzen geht der Wiederholungszaehler kaputt, der auf exakter Gleichheit beruht."""
    erlaubt = _erlaubte_werte("_befund_format", erwartet=4)
    benutzt = {m for m in re.findall(r"^  Ursache   (\w+) ", _muster(), re.M)}
    assert benutzt, "Das Muster zeigt keine `Ursache`-Zeile mit Enum-Wort"
    assert benutzt <= erlaubt, (
        f"Das Muster benutzt {sorted(benutzt - erlaubt)}, "
        f"die JSON kennt nur {sorted(erlaubt)}")


# --------------------------------------------------------------------------------------
# 2. Das Gedaechtnis: Schema des Sichtungsstands
# --------------------------------------------------------------------------------------

def test_hochwassermarke_ist_ein_vergleichbarer_zeitpunkt():
    """Gegen diese Marke entscheidet der Durchgang, was er ueberhaupt ansieht. Ist sie
    unlesbar oder ohne Zeitzone, arbeitet er entweder doppelt oder uebersieht."""
    marke = _stand()["zuletzt_gesichtet_bis"]
    gelesen = datetime.datetime.fromisoformat(marke)
    assert gelesen.tzinfo is not None, (
        f"`{marke}` traegt keine Zeitzone - der Vergleich gegen die UTC-Zeitstempel aus "
        f"app/protokoll.py waere dann geraten")


def test_jeder_befund_traegt_regel_ursache_und_entscheidung():
    """Erst die Struktur macht Wiederholungstaeter sichtbar - eine Regel, die dreimal
    bricht, ist kein Modellfehler mehr. Ein Befund ohne `regeln` faellt aus dieser
    Zaehlung heraus, ohne dass es jemand merkt."""
    ursachen = _erlaubte_werte("_befund_format", erwartet=4)
    entscheidungen = _erlaubte_werte("_entscheidung_format", erwartet=3)

    for durchgang in _stand()["durchgaenge"]:
        for i, befund in enumerate(durchgang["befunde"], 1):
            wo = f"Durchgang {durchgang['datum']}, Befund {i}"
            assert befund.get("regeln"), f"{wo}: keine Regel-ID"
            assert befund.get("was", "").strip(), f"{wo}: kein Befundsatz"
            assert befund.get("ursache") in ursachen, (
                f"{wo}: ursache={befund.get('ursache')!r}, erlaubt {sorted(ursachen)}")
            assert befund.get("entscheidung") in entscheidungen, (
                f"{wo}: entscheidung={befund.get('entscheidung')!r}, "
                f"erlaubt {sorted(entscheidungen)}")


def test_ein_nein_oder_spaeter_traegt_seinen_grund():
    """Ohne den Grund ist die Ablehnung nur ein Zaehlwert. Mit ihm kann der naechste
    Durchgang den gleichartigen Vorschlag mit `Achtung`-Zeile vorlegen, statt David
    dieselbe Entscheidung ein zweites Mal zu kosten."""
    for durchgang in _stand()["durchgaenge"]:
        for i, befund in enumerate(durchgang["befunde"], 1):
            if befund["entscheidung"] != "ja":
                assert befund.get("grund", "").strip(), (
                    f"Durchgang {durchgang['datum']}, Befund {i}: "
                    f"entscheidung={befund['entscheidung']!r} ohne `grund`")


def test_der_sichtungsstand_verraet_die_guild_nicht():
    """Die einzige Datei, in die ein Durchgang schreibt - und das Repo ist oeffentlich.
    Ein Permalink `discord.com/channels/<guild>/…` verriete die Guild, eine nackte
    Snowflake-ID den Kanal. Der Ablauf sagt das seit jeher; hier merkt es eine Maschine.

    Bewusst NICHT auf das Wort 'Discord' gepruegt: `bemerkung` darf den Discord-Zusatz
    beim Namen nennen. Geprueft wird, was tatsaechlich leakt."""
    roh = STAND.read_text(encoding="utf-8")
    assert "http" not in roh, "Eine URL im Sichtungsstand"
    assert "discord.com" not in roh.lower(), "Ein Discord-Permalink im Sichtungsstand"
    ids = re.findall(r"\d{17,19}", roh)
    assert not ids, f"Discord-IDs im Sichtungsstand: {ids}"


# --------------------------------------------------------------------------------------
# 3. Die Ablaufdateien nennen nur Dateien, die es gibt
# --------------------------------------------------------------------------------------

@pytest.mark.parametrize("datei", sorted((WURZEL / ".claude/ablaeufe").glob("*.md")),
                         ids=lambda p: p.name)
def test_genannte_dateien_existieren(datei):
    """Dieselbe Pruefung, die tests/test_doku_pflege.py fuer die vier Wurzel-Dokumente
    fuehrt - nur fuer die Ablaeufe, die sie nicht ansieht. Bewusst NICHT dort ergaenzt:
    jene Datei ist auf die vier Dokumente gescoped, und ihre uebrigen Pruefungen
    (§-Verweise, Stand-Angabe, SPEC-Status, 'genau vier') ergaeben fuer Ablaeufe keinen
    Sinn oder braeuchten Ausnahmen.

    Ein Ablauf ist eine Handlungsanweisung: Zeigt sie auf eine Datei, die es nicht mehr
    gibt, laeuft der naechste zeitgesteuerte Durchgang ins Leere - unbeaufsichtigt, und
    niemand sieht zu."""
    fehlend = sorted({
        pfad for pfad in re.findall(r"`(\.?[A-Za-z_][\w./<>-]*/[\w./<>-]+\.\w{1,7})`",
                                    datei.read_text(encoding="utf-8"))
        if "<" not in pfad and not (WURZEL / pfad).exists()
    })
    assert not fehlend, (
        f"{datei.name} nennt Dateien, die es nicht gibt: {fehlend}.\n"
        f"Umbenannt oder entfernt? Dann den Ablauf mitziehen - er wird unbeaufsichtigt "
        f"gefahren und kann nicht nachfragen.")
