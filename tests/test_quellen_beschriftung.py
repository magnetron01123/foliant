"""Der Beschriftungs-Standard fuer Quellen (importer/quellen.py).

Eine Quelle wird ueberall mit denselben drei Angaben beschrieben: WELCHES BUCH
(`titel`), WELCHE SPRACHE (`sprache`), WELCHER REGELSTAND (`edition`). Vorher hing jeder
Importweg einen anderen Klammer-Zusatz an denselben Werktitel - "SRD 5.2.1 (Deutsch)",
"Player's Handbook (D&D Beyond)", "Basic Rules (2014) (D&D Beyond)". Die Zusaetze
wiederholten nur, was daneben als eigene Spalte steht, und weil jeder Weg es anders tat,
waren die Quellen nebeneinander nicht mehr vergleichbar.
"""
from __future__ import annotations

import sqlite3
import types
from pathlib import Path

import pytest

from importer.quellen import normalisiere_titel, registriere_quelle, werktitel


@pytest.mark.parametrize("roh, erwartet", [
    # Weg: Sprache, Regelversion, Bezugsweg - auch zwei Klammern hintereinander.
    ("SRD 5.2.1 (Deutsch)", "SRD 5.2.1"),
    ("Basic Rules (2014) (D&D Beyond)", "Basic Rules"),
    ("Spielerhandbuch (Deutsch, 2014er Regeln)", "Spielerhandbuch"),
    ("Eberron: Forge of the Artificer (Druck)", "Eberron: Forge of the Artificer"),
    ("System Reference Document 5.2 (Open5e)", "System Reference Document 5.2"),
    # Bleibt: alles, was zum Werknamen gehoert. Lieber ein ungekuerzter Titel als ein
    # abgeschnittener Werkname.
    ("Monstrous Compendium Vol. 1 (Spelljammer Creatures)",
     "Monstrous Compendium Vol. 1 (Spelljammer Creatures)"),
    ("Curse of Strahd: Character Options", "Curse of Strahd: Character Options"),
    # Ein Titel, der NUR aus dem Zusatz besteht, wird nicht zu einer leeren Zeile.
    ("(Deutsch)", "(Deutsch)"),
    ("", ""),
    # Einheitlich auch im Kleinen: derselbe Verlag schreibt beide Apostroph-Formen.
    ("Elemental Evil Player's Companion", "Elemental Evil Player’s Companion"),
    ("  Doppelte   Leerzeichen ", "Doppelte Leerzeichen"),
])
def test_werktitel_entfernt_nur_die_doppelten_angaben(roh, erwartet):
    assert werktitel(roh) == erwartet


def _leere_db() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE quellen (id INTEGER PRIMARY KEY, kuerzel TEXT UNIQUE, "
                "titel TEXT, sprache TEXT, edition TEXT, herkunft TEXT, lizenz TEXT, "
                "prioritaet INTEGER, dateipfad TEXT, inhaltsart TEXT)")
    return con


def test_registrieren_schreibt_den_standard_statt_ihn_der_anzeige_zu_ueberlassen():
    """Der Standard greift beim SCHREIBEN. Sonst muesste ihn jede Ausgabe (Website,
    Belegzeile, admin) einzeln nachbauen - und die Fassungen liefen wieder auseinander."""
    con = _leere_db()
    registriere_quelle(con, kuerzel="ddb-phb", titel="Player's Handbook (D&D Beyond)",
                       sprache="en", edition="2024", herkunft="ddb")
    assert con.execute("SELECT titel FROM quellen").fetchone()[0] == "Player’s Handbook"


