"""DDB-Spike Schritt 1-2 (docs/ddb-spike-runbook.md), als Test dokumentiert:
apsw-sqlite3mc kann auf dieser Maschine SQLCipher-v3-Datenbanken erstellen und
READONLY wieder oeffnen - mit den EXPLIZITEN Legacy-Parametern (keine stillen
Bibliotheksdefaults, Vorschlag §6.1).

`legacy=3` entspricht dem SQLCipher-v3-Profil: 1.024-Byte-Seiten, 64.000
KDF-Iterationen, SHA-1 fuer KDF/HMAC - das Format der DDB-Buchdatenbanken laut
Referenz (SQLite3 Multiple Ciphers-Doku, utelle.github.io).

Laeuft nur, wenn apsw-sqlite3mc installiert ist (.venv-ddb, requirements-ddb.txt);
in der normalen Runtime-Suite wird er uebersprungen - SQLite3MC gehoert nie in die
dauerhafte Runtime. Der Test nutzt AUSSCHLIESSLICH synthetische Daten."""
import pytest

apsw = pytest.importorskip("apsw", reason="DDB-Spike: apsw-sqlite3mc nur in .venv-ddb")

_SCHLUESSEL = "synthetischer-testschluessel"


def _konfiguriere_sqlcipher_v3(con) -> None:
    """Explizite SQLCipher-v3-Parameter VOR dem Schluessel setzen (dokumentierte
    Annahme, nicht Bibliotheksdefault)."""
    con.pragma("cipher", "sqlcipher")
    con.pragma("legacy", 3)
    con.pragma("key", _SCHLUESSEL)


def test_sqlcipher_v3_erstellen_und_readonly_lesen(tmp_path):
    pfad = str(tmp_path / "sqlcipher-v3-synthetisch.db3")

    con = apsw.Connection(pfad)
    _konfiguriere_sqlcipher_v3(con)
    con.execute("CREATE TABLE Content (ID INTEGER PRIMARY KEY, CobaltID TEXT, "
                "ParentID INTEGER, Slug TEXT, Title TEXT, RenderedHTML TEXT)")
    con.execute("INSERT INTO Content VALUES (1, 'c-1', NULL, 'kap-1', 'Kapitel 1', "
                "'<p>Synthetischer Inhalt</p>')")
    con.close()

    # Verschluesselung greift: ohne Schluessel ist die Datei nicht lesbar.
    roh = apsw.Connection(pfad, flags=apsw.SQLITE_OPEN_READONLY)
    with pytest.raises(apsw.Error):
        roh.execute("SELECT count(*) FROM Content").fetchall()
    roh.close()

    # READONLY + korrekte Parameter: erste echte Leseabfrage beweist die Entschluesselung.
    ro = apsw.Connection(pfad, flags=apsw.SQLITE_OPEN_READONLY)
    _konfiguriere_sqlcipher_v3(ro)
    zeilen = ro.execute("SELECT ID, Slug, Title, RenderedHTML FROM Content").fetchall()
    assert zeilen == [(1, "kap-1", "Kapitel 1", "<p>Synthetischer Inhalt</p>")]
    ro.close()


def test_falscher_schluessel_scheitert(tmp_path):
    pfad = str(tmp_path / "sqlcipher-falscher-schluessel.db3")
    con = apsw.Connection(pfad)
    _konfiguriere_sqlcipher_v3(con)
    con.execute("CREATE TABLE t (x)")
    con.close()

    ro = apsw.Connection(pfad, flags=apsw.SQLITE_OPEN_READONLY)
    ro.pragma("cipher", "sqlcipher")
    ro.pragma("legacy", 3)
    ro.pragma("key", "voellig-falsch")
    with pytest.raises(apsw.Error):
        ro.execute("SELECT count(*) FROM t").fetchall()
    ro.close()
