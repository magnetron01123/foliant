"""Blocker-Regression SYN-P0-006 (Synthese 2026-07-12, verifiziert): Ungueltige
kategorie-/quelle-/richtung-Parameter erzeugten ein falsches 'Nichts im Bestand' -
inklusive des B1-Ehrlichkeitshinweises, der das Modell zur Fehlanzeige anwies.
Reproduzierter Realfall: suche_bestand('Feuerball', kategorie='spell') -> leer + Leerhinweis,
obwohl der Feuerball mit kategorie='zauber' zwei Treffer hatte."""
import sqlite3
from pathlib import Path

import pytest

from app import db as adb
from app.tools import charakter as ch
from app.tools import nachschlagen as ns
from app.tools import suche as su

_SCHEMA = Path(__file__).resolve().parent.parent / "db" / "schema.sql"


@pytest.fixture()
def bestand(tmp_path, monkeypatch):
    pfad = tmp_path / "foliant-validierung.sqlite"
    con = sqlite3.connect(pfad)
    con.executescript(_SCHEMA.read_text(encoding="utf-8"))
    con.execute(
        "INSERT INTO quellen (kuerzel,titel,sprache,edition,herkunft,lizenz,prioritaet) "
        "VALUES ('srd-de','SRD 5.2.1 (Deutsch)','de','2024','pdf','CC-BY-4.0',10)")
    con.execute(
        "INSERT INTO eintraege (quelle_id,kategorie,name_de,name_en,sprache,edition,seite,"
        "body_md) VALUES (1,'zauber','Feuerball','Fireball','de','2024','139','8W6 Feuer.')")
    con.commit()
    con.execute("INSERT INTO eintraege_fts(eintraege_fts) VALUES('rebuild')")
    con.commit()
    con.close()
    monkeypatch.setattr(adb, "standard_pfad", lambda: pfad)
    return pfad


def test_ungueltige_kategorie_ist_kein_leerer_bestand(bestand):
    """Der Realfall der Synthese: englischer Kategoriewert fuer vorhandenen Inhalt."""
    s = su.foliant_suche_bestand("Feuerball", kategorie="spell")
    assert s["treffer"] == [] and "fehler" in s
    assert "spell" in s["fehler"] and "zauber" in s["fehler"]      # gueltige Werte genannt
    assert "KEIN 'nicht im Bestand'" in s["hinweis"]
    assert "Nichts im Bestand" not in s.get("hinweis", "")         # nie der B1-Leerhinweis
    # Gueltige Kategorie liefert den Treffer weiterhin:
    assert su.foliant_suche_bestand("Feuerball", kategorie="zauber")["treffer"]


def test_quellen_titel_statt_kuerzel_wird_erklaert(bestand):
    """Haeufigster Fehlaufruf: der Treffer-TITEL als quelle-Filter (SYN-P1-002-Nachbar)."""
    s = su.foliant_suche_bestand("Feuerball", quelle_kuerzel="SRD 5.2.1 (Deutsch)")
    assert s["treffer"] == [] and "fehler" in s
    assert "srd-de" in s["fehler"] and "Titel" in s["fehler"]
    assert su.foliant_suche_bestand("Feuerball", quelle_kuerzel="srd-de")["treffer"]


def test_ungueltige_talent_kategorie(bestand):
    antwort = ch.foliant_liste_optionen("talent", talent_kategorie="origin")
    assert antwort["talente"] == [] and "fehler" in antwort
    assert "herkunft" in antwort["fehler"]


def test_ungueltige_glossar_richtung(bestand):
    u = ns.foliant_uebersetze_begriff("Feuerball", richtung="de-en")
    assert u["gefunden"] is False and "fehler" in u
    assert "auto" in u["fehler"]


def test_p2_grenzen_gegen_ueberlast(bestand):
    """SYN-P2-004 (codex TECH-013): ueberlange Query wird gekappt (kein Crash, kein
    ausuferndes Fuzzy), limit ueber der Obergrenze wird gedeckelt."""
    from app import db as adb
    r = su.foliant_suche_bestand("Feuerball " + "z" * 5000)
    assert isinstance(r["treffer"], list)                 # kein Crash, echte Antwort
    con = adb.connect(str(adb.standard_pfad()))
    try:
        erg = adb.fts_suche(con, "Feuerball", limit=99999)
        assert len(erg["treffer"]) <= adb.MAX_LIMIT
    finally:
        con.close()