def test_bestand_zieht_ohne_re_import_nach():
    """Die Titel im Bestand stammen aus der Zeit vor dem Standard. Ohne diesen Schritt
    wuerden sie erst beim naechsten Re-Import gerade gezogen - fuer ein DDB-Buch also
    womoeglich nie."""
    con = _leere_db()
    con.executemany(
        "INSERT INTO quellen (kuerzel, titel, sprache, edition, herkunft) "
        "VALUES (?,?,?,?,?)",
        [("srd-de", "SRD 5.2.1 (Deutsch)", "de", "2024", "pdf"),
         ("mcv1", "Monstrous Compendium Vol. 1 (Spelljammer Creatures)", "en", "2014",
          "ddb")])

    assert normalisiere_titel(con) == 1          # nur der echte Zusatz faellt
    assert normalisiere_titel(con) == 0          # idempotent
    titel = dict(con.execute("SELECT kuerzel, titel FROM quellen"))
    assert titel["srd-de"] == "SRD 5.2.1"
    assert titel["mcv1"] == "Monstrous Compendium Vol. 1 (Spelljammer Creatures)"


def test_erzeuger_haengen_den_bezugsweg_nicht_mehr_an_den_titel():
    """Die Zusaetze entstanden nicht in der Config, sondern im Code: der DDB-Katalog und
    der Open5e-Importer bauten sie in den Titel. Wird das rueckgaengig gemacht, muss es
    rueckgaengig BLEIBEN - sonst kommen sie beim naechsten Import stillschweigend wieder."""
    from pathlib import Path

    for datei, verbot in (("importer/ddb_exporter/katalog.py", '(D&D Beyond)"'),
                          ("importer/import_open5e.py", '(Open5e)"')):
        quelltext = Path(datei).read_text(encoding="utf-8")
        for zeile in quelltext.splitlines():
            if "titel" in zeile and verbot in zeile and not zeile.lstrip().startswith("#"):
                pytest.fail(f"{datei}: Bezugsweg wieder im Titel - {zeile.strip()}")


def test_auffrischen_aendert_metadaten_und_laesst_eintraege_stehen(tmp_path, monkeypatch,
                                                                   capsys):
    """`admin quellen-auffrischen` ist der Weg fuer eine korrigierte Zeichenkette im
    Titel - hier der real aufgetretene OCR-Fehler im ersten Buchstaben ('Ianathars' statt
    'Xanathars'). Ein Re-Import waere dafuer der falsche Hebel: er spielt die rohen
    OCR-Namen der 2014-Scans wieder ein und macht deren Namensreparatur zunichte
    (CLAUDE.md). Der Test haelt beides fest - die Metadaten aendern sich, die Eintraege
    bleiben Zeichen fuer Zeichen stehen."""
    from app import admin, db as _db
    from tests.hilfen import neue_db

    pfad = tmp_path / "bestand.sqlite"
    con = neue_db(pfad)
    con.execute("INSERT INTO quellen (kuerzel,titel,sprache,edition,herkunft,lizenz,"
                "prioritaet) VALUES ('xgte-2014-de','Ianathars Ratgeber (Deutsch)','de',"
                "'2014','pdf','privat',85)")
    con.execute("INSERT INTO eintraege (quelle_id,kategorie,name_de,sprache,edition,"
                "body_md) VALUES (1,'regel','Trefferwürfel','de','2014','Repariert.')")
    con.commit()
    con.close()

    monkeypatch.setattr(_db, "lade_konfig", lambda: {"quelle": [
        {"kuerzel": "xgte-2014-de", "titel": "Xanathars Ratgeber für Alles",
         "sprache": "de", "edition": "2014", "herkunft": "pdf", "lizenz": "privat",
         "prioritaet": 85},
        # Ein Block OHNE importierte Eintraege wird NICHT angelegt - sonst stuende eine
        # leere Quelle auf der Website.
        {"kuerzel": "gibt-es-nicht", "titel": "Nie importiert", "sprache": "de",
         "edition": "2024", "herkunft": "pdf"},
    ]})
    monkeypatch.setattr(admin, "_web_db_auffrischen", lambda *_a, **_k: None)
    admin.cmd_quellen_auffrischen(types.SimpleNamespace(db=str(pfad)))

    con = sqlite3.connect(pfad)
    con.row_factory = sqlite3.Row
    quellen = {r["kuerzel"]: r["titel"] for r in con.execute(
        "SELECT kuerzel, titel FROM quellen")}
    assert quellen == {"xgte-2014-de": "Xanathars Ratgeber für Alles"}
    eintraege = con.execute("SELECT name_de, body_md FROM eintraege").fetchall()
    assert [tuple(r) for r in eintraege] == [("Trefferwürfel", "Repariert.")]
    con.close()
    assert "Ianathars" in capsys.readouterr().out          # die Aenderung wird benannt


