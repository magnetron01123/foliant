"""Tests fuer den DDB-Exporter (importer/ddb_exporter/) - vollstaendig offline mit
Mock-Transport und synthetischen Daten; keine echten Secrets, Texte oder API-Antworten.

Laufen in der Haupt-Suite, mit Ausnahme der DB3-Leser-Tests (brauchen apsw-sqlite3mc
aus .venv-ddb und werden sonst uebersprungen)."""
import io
import json
import zipfile
from pathlib import Path

import pytest

# Exporter-Abhaengigkeiten (markdownify/bs4) leben nur in .venv-ddb (requirements-ddb.txt)
# - in der Runtime-Suite werden diese Tests komplett uebersprungen.
pytest.importorskip("markdownify", reason="DDB-Exporter-Tests nur in .venv-ddb")

from importer.ddb_exporter import artifact, book_archive
from importer.ddb_exporter.ddb_client import BUCH_ENTITY_TYPE, DdbClient, DdbFehler
from importer.ddb_exporter.html_to_markdown import bereinige_html, html_zu_markdown

_COBALT = "synthetisches-testtoken-nie-echt"


class _Antwort:
    def __init__(self, status_code=200, daten=None, roh=b""):
        self.status_code = status_code
        self._daten = daten
        self._roh = roh

    def json(self):
        if self._daten is None:
            raise ValueError("kein JSON")
        return self._daten


class _Transport:
    """Mock fuer httpx: URL-Suffix -> Antwort(en); zeichnet alle Aufrufe auf."""
    def __init__(self, antworten):
        self.antworten = antworten
        self.aufrufe: list[tuple[str, dict]] = []

    def post(self, url, json=None, data=None, headers=None):
        self.aufrufe.append((url, {"json": json, "data": data, "headers": headers}))
        for suffix, antwort in self.antworten.items():
            if url.endswith(suffix):
                if isinstance(antwort, list):
                    return antwort.pop(0)
                return antwort
        return _Antwort(404)


def _ok(daten):
    return _Antwort(200, {"status": "success", "data": daten})


# ------------------------------- DdbClient -------------------------------

def test_owned_filter_streng():
    """Referenz-Struktur (Muncher, 11.07.2026): Licenses[] -> Entities[]. Nur
    EntityTypeID==Sourcebook UND isOwned==true; geteilte/fremde fliegen raus."""
    transport = _Transport({"available-user-content": _ok({"Licenses": [
        {"EntityTypeID": BUCH_ENTITY_TYPE, "Entities": [
            {"id": 1, "name": "Eigenes Buch", "isOwned": True},
            {"id": 2, "name": "Geteiltes Buch", "isOwned": False},
        ]},
        {"EntityTypeID": 12345, "Entities": [
            {"id": 3, "name": "Kein Buch", "isOwned": True}]},
    ]})})
    buecher = DdbClient(transport, _COBALT).eigene_buecher()
    assert buecher == [{"id": 1, "name": "Eigenes Buch"}]


def test_unerwartete_struktur_diagnose_secret_frei():
    """Struktur-Fehler nennen Key-Namen und Typen - niemals Werte oder das Token."""
    transport = _Transport({"available-user-content": _Antwort(200, {
        "status": "success", "data": {"Voellig": {"Anders": ["geheimer-wert-123"]}}})})
    with pytest.raises(DdbFehler) as info:
        DdbClient(transport, _COBALT).eigene_buecher()
    meldung = str(info.value)
    assert "Voellig" in meldung and "Anders" in meldung      # Key-Namen: ja
    assert "geheimer-wert-123" not in meldung                # Werte: nie
    assert _COBALT not in meldung


def test_auth_fehler_ohne_retry():
    """401/403: sofortiger Abbruch, KEIN automatischer Retry (O5)."""
    transport = _Transport({"user-data": _Antwort(401)})
    with pytest.raises(DdbFehler, match="401"):
        DdbClient(transport, _COBALT).pruefe_token()
    assert len(transport.aufrufe) == 1


