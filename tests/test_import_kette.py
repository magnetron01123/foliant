"""Die Glossar-Kette hat GENAU EINEN Weg: `importer.import_glossar.seed_alles`, gerufen
von `admin import --quelle glossar`.

Vorgeschichte in zwei Stufen. Erst stand die Kette in `cmd_import` mit Importen INNERHALB
der Funktion - ein fehlender Name fiel dann erst nach Minuten echter Arbeit auf (real am
27.07.2026: der Zauber-Seeder war eingereiht, aber nicht importiert). Danach zeigte die
Konsolidierung den teureren Fehler: `importer/import_glossar.py` trug einen ZWEITEN
Einstiegspunkt, der nur sechs der Schritte fuhr - ohne Transaktion, ohne die
Namensreparaturen. Der schrieb kein kaputtes, sondern ein still UNVOLLSTAENDIGES Glossar,
und das Glossar entscheidet ueber '*'-Kennzeichnung (S5/S6), Suchbruecken (B3) und das
Deutsch-first-Ranking.

Beide Fehlerformen haben denselben Kern: ein Seeder existiert, laeuft aber nicht mit.
Genau darauf zielen die Tests hier - rein statisch, ohne DB."""
import ast
import inspect
import pathlib
import sqlite3
import types

import pytest

import importer.import_glossar as ig

from tests.hilfen import SCHEMA, WURZEL as _WURZEL
_ADMIN = _WURZEL / "app" / "admin.py"

# Praefixe der Schritte, die fachlich in die Kette gehoeren.
_SCHRITT_PRAEFIXE = ("seed_", "kanonisiere_", "repariere_")

# Bewusst NICHT in der Kette:
#   seed_alles   - IST die Kette, kein Schritt darin.
#   seed_glossar - nimmt eine Begriffsliste statt nur `con`; der Kettenschritt ist der
#                  Wrapper seed_glossar_kernbegriffe (ruft sie mit KERNBEGRIFFE_EN).
# Waechst diese Liste, ist das eine bewusste Entscheidung, kein Versehen.
_NICHT_IN_KETTE = {"seed_alles", "seed_glossar"}


def _funktion(baum, name):
    return next(k for k in ast.walk(baum)
                if isinstance(k, ast.FunctionDef) and k.name == name)


def test_kette_enthaelt_jeden_seeder_des_moduls():
    """Der Kern-Waechter: wer einen Seeder ergaenzt, aber nicht einreiht, faellt hier auf -
    nicht erst daran, dass ein Begriff auf Produktion ein '*' traegt, das er nicht haben
    sollte."""
    in_kette = {schritt.__name__ for schritt, _ in ig._KETTE}
    definiert = {name for name, obj in vars(ig).items()
                 if inspect.isfunction(obj) and obj.__module__ == ig.__name__
                 and name.startswith(_SCHRITT_PRAEFIXE)}
    fehlend = definiert - in_kette - _NICHT_IN_KETTE
    assert not fehlend, (
        f"in importer/import_glossar.py definiert, aber nicht in _KETTE: {sorted(fehlend)} "
        f"- entweder einreihen oder in _NICHT_IN_KETTE begruenden")