def test_p2_glossar_cache_invalidiert_nach_aenderung(bestand):
    """SYN-P2-004: der Glossar-Cache liefert nach einer Aenderung (neue Zeile ->
    andere Zeilenzahl) die aktuellen Daten, nicht den alten Stand."""
    from app import db as adb
    from app import glossar as gl
    con = adb.connect(str(adb.standard_pfad()))
    try:
        assert gl.lookup(con, "Feuerball", richtung="de_en") == []   # noch nichts
        con.execute("INSERT INTO glossar (term_en,term_de,offiziell) "
                    "VALUES ('Fireball','Feuerball',1)")
        con.commit()
        zeilen = gl.lookup(con, "Feuerball", richtung="de_en")
        assert zeilen and zeilen[0]["term_en"] == "Fireball"         # Cache invalidiert
    finally:
        con.close()


def test_kategorien_stehen_ueberall_gleich():
    """Die acht Kategorien sind ein geschlossener Vertrag und stehen an DREI Orten:
    db.KATEGORIEN (Laufzeit-Validierung), das Literal in nachschlagen (daraus erzeugt
    FastMCP das Enum-Schema fuer den Client) und der CHECK in db/schema.sql.

    Driftet einer, entsteht genau die Fehlerklasse aus SYN-P0-006, nur eine Ebene tiefer:
    entweder gibt es Inhalte, die kein Tool abfragen kann, oder ein Tool bietet eine
    Kategorie an, die der Schema-CHECK beim Import ablehnt. Beides faellt sonst erst
    am Bestand auf. Das Literal muss literal bleiben - aus einem Tupel gebaut erzeugte
    FastMCP kein Enum -, also prueft der Test die Gleichheit, statt sie zu erzwingen."""
    import re
    import typing

    literal = set(typing.get_args(ns.Kategorie))
    assert literal == set(adb.KATEGORIEN), (
        f"nachschlagen.Kategorie vs. db.KATEGORIEN: "
        f"nur im Literal {sorted(literal - set(adb.KATEGORIEN))}, "
        f"nur in db {sorted(set(adb.KATEGORIEN) - literal)}")

    sql = _SCHEMA.read_text(encoding="utf-8")
    block = re.search(r"kategorie\s+TEXT NOT NULL CHECK \(kategorie IN\s*\((.*?)\)\)",
                      sql, re.S)
    assert block, "CHECK-Constraint fuer kategorie in db/schema.sql nicht gefunden"
    im_schema = set(re.findall(r"'([^']+)'", block.group(1)))
    assert im_schema == set(adb.KATEGORIEN), (
        f"db/schema.sql vs. db.KATEGORIEN: "
        f"nur im Schema {sorted(im_schema - set(adb.KATEGORIEN))}, "
        f"nur in db {sorted(set(adb.KATEGORIEN) - im_schema)}")


def test_artefaktvertrag_kennt_dieselben_kategorien():
    """`importer/ddb_artefakt.KATEGORIEN_ERLAUBT` ist die fuenfte Stelle mit den acht
    Kategorien - und bleibt bewusst eine eigene: das Modul ist der ARTEFAKTVERTRAG und
    ausdruecklich architekturneutral (es laeuft im Exporter-Container, der die Foliant-DB
    gar nicht sieht). Ein Import von app.db waere dort die falsche Abhaengigkeit.

    Stimmen muessen sie trotzdem: kennt der Vertrag eine Kategorie weniger, kann der
    Exporter sie nie liefern; kennt er eine mehr, schreibt der Offline-Import einen Wert,
    den der Schema-CHECK ablehnt. Also ein Waechter statt einer Kopplung."""
    from importer.ddb_artefakt import KATEGORIEN_ERLAUBT

    assert KATEGORIEN_ERLAUBT == set(adb.KATEGORIEN), (
        f"Artefaktvertrag vs. db.KATEGORIEN: "
        f"nur im Vertrag {sorted(KATEGORIEN_ERLAUBT - set(adb.KATEGORIEN))}, "
        f"nur in db {sorted(set(adb.KATEGORIEN) - KATEGORIEN_ERLAUBT)}")