def test_auffrischen_nimmt_einem_setting_band_nicht_den_spoilerschutz(tmp_path,
                                                                      monkeypatch):
    """Real passiert am 31.07.2026, beim ERSTEN Lauf des Kommandos auf dem Pi: Der
    Config-Block von 'efota-en' fuehrt kein `inhaltsart`. Weil die Auffrischung fuer
    fehlende Werte den Import-Standard einsetzte, wurde aus 'abenteuer_setting' still
    'regelwerk' - ein Setting-Band ohne Spoiler-Schutz, also ohne die OBERSTE
    Verhaltensregel (SPEC.md par. 7). Kein Fehler, keine Warnung, nur eine fehlende
    Kennzeichnung im Chat.

    Die Regel dagegen: Was die Config nicht sagt, bleibt stehen. Ein Import darf
    Standardwerte setzen (er baut die Quelle neu auf) - eine Auffrischung nie."""
    from app import admin, db as _db
    from tests.hilfen import neue_db

    pfad = tmp_path / "bestand.sqlite"
    con = neue_db(pfad)
    con.execute("INSERT INTO quellen (kuerzel,titel,sprache,edition,herkunft,lizenz,"
                "prioritaet,inhaltsart,dateipfad) VALUES ('efota-en','Alter Titel','en',"
                "'2024','pdf','privat',45,'abenteuer_setting','quellen/md/efota.md')")
    con.commit()
    con.close()

    # Config-Block wie auf dem Pi: NUR der Titel geaendert, kein inhaltsart, kein
    # dateipfad, keine Lizenz.
    monkeypatch.setattr(_db, "lade_konfig", lambda: {"quelle": [
        {"kuerzel": "efota-en", "titel": "Eberron: Forge of the Artificer",
         "sprache": "en", "edition": "2024", "herkunft": "pdf"}]})
    monkeypatch.setattr(admin, "_web_db_auffrischen", lambda *_a, **_k: None)
    admin.cmd_quellen_auffrischen(types.SimpleNamespace(db=str(pfad)))

    con = sqlite3.connect(pfad)
    con.row_factory = sqlite3.Row
    q = dict(con.execute("SELECT * FROM quellen").fetchone())
    con.close()
    assert q["titel"] == "Eberron: Forge of the Artificer"      # die Config gewinnt
    assert q["inhaltsart"] == "abenteuer_setting"               # ... aber nur, wo sie spricht
    assert q["lizenz"] == "privat" and q["prioritaet"] == 45
    assert q["dateipfad"] == "quellen/md/efota.md"


def test_jede_seeder_marke_gilt_als_eigene_ableitung():
    """Die Website weist getrennt aus, was von dnddeutsch.de uebernommen und was Foliant
    selbst am Bestand belegt hat. Unterschieden wird an Marken in `glossar.quelle`, die
    unsere eigenen Seeder setzen - und die stehen ueber mehrere Module verstreut. Kommt
    ein Seeder dazu, dessen Marke `app.glossar.EIGENE_ABLEITUNG_MARKEN` nicht kennt,
    zaehlen seine Zeilen still zu dnddeutsch.de: eine falsche Zuschreibung, die niemandem
    auffiele, weil nur eine Zahl um ein paar Hundert danebenliegt.

    Gesucht wird deshalb im QUELLTEXT aller Module, nicht in einer zweiten Liste - und
    ueber `rglob`, weil ein kuenftiger Seeder weder 'srd_*' heissen noch in
    import_glossar.py liegen muss."""
    import re
    from pathlib import Path

    from app.glossar import ist_eigene_ableitung

    marken = set()
    for datei in sorted(Path("importer").rglob("*.py")) + sorted(Path("app").rglob("*.py")):
        text = datei.read_text(encoding="utf-8")
        marken |= set(re.findall(r'^\w*QUELLE\w* = "([^"]+)"', text, re.M))
        marken |= set(re.findall(r'_upsert\([^)]*?,\s*[01],\s*"([^"]+)"', text, re.S))
        marken |= set(re.findall(r"quelle = '([^']+)'", text))

    assert len(marken) >= 8, f"Marken nicht gefunden - Regex pruefen: {sorted(marken)}"
    unbekannt = sorted(m for m in marken if not ist_eigene_ableitung(m))
    assert not unbekannt, (
        f"Diese Seeder-Marken zaehlt die Website faelschlich zu dnddeutsch.de: "
        f"{unbekannt} - app.glossar.EIGENE_ABLEITUNG_MARKEN ergaenzen.")