def test_jeder_kettenschritt_nimmt_nur_die_verbindung():
    """seed_alles ruft jeden Schritt als schritt(con). Ein Schritt mit weiteren
    PFLICHT-Parametern wuerde erst zur Laufzeit auffallen."""
    for schritt, beschriftung in ig._KETTE:
        pflicht = [p for p in inspect.signature(schritt).parameters.values()
                   if p.default is inspect.Parameter.empty
                   and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
        assert len(pflicht) == 1, f"{schritt.__name__}: erwartet genau (con), hat {pflicht}"
        assert beschriftung, f"{schritt.__name__}: Bilanz-Beschriftung fehlt"


def test_admin_ruft_die_kette_statt_einzelner_seeder():
    """Die Reihenfolge ist Fachwissen und gehoert der Fachschicht. Ruft die CLI wieder
    einzelne Seeder, gibt es zwei Orte, an denen sie steht - und damit zwei, die driften."""
    baum = ast.parse(_ADMIN.read_text(encoding="utf-8"))
    fn = _funktion(baum, "cmd_import")
    aufgerufen = {k.func.id for k in ast.walk(fn)
                  if isinstance(k, ast.Call) and isinstance(k.func, ast.Name)}
    assert "seed_alles" in aufgerufen, "cmd_import faehrt die Glossar-Kette nicht mehr"
    einzeln = {n for n in aufgerufen if n.startswith(_SCHRITT_PRAEFIXE)} - {"seed_alles",
                                                                           "seed_facetten"}
    assert not einzeln, (f"cmd_import ruft Seeder direkt: {sorted(einzeln)} - die Kette "
                         f"gehoert nach importer.import_glossar._KETTE")


@pytest.mark.parametrize("quelle", ["glossar", "facetten"])
def test_jeder_import_zweig_frischt_die_web_db_auf(tmp_path, monkeypatch, quelle):
    """Die Web-DB traegt Glossar UND Quellen-Metadaten - sie muss nach JEDEM Zweig
    nachgezogen werden.

    Bis zum 31.07.2026 kehrten die Zweige `glossar` und `facetten` frueh zurueck, vor
    dem Aufruf am Funktionsende. Ausgerechnet `--quelle glossar` ist aber der einzige
    Zweig, der das Glossar aendert - also genau den Inhalt, den die Web-DB ueberhaupt
    ueberträgt. Die Website zeigte danach bis zum naechsten Quellen-Import einen alten
    Stand, und seit sie die Buchliste zeigt, faellt das auch auf."""
    from app import admin

    db = tmp_path / "foliant.sqlite"
    sqlite3.connect(db).executescript(
        SCHEMA.read_text(encoding="utf-8"))
    gerufen: list[str | None] = []
    monkeypatch.setattr(admin, "_web_db_auffrischen", lambda p: gerufen.append(p))
    monkeypatch.setattr(ig, "seed_alles", lambda con: {"Testzeilen": 0})
    monkeypatch.setattr("importer.facetten_seeder.seed_facetten", lambda con: {"zauber": 0})

    admin.cmd_import(types.SimpleNamespace(quelle=quelle, db=str(db), force=False))
    assert gerufen, (f"`import --quelle {quelle}` hat die Web-DB nicht aufgefrischt - "
                     f"die Website bleibt auf dem alten Stand stehen")


def test_kein_zweiter_einstiegspunkt_in_den_importern():
    """Ein `if __name__ == '__main__'` in einem Importer ist ein zweiter Prozessweg neben
    `app.admin` - und zwar einer, den keine der vier Doku-Dateien kennt. Genau so entstand
    der unvollstaendige Glossar-Lauf. Ausnahme ist ddb_exporter: der ist ausdruecklich ein
    eigener, kurzlebiger Prozess OHNE DB-Zugriff (CONCEPT.md par. 10, ADR)."""
    treffer = [p.relative_to(_WURZEL).as_posix()
               for p in (_WURZEL / "importer").rglob("*.py")
               if "ddb_exporter" not in p.parts
               and '__name__ == "__main__"' in p.read_text(encoding="utf-8")]
    assert not treffer, (f"zweiter Einstiegspunkt neben app.admin: {treffer} - Importe "
                         f"laufen ueber `python -m app.admin import`")


def test_kettenschritte_committen_nicht_selbst():
    """Statischer Waechter: kein Schritt darf `con.commit()` rufen.

    `seed_alles` und der Kommentar in `app/admin.py` sagen beide "EINE Transaktion, ganz
    oder gar nicht" zu - bis zum 31.07.2026 trugen aber 15 der Schritte ihr eigenes
    Commit, was genau diese Zusage aufhob. Ein neuer Schritt mit Commit faellt hier auf,
    nicht erst an einem halb geschriebenen Glossar nach einem Abbruch."""
    baum = ast.parse((_WURZEL / "importer" / "import_glossar.py").read_text(encoding="utf-8"))
    schuldige = sorted({
        fn.name for fn in ast.walk(baum) if isinstance(fn, ast.FunctionDef)
        for k in ast.walk(fn)
        if isinstance(k, ast.Call) and isinstance(k.func, ast.Attribute)
        and k.func.attr == "commit"})
    assert not schuldige, (
        f"Kettenschritt(e) mit eigenem Commit: {schuldige} - die Transaktion fuehrt der "
        f"Aufrufer (`with con: seed_alles(con)`), sonst ist die Kette nicht atomar")


def test_abbruch_mitten_in_der_kette_laesst_das_glossar_unveraendert(tmp_path, monkeypatch):
    """Der reale Fehlerfall vom 27.07.2026: ein Schritt wirft nach Minuten Laufzeit.

    Erwartung: Das Glossar steht danach exakt auf dem Stand VOR dem Lauf. Ohne die
    Transaktion haetten die vorherigen Schritte ihre Zeilen bereits committet, und die
    spaeteren Kanonisierer (die die Konflikte aufloesen) waeren nie gelaufen - ein still
    unvollstaendiges Glossar, das ueber '*'-Kennzeichnung und Deutsch-first-Ranking
    entscheidet."""
    db = tmp_path / "foliant.sqlite"
    con = sqlite3.connect(db)
    con.executescript(SCHEMA.read_text(encoding="utf-8"))
    con.execute("INSERT INTO glossar (term_en, term_de, offiziell, quelle) "
                "VALUES ('Fireball','Feuerball',1,'Test')")
    con.commit()

    def schritt_wirft(c):
        raise RuntimeError("NameError-Aequivalent mitten in der Kette")

    # ERSTER Schritt ist ein ECHTER Kettenschritt (netzfrei, schreibt Glossarzeilen).
    # Nur so misst der Test die Sache: mit einem selbstgebauten Schritt wuerde er auch
    # ohne den Fix bestehen, weil der Schritt dann gar kein Commit mitbringt.
    monkeypatch.setattr(ig, "_KETTE", [(ig.seed_abkuerzungen, "Abkuerzungen"),
                                       (schritt_wirft, "kaputt")])
    with pytest.raises(RuntimeError):
        with con:
            ig.seed_alles(con)

    pruef = sqlite3.connect(db)
    try:
        zeilen = pruef.execute("SELECT term_en FROM glossar").fetchall()
    finally:
        pruef.close()
    assert zeilen == [("Fireball",)], (
        f"Teilzustand nach dem Abbruch: {zeilen} - die Kette ist nicht atomar")