def test_ddb_editionsnamen_stimmen_mit_den_aliassen():
    """Dass D&D Beyond 2024 als '5.5e' und 2014 als '5e' fuehrt, ist EIN externer Fakt
    (SPEC.md §13) - er steht aber an zwei Stellen: `db.EDITION_ALIASSE` (Nutzereingabe in
    der Suche) und `ddb_exporter.katalog._EDITION_PREFIX` (Buch-Kategorie beim Export).

    Zusammengelegt werden sie NICHT: die Katalog-Fassung ist eine geordnete Liste, weil
    sie per PRAEFIX matcht und '5.5e' vor '5e' geprueft werden muss - eine Ableitung aus
    dem Dict muesste diese Ordnung durch Sortieren wiederherstellen und waere fragiler als
    zwei klare Listen. Der Waechter genuegt: eine kuenftige Edition darf nicht in nur
    einer der beiden landen."""
    from importer.ddb_exporter.katalog import _EDITION_PREFIX

    assert dict(_EDITION_PREFIX) == adb.EDITION_ALIASSE
    # Praefix-Ordnung ist Semantik, nicht Kosmetik: '5e' zuerst wuerde '5.5e' schlucken.
    laengen = [len(p) for p, _ in _EDITION_PREFIX]
    assert laengen == sorted(laengen, reverse=True), "laengster Praefix muss zuerst stehen"


def test_admin_cli_block_in_concept_ist_wirklich_vollstaendig():
    """CONCEPT.md §8 fuehrt die Admin-CLI unter der Ueberschrift "(vollstaendig)" - und
    liess am 30.07.2026 zwei Kommandos aus (`glossar-paare`, `suchbericht`). Dazu nannte
    der Text ein Flag `--vorschau`, das es nie gab: `git log -S` findet es ausschliesslich
    im Doku-Commit. Wer der Anleitung folgte, bekam Exit 2.

    Der Waechter vergleicht den Doku-Block mit dem echten argparse-Baum. Er prueft die
    NAMEN, nicht die Beschreibungen - die duerfen und sollen unterschiedlich formuliert
    sein. Dieselbe Bauart wie die Vertragswaechter darueber: eine Doppelung, die lautlos
    driftet, bekommt einen Test statt einer Bitte."""
    import re
    from pathlib import Path

    from app import admin

    wurzel = Path(__file__).resolve().parent.parent
    text = (wurzel / "CONCEPT.md").read_text(encoding="utf-8")
    block = re.search(r"### Admin-CLI \(vollständig\)\n```\n(.*?)```", text, re.S)
    assert block, "Der Admin-CLI-Block in CONCEPT.md §8 ist verschwunden oder umbenannt"

    dokumentiert: set[str] = set()
    for zeile in block.group(1).splitlines():
        if not zeile.strip():
            continue
        felder = [f.strip() for f in zeile.split("|") if f.strip()]
        if len(felder) > 1 and all(" " not in f for f in felder):
            # Sammelzeile 'ddb-pruefe | ddb-import | ...' - jedes Feld ist ein Kommando.
            # Die Bedingung 'jedes Feld ein einzelnes Wort' trennt sie von der
            # import-Zeile, deren Pipes ARGUMENT-Alternativen sind, keine Kommandos.
            dokumentiert |= set(felder)
        else:
            # Sonst: erstes Wort = Kommando, der Rest ist die Beschreibungsspalte.
            dokumentiert.add(zeile.split()[0])

    import argparse

    echte = {name for a in admin.baue_parser()._actions
             if isinstance(a, argparse._SubParsersAction) for name in a.choices}

    assert dokumentiert == echte, (
        f"CONCEPT.md §8 und app/admin.py driften: "
        f"nur in der Doku {sorted(dokumentiert - echte)}, "
        f"nur im Code {sorted(echte - dokumentiert)}")