def test_anonyme_sitzung_wird_abgelehnt():
    """DDB lehnt ungueltige Tokens nicht ab, sondern antwortet anonym (Fund 11.07.2026)
    - ohne userId in user-data gilt der Token als ungueltig, sonst blieben gekaufte
    Inhalte unsichtbar."""
    transport = _Transport({"user-data": _ok({})})
    with pytest.raises(DdbFehler, match="ANONYM"):
        DdbClient(transport, _COBALT).pruefe_token()
    ok = _Transport({"user-data": _ok({"userId": 7, "userDisplayName": "TestSpieler"})})
    assert DdbClient(ok, _COBALT).pruefe_token() == "TestSpieler"


def test_5xx_begrenzter_retry(monkeypatch):
    """5xx: begrenzte Wiederholungen mit Backoff, dann klarer Fehler."""
    import importer.ddb_exporter.ddb_client as dc
    monkeypatch.setattr(dc.time, "sleep", lambda s: None)
    transport = _Transport({"user-data": [_Antwort(503), _Antwort(503), _Antwort(503)]})
    with pytest.raises(DdbFehler, match="503"):
        DdbClient(transport, _COBALT).pruefe_token()
    assert len(transport.aufrufe) == 3

    transport2 = _Transport({"user-data": [_Antwort(503), _ok({"userId": 7})]})
    DdbClient(transport2, _COBALT).pruefe_token()          # zweiter Versuch gewinnt
    assert len(transport2.aufrufe) == 2


def test_fehlermeldungen_sind_secret_frei():
    """Weder Cobalt noch signierte URL-Querystrings erscheinen in Fehlermeldungen."""
    transport = _Transport({"get-book-url/7": _Antwort(500)})
    client = DdbClient(transport, _COBALT)
    import importer.ddb_exporter.ddb_client as dc
    dc.time.sleep, alt = (lambda s: None), dc.time.sleep
    try:
        with pytest.raises(DdbFehler) as info:
            client.buch_url(7)
    finally:
        dc.time.sleep = alt
    assert _COBALT not in str(info.value)
    # Cobalt geht NUR als token-Formfeld raus (Referenz-Auth), nie in URL oder JSON:
    for url, kw in transport.aufrufe:
        assert _COBALT not in url and kw["json"] is None
        assert kw["data"]["token"] == _COBALT
        assert kw["headers"]["Content-Type"] == "application/x-www-form-urlencoded"
        assert "Cookie" not in kw["headers"]


def test_buch_schluessel_form_encoded_und_base64():
    """book-codes laeuft FORM-encoded (token + sources-JSON-String) und der Schluessel
    kommt Base64-codiert zurueck - dekodiert wird zum Klartext (Referenz: Muncher)."""
    import base64
    schluessel_b64 = base64.b64encode(b"klartext-schluessel-7").decode()
    transport = _Transport({"book-codes": _ok([
        {"sourceID": 7, "data": schluessel_b64}])})
    assert DdbClient(transport, _COBALT).buch_schluessel(7) == "klartext-schluessel-7"
    url, kw = transport.aufrufe[-1]
    assert kw["json"] is None and kw["data"]["token"] == _COBALT     # form, nicht JSON
    assert json.loads(kw["data"]["sources"]) == [{"sourceID": 7, "versionID": None}]
    assert kw["headers"]["Content-Type"] == "application/x-www-form-urlencoded"
    with pytest.raises(DdbFehler, match="42"):
        DdbClient(_Transport({"book-codes": _ok([])}), _COBALT).buch_schluessel(42)


# ------------------------------- book_archive -------------------------------

def _zip_bytes(dateien: dict[str, bytes]) -> bytes:
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w") as z:
        for name, inhalt in dateien.items():
            z.writestr(name, inhalt)
    return puffer.getvalue()