def test_import_ohne_inhaltsart_wird_abgelehnt(tmp_path, monkeypatch, capsys):
    """Die einzige Stelle, an der eine NEUE Quelle die oberste Verhaltensregel verlieren
    konnte: fehlte `inhaltsart` im [[quelle]]-Block, galt still 'regelwerk' - ein
    Abenteuerband landete dann ohne Spoiler-Schutz im Bestand, ohne Fehler und ohne
    Warnung. Seit dem 31.07.2026 ist der Wert Pflicht wie `edition` (Regel 1: nichts wird
    geraten). Lieber ein abgelehnter Import als ein ungekennzeichneter Band."""
    from app import admin, db as _db
    from tests.hilfen import neue_db

    pfad = tmp_path / "bestand.sqlite"
    neue_db(pfad).close()
    md = tmp_path / "band.md"
    md.write_text("# Ein Kapitel\n\nGenug Text fuer einen Eintrag im Bestand.\n",
                  encoding="utf-8")
    block = {"kuerzel": "neu-de", "titel": "Ein neuer Band", "sprache": "de",
             "edition": "2024", "herkunft": "pdf", "dateipfad": str(md)}
    monkeypatch.setattr(_db, "lade_konfig", lambda: {"quelle": [block]})
    monkeypatch.setattr(_db, "projekt_pfad", lambda p: Path(p))
    monkeypatch.setattr(admin, "_web_db_auffrischen", lambda *_a, **_k: None)

    with pytest.raises(SystemExit) as abbruch:
        admin.cmd_import(types.SimpleNamespace(quelle="neu-de", db=str(pfad), force=False))
    meldung = str(abbruch.value)
    assert "inhaltsart fehlt" in meldung
    assert "abenteuer_setting" in meldung and "regelwerk" in meldung   # beide Werte genannt
    # Und der Bestand ist unangetastet geblieben.
    con = sqlite3.connect(pfad)
    assert con.execute("SELECT count(*) FROM quellen").fetchone()[0] == 0
    con.close()


def test_verschriebene_inhaltsart_wird_nicht_als_regelwerk_verbucht():
    """Der Wert wird gegen die erlaubten geprueft, nicht nur auf Anwesenheit. Alles
    ausser 'abenteuer_setting' gilt naemlich als Regelwerk - ein verschriebenes
    'abenteur_setting' naehme einem Band also genauso still den Spoiler-Schutz.

    `db/schema.sql` traegt dafuer eine CHECK-Klausel, aber nur in FRISCH angelegten
    Datenbanken. Auf dem Pi kam die Spalte per ALTER TABLE dazu; dort gibt es sie nicht
    (am 31.07.2026 nachgesehen) - die Pruefung im Code ist also die einzige."""
    con = _leere_db()
    with pytest.raises(ValueError, match="inhaltsart"):
        registriere_quelle(con, kuerzel="x", titel="X", sprache="de", edition="2024",
                           herkunft="pdf", inhaltsart="abenteur_setting")
    assert con.execute("SELECT count(*) FROM quellen").fetchone()[0] == 0