def test_quelle_kuerzel_wird_im_strukturpfad_nicht_still_verworfen(bestand):
    """Befund 30.07.2026: foliant_suche_bestand reichte `quelle_kuerzel` nur in den
    VOLLTEXT-Pfad weiter. _struktur_filter nahm den Parameter gar nicht erst entgegen -
    eine reine Struktur-Anfrage mit Quellen-Einschraenkung durchsuchte still den GESAMTEN
    Bestand, und ein Tippfehler im Kuerzel blieb ebenso still.

    Das ist derselbe Fehlermodus wie SYN-P0-006, nur umgekehrt: dort erzeugte ein
    ungueltiger Parameter eine falsche Fehlanzeige, hier erzeugt er ein falsches
    ERGEBNIS - und das ist schwerer zu bemerken, weil die Antwort plausibel aussieht.
    'gefiltert_nach' behauptete sogar, die Quelle sei beruecksichtigt."""
    r = su.foliant_suche_bestand(kategorie="zauber", grad=3, quelle_kuerzel="GIBTESNICHT")
    assert "fehler" in r, f"ungueltiges Kuerzel stillschweigend ignoriert: {r}"
    assert "GIBTESNICHT" in r["fehler"]
    assert r["treffer"] == []
    # Und der Hinweis muss klarstellen, dass das KEINE Bestandsluecke ist:
    assert "KEIN 'nicht im Bestand'" in r["hinweis"]


def test_detailabruf_meldet_ungueltige_kategorie_strukturiert(bestand):
    """Regression der Tool-Zusammenlegung (30.07.2026): Bis dahin steckte die Kategorie im
    WERKZEUGNAMEN (foliant_hol_zauber) und konnte gar nicht ungueltig sein. Seit
    foliant_hol_eintrag ist sie ein Parameter - und ein ungueltiger Wert flog als
    ungefangene ValueError aus _pruefe_kategorie heraus, statt als 'fehler'
    zurueckzukommen. Der SUCH-Pfad faengt sie seit SYN-P0-006; der Detailpfad hatte die
    Stelle nie gebraucht.

    Beide Wege muessen sie nehmen - auch der ueber eintrag_id, der sonst 'Referenz
    veraltet' meldet und damit den falschen Grund nennt."""
    for aufruf in (dict(name="Feuerball"), dict(eintrag_id=1)):
        r = ns.foliant_hol_eintrag("spell", **aufruf)          # englischer Wert statt 'zauber'
        assert "fehler" in r, f"{aufruf}: keine strukturierte Meldung, {r}"
        assert "spell" in r["fehler"] and "zauber" in r["fehler"]
        assert "KEIN 'nicht im Bestand'" in r["hinweis"]


def test_kategorie_mismatch_nennt_den_richtigen_wert(bestand):
    """Ein Aufruf mit gueltiger, aber FALSCHER Kategorie zu einer eintrag_id ist bis auf
    ein Feld richtig - die Meldung muss deshalb den Wert nennen, der dort hingehoert,
    statt auf ein 'passendes foliant_hol_*' zu verweisen, das es nicht mehr gibt."""
    eid = ns.foliant_hol_eintrag("zauber", "Feuerball")["eintrag_id"]
    r = ns.foliant_hol_eintrag("monster", eintrag_id=eid)
    assert "fehler" in r
    assert "kategorie='zauber'" in r["fehler"], r["fehler"]
    assert "foliant_hol_*" not in r["fehler"]


def test_herausforderungsgrad_wird_validiert(bestand):
    """hg ging als EINZIGER Facetten-Parameter ungeprueft durch, waehrend schule,
    schadensart und typ einen strukturierten Fehler liefern. 'abc' erzeugte deshalb keinen
    Parameterfehler, sondern einen ehrlich klingenden Nulltreffer - genau die
    Antwortklasse, gegen die SYN-P0-006 angetreten ist."""
    r = su.foliant_suche_bestand(kategorie="monster", hg="abc")
    assert "fehler" in r and r["treffer"] == []
    assert "KEIN 'nicht im Bestand'" in r["hinweis"]
    # Die echten Schreibweisen der Statbloecke bleiben gueltig:
    for gueltig in ("0", "1", "1/4", "1/2"):
        assert "fehler" not in su.foliant_suche_bestand(kategorie="monster", hg=gueltig), gueltig