def test_zip_slip_und_mehrdeutige_db_abgelehnt(tmp_path):
    boese = _zip_bytes({"../ausbruch.db3": b"x"})
    (tmp_path / "boese.zip").write_bytes(boese)
    with pytest.raises(book_archive.ArchivFehler, match="Slip"):
        book_archive.extrahiere_buch_db(tmp_path / "boese.zip", tmp_path / "work")

    zwei = _zip_bytes({"a.db3": b"x", "b.db3": b"y"})
    (tmp_path / "zwei.zip").write_bytes(zwei)
    with pytest.raises(book_archive.ArchivFehler, match="EINE"):
        book_archive.extrahiere_buch_db(tmp_path / "zwei.zip", tmp_path / "work")

    keine = _zip_bytes({"nur-text.txt": b"x"})
    (tmp_path / "keine.zip").write_bytes(keine)
    with pytest.raises(book_archive.ArchivFehler, match="EINE"):
        book_archive.extrahiere_buch_db(tmp_path / "keine.zip", tmp_path / "work")


def test_gueltiges_archiv_extrahiert_genau_die_db(tmp_path):
    gut = _zip_bytes({"buch/inhalt.db3": b"DB3-BYTES", "buch/version.txt": b"1"})
    (tmp_path / "gut.zip").write_bytes(gut)
    db3 = book_archive.extrahiere_buch_db(tmp_path / "gut.zip", tmp_path / "work")
    assert db3.read_bytes() == b"DB3-BYTES"
    assert not (tmp_path / "work" / "version.txt").exists()   # nur die DB3


class _StreamTransport:
    def __init__(self, bloecke, status=200):
        self._bloecke, self._status = bloecke, status

    def stream(self, methode, url):
        aussen = self

        class _Ctx:
            status_code = aussen._status

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def iter_bytes(self):
                yield from aussen._bloecke
        return _Ctx()


def test_download_streamt_atomar(tmp_path):
    ziel = tmp_path / "buch.zip"
    inhalt = _zip_bytes({"x.db3": b"y"})
    pfad = book_archive.lade_archiv(_StreamTransport([inhalt]), "https://s/x", ziel)
    assert pfad == ziel and ziel.read_bytes() == inhalt
    assert not ziel.with_suffix(".zip.part").exists()

    with pytest.raises(book_archive.ArchivFehler, match="Signatur"):
        book_archive.lade_archiv(_StreamTransport([b"kein zip"]), "https://s/x",
                                 tmp_path / "kaputt.zip")
    assert not (tmp_path / "kaputt.zip").exists()
    assert not (tmp_path / "kaputt.zip.part").exists()        # .part aufgeraeumt


# ------------------------------- HTML -> Markdown -------------------------------

def test_html_bereinigung_und_gfm():
    html = ("<h2>Kapitel</h2><script>boese()</script><p onclick='x()'>Text mit "
            "<a href='/spells/1'>Link</a> und <a href='javascript:alert(1)'>Skript</a>."
            "</p><img src='x.png' alt='Karte der Ebene'>"
            "<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>")
    md = html_zu_markdown(html)
    assert "## Kapitel" in md
    assert "boese" not in md and "onclick" not in md and "javascript:" not in md
    assert "[Link](https://www.dndbeyond.com/spells/1)" in md   # DDB-Link normalisiert
    assert "Skript" in md                                        # Text bleibt, Link weg
    assert "[Bild: Karte der Ebene]" in md
    assert "| A | B |" in md and "| 1 | 2 |" in md               # GFM-Tabelle
    assert "onclick" not in bereinige_html(html)
    # Interne ddb://-Verweise werden auf reinen Text reduziert (saubere Namen):
    ddb = html_zu_markdown("<h3><a href='ddb://monsters/6491381'>Priest of Osybus</a></h3>")
    assert ddb == "### Priest of Osybus" and "ddb://" not in ddb
    # Auch NACKTE ddb://-URLs im Text werden entfernt (QS-Fund):
    bare = html_zu_markdown("<p>Siehe ddb://compendium/items/orb und mehr.</p>")
    assert "ddb://" not in bare and "Siehe" in bare


# ------------------------------- Artefakt-Schreiber -------------------------------

_BUCH = {"id": 999999, "kuerzel": "ddb-synthetic-en", "titel": "Synthetic Handbook",
         "sprache": "en", "edition": "2024", "lizenz": "privat", "prioritaet": 40}

