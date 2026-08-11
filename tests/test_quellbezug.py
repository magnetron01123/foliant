"""Der Quellbezug holt eine fehlende Quelldatei aus ihrer `quell_url` (O2).

Alle Tests laufen OHNE Netz: `hole_wenn_fehlt` nimmt einen `lader`, damit die Zusagen
pruefbar sind, ohne von media.dndbeyond.com abzuhaengen. Was hier steht, sind die
Zusagen aus dem Modul-Docstring - vor allem die tragende: eine vorhandene Datei bleibt
unberuehrt.
"""
from __future__ import annotations

import hashlib

import pytest

from importer.quellbezug import MAX_BYTES, BezugFehler, hole_wenn_fehlt

PDF = b"%PDF-1.7\n... Inhalt ...\n%%EOF\n"
PDF_HASH = hashlib.sha256(PDF).hexdigest()


def _lader(nutzlast: bytes, protokoll: list | None = None):
    def lade(url, zeitlimit):
        if protokoll is not None:
            protokoll.append(url)
        return nutzlast
    return lade


# --- die tragende Regel ----------------------------------------------------------------

def test_vorhandene_datei_wird_nie_angefasst(tmp_path):
    """DIE Zusage des Moduls. Unter quellen/ liegen kuratierte und reparierte PDFs
    (Browser-Druck-Ausdrucke); ein Bezug, der sie ersetzt, macht Handarbeit lautlos
    zunichte - und zwar bei einem routinierten Re-Import, wo niemand damit rechnet."""
    ziel = tmp_path / "vorhanden.pdf"
    ziel.write_bytes(b"%PDF-1.4 muehsam repariert")
    gerufen = []

    assert hole_wenn_fehlt(ziel, "https://example.invalid/neu.pdf",
                           lader=_lader(PDF, gerufen)) is None
    assert ziel.read_bytes() == b"%PDF-1.4 muehsam repariert"
    assert gerufen == [], "die URL wurde ueberhaupt angefasst - der Lader lief"


def test_ohne_url_passiert_nichts(tmp_path):
    """Quellen ohne `quell_url` sind der Normalfall (gekaufte Buecher, Scans). None ist
    dort kein Fehler - der Aufrufer laeuft danach in seine eigene Meldung."""
    assert hole_wenn_fehlt(tmp_path / "fehlt.pdf", None, lader=_lader(PDF)) is None
    assert hole_wenn_fehlt(tmp_path / "fehlt.pdf", "", lader=_lader(PDF)) is None


# --- der Normalfall --------------------------------------------------------------------

def test_fehlende_datei_wird_geholt_und_gemeldet(tmp_path):
    ziel = tmp_path / "tief" / "errata.pdf"     # Verzeichnis existiert noch nicht
    meldung = hole_wenn_fehlt(ziel, "https://example.invalid/e.pdf", lader=_lader(PDF))

    assert ziel.read_bytes() == PDF
    assert PDF_HASH in meldung, "der sha256 gehoert in die Ausgabe (V10-Provenienz)"
    assert "quell_hash" in meldung, "ohne Hinweis bleibt der Hash-Pin ungenutzt"


def test_kein_teil_rest_nach_dem_schreiben(tmp_path):
    """Geschrieben wird ueber einen Kandidaten + os.replace. Bleibt eine `.teil`-Datei
    liegen, geht sie beim naechsten Lauf als 'ist ja da' durch und scheitert erst im
    Parser."""
    ziel = tmp_path / "e.pdf"
    hole_wenn_fehlt(ziel, "https://example.invalid/e.pdf", lader=_lader(PDF))
    assert list(tmp_path.iterdir()) == [ziel]


# --- was eine Antwort passieren muss ---------------------------------------------------

def test_http_wird_abgelehnt(tmp_path):
    with pytest.raises(BezugFehler, match="nicht https"):
        hole_wenn_fehlt(tmp_path / "e.pdf", "http://example.invalid/e.pdf",
                        lader=_lader(PDF))
    assert not (tmp_path / "e.pdf").exists()


def test_html_seite_mit_status_200_ist_keine_pdf(tmp_path):
    """Der haeufigste Fehlerfall bei freien Downloads: ein Portal liefert eine Anmelde-
    oder Cloudflare-Fehlerseite MIT HTTP 200. Ohne die Pruefung landete sie als
    `errata.pdf` im Bestand und faellt erst im PDF-Parser auf - mit einer Meldung, die
    auf die falsche Ursache zeigt."""
    ziel = tmp_path / "errata.pdf"
    with pytest.raises(BezugFehler, match="kein .pdf-Dokument"):
        hole_wenn_fehlt(ziel, "https://example.invalid/e.pdf",
                        lader=_lader(b"<!DOCTYPE html><title>Just a moment...</title>"))
    assert not ziel.exists(), "nichts geschrieben - sonst gilt der Muell beim naechsten"


def test_leere_antwort_ist_ein_fehler(tmp_path):
    with pytest.raises(BezugFehler, match="leere Antwort"):
        hole_wenn_fehlt(tmp_path / "e.pdf", "https://example.invalid/e.pdf",
                        lader=_lader(b""))


def test_unbekannte_endung_wird_nicht_auf_magie_geprueft(tmp_path):
    """Nur Formate mit eindeutiger Signatur werden geprueft. Ein Markdown-Bezug soll
    nicht daran scheitern, dass es fuer .md keine magischen Bytes gibt."""
    ziel = tmp_path / "quelle.md"
    hole_wenn_fehlt(ziel, "https://example.invalid/q.md", lader=_lader(b"# Titel\n"))
    assert ziel.read_text() == "# Titel\n"


# --- Hash-Pin (V10) --------------------------------------------------------------------

def test_passender_hash_pin_laeuft_durch(tmp_path):
    ziel = tmp_path / "e.pdf"
    meldung = hole_wenn_fehlt(ziel, "https://example.invalid/e.pdf",
                              erwarteter_hash=PDF_HASH, lader=_lader(PDF))
    assert ziel.exists()
    # Mit Pin KEIN Tipp mehr - er stuende sonst bei jedem Lauf da, obwohl er erledigt ist.
    assert "Tipp:" not in meldung


def test_abweichender_hash_bricht_ab_und_schreibt_nichts(tmp_path):
    """Derselbe URL, anderer Inhalt = eine neue Auflage. Wuerde sie stumm importiert,
    behauptete `versions_stand = "Errata Version 1.0"` etwas Falsches ueber den Bestand
    (Regel 2). Das ist eine Entscheidung, die im Diff stehen muss."""
    ziel = tmp_path / "e.pdf"
    with pytest.raises(BezugFehler, match="quell_hash passt nicht"):
        hole_wenn_fehlt(ziel, "https://example.invalid/e.pdf",
                        erwarteter_hash="a" * 64, lader=_lader(PDF))
    assert not ziel.exists()


# --- Deckel ----------------------------------------------------------------------------

def test_groessendeckel_greift_im_standard_lader():
    """Der Deckel sitzt im Lader, damit eine falsch konfigurierte URL den Datentraeger
    nicht fuellt. Geprueft wird die Grenze selbst, nicht httpx: der Wert ist die Zusage."""
    assert MAX_BYTES == 100 * 1024 * 1024