_CONTENT = [
    {"id": 1, "cobalt_id": "c1", "parent_id": None, "slug": "spells",
     "title": "Spells", "html": "<h1>Spells</h1><p>Uebersicht.</p>"},
    {"id": 2, "cobalt_id": "c2", "parent_id": 1, "slug": "spells-a",
     "title": "Synthetic Bolt", "html": "<p>Ein erfundener Zauber.</p>"},
    {"id": 3, "cobalt_id": "c3", "parent_id": None, "slug": "leer",
     "title": "Leer", "html": "  "},
]


def test_baue_eintraege_hierarchie_kategorien_zaehler():
    eintraege, zaehler = artifact.baue_eintraege(_CONTENT, _BUCH["titel"],
                                                 html_zu_markdown)
    assert [e["ddb_id"] for e in eintraege] == ["1", "2"]        # leer uebersprungen
    assert zaehler["leer"] == 1 and zaehler["fehlende_parents"] == 0
    zauber = eintraege[1]
    assert zauber["breadcrumb"] == ["Synthetic Handbook", "Spells", "Synthetic Bolt"]
    assert zauber["category"] == "zauber"                        # via Breadcrumb
    assert zauber["source_url"].endswith("/sources/spells-a")


def test_schreibe_artefakt_atomar_und_validiert(tmp_path):
    eintraege, zaehler = artifact.baue_eintraege(_CONTENT, _BUCH["titel"],
                                                 html_zu_markdown)
    ziel = artifact.schreibe_artefakt(tmp_path, _BUCH, eintraege, zaehler,
                                      export_id="20260711T000000Z",
                                      exported_at="2026-07-11T00:00:00+00:00")
    assert ziel.name == "20260711T000000Z"
    assert not list(ziel.parent.glob(".partial-*"))
    manifest = json.loads((ziel / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["entry_count"] == 2 and manifest["empty_content_count"] == 1
    # Determinismus: gleicher Input -> identische entries.jsonl
    ziel2 = artifact.schreibe_artefakt(tmp_path, _BUCH, eintraege, zaehler,
                                       export_id="20260711T000001Z",
                                       exported_at="2026-07-11T00:00:01+00:00")
    assert (ziel / "entries.jsonl").read_bytes() == (ziel2 / "entries.jsonl").read_bytes()
    # Und: das fertige Artefakt laeuft durch den ECHTEN Offline-Import (Rundreise).
    from importer.import_ddb import importiere_ddb_artefakt
    import sqlite3
    oeffentlich = tmp_path / "foliant.sqlite"
    con = sqlite3.connect(oeffentlich)
    con.executescript((Path(__file__).resolve().parent.parent / "db" /
                       "schema.sql").read_text(encoding="utf-8"))
    con.commit(); con.close()
    bericht = importiere_ddb_artefakt(ziel, _BUCH, oeffentliche_db=oeffentlich,
                                      private_db=tmp_path / "p" / "privat.sqlite")
    # Der generische 'Spells'-Kapitel-Header wird beim Import BEWUSST verworfen
    # (QS 2026-07-11, _ist_kapitel_header) - nur der echte Zauber landet im Bestand.
    assert bericht["eintraege_neu"] == 1
    assert bericht["kategorien"] == {"zauber": 1}
    privat = sqlite3.connect(f"file:{tmp_path / 'p' / 'privat.sqlite'}?mode=ro", uri=True)
    namen = {r[0] for r in privat.execute("SELECT name_en FROM eintraege")}
    privat.close()
    assert namen == {"Synthetic Bolt"}          # 'Spells'-Stub gefiltert, Inhalt erhalten


def test_parent_zyklus_bricht_ab():
    zyklus = [{"id": 1, "parent_id": 2, "title": "A", "slug": "a", "html": "<p>x</p>"},
              {"id": 2, "parent_id": 1, "title": "B", "slug": "b", "html": "<p>y</p>"}]
    with pytest.raises(ValueError, match="Zyklus"):
        artifact.baue_eintraege(zyklus, "Buch", html_zu_markdown)


def test_strukturierte_eintraege_aus_detailtabellen(tmp_path):
    """Buecher ohne Content-Text: Einzeleintraege aus RPGSpell/RPGMonster + Text aus
    HTMLDescription (join ueber EntityTypeID+EntityID). Synthetische SQLCipher-DB."""
    apsw = pytest.importorskip("apsw", reason="Detailtabellen-Test braucht apsw-sqlite3mc")
    pfad = str(tmp_path / "book.db3")
    con = apsw.Connection(pfad)
    con.pragma("cipher", "sqlcipher"); con.pragma("legacy", 3); con.pragma("key", "k")
    con.execute("CREATE TABLE EntityType(ID, Name)")
    con.execute("INSERT INTO EntityType VALUES(1118725998,'RPGSpell'),(9,'RPGMonster')")
    con.execute("CREATE TABLE RPGSpell(ID, Name, Level)")
    con.execute("INSERT INTO RPGSpell VALUES(2367,'Synthetic Bolt',1)")
    con.execute("CREATE TABLE RPGMonster(ID, Name)")
    con.execute("INSERT INTO RPGMonster VALUES(55,'Asteroid Spider')")
    con.execute("CREATE TABLE HTMLDescription(ID, DisplayOrder, Text, EntityTypeID, EntityID)")
    con.execute("INSERT INTO HTMLDescription VALUES"
                "(1,0,'<p>A synthetic spell.</p>',1118725998,2367),"
                "(2,0,'<p>A synthetic monster.</p>',9,55)")
    con.close()

    from importer.ddb_exporter.book_archive import lies_strukturierte_eintraege
    zeilen = lies_strukturierte_eintraege(Path(pfad), "k")
    nach_kat = {z["category"]: z for z in zeilen}
    assert nach_kat["zauber"]["title"] == "Synthetic Bolt"
    assert "synthetic spell" in nach_kat["zauber"]["html"].lower()
    assert nach_kat["monster"]["title"] == "Asteroid Spider"

    eintraege, _ = artifact.baue_eintraege(zeilen, "Test Book", html_zu_markdown)
    kats = {e["category"] for e in eintraege}
    assert {"zauber", "monster"} <= kats
    zauber = next(e for e in eintraege if e["category"] == "zauber")
    assert zauber["breadcrumb"] == ["Test Book", "Synthetic Bolt"]


def test_edition_autoritativ_aus_buch_db(tmp_path):
    """V1/Q3: Edition kommt aus RPGSourceCategory.Name (explizit) bzw. ReleaseDate
    (< 2024 -> 2014); mehrdeutig -> None (Buch wird dann NICHT geraten geladen)."""
    apsw = pytest.importorskip("apsw", reason="Edition-Test braucht apsw-sqlite3mc")
    from importer.ddb_exporter.book_archive import lies_edition

    def _mach_db(pfad, kat_name, release, sid=99):
        con = apsw.Connection(str(pfad))
        con.pragma("cipher", "sqlcipher"); con.pragma("legacy", 3); con.pragma("key", "k")
        con.execute("CREATE TABLE RPGSourceCategory(ID, Name)")
        con.execute("INSERT INTO RPGSourceCategory VALUES(7,?)", (kat_name,))
        con.execute("CREATE TABLE RPGSource(ID, RPGSourceCategoryID, ReleaseDate)")
        con.execute("INSERT INTO RPGSource VALUES(?,7,?)", (sid, release))
        con.close()

    p1 = tmp_path / "a.db3"; _mach_db(p1, "5.5e Expanded Rules", "6/2/2026")
    assert lies_edition(Path(p1), "k", 99) == "2024"          # Kategorie explizit

    p2 = tmp_path / "b.db3"; _mach_db(p2, "2014 Expanded Rules", "4/21/2022")
    assert lies_edition(Path(p2), "k", 99) == "2014"          # Kategorie explizit

    p3 = tmp_path / "c.db3"; _mach_db(p3, "Critical Role", "3/17/2020")
    assert lies_edition(Path(p3), "k", 99) == "2014"          # ReleaseDate < 2024

    p4 = tmp_path / "d.db3"; _mach_db(p4, "Hidden Sources", "4/30/2025")
    assert lies_edition(Path(p4), "k", 99) is None            # mehrdeutig -> nicht raten
