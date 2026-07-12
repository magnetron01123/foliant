"""OCR-Vorstufe (importer/ocr_vorstufe.py): Triage-Befunde an ECHTEN Mini-PDFs
(mit PyMuPDF erzeugt - kein Mock, die Textschicht-Zaehlung ist der Kern) und der
pure ocrmypdf-Kommandobau. Der eigentliche OCR-Lauf braucht Tesseract und laeuft
nur dort, wo es installiert ist (Pi-Container) - hier uebersprungen."""
from __future__ import annotations

import shutil
import sys

import pytest

from importer.ocr_vorstufe import (MIN_ZEICHEN, SCAN_SCHWELLE, ocr_befehl,
                                   triagiere_pdf)

_TEXT = ("Feuerball (Fireball): Ein heller Lichtstreif schiesst auf einen Punkt deiner "
         "Wahl und explodiert dort mit einem dumpfen Grollen in einer Feuersbrunst. ")


def _baue_pdf(pfad, text_seiten: int, leer_seiten: int, duenn_seiten: int = 0):
    import fitz
    doc = fitz.open()
    for _ in range(text_seiten):
        seite = doc.new_page()
        seite.insert_text((72, 72), (_TEXT * 3)[:MIN_ZEICHEN * 3], fontsize=9)
    for _ in range(duenn_seiten):
        seite = doc.new_page()
        seite.insert_text((72, 72), "Seite 42", fontsize=9)      # nur Seitenzahl
    for _ in range(leer_seiten):
        doc.new_page()                                            # Scan-Seite: kein Text
    doc.save(str(pfad))
    doc.close()
    return pfad


def test_triage_digital(tmp_path):
    pdf = _baue_pdf(tmp_path / "digital.pdf", text_seiten=5, leer_seiten=0)
    t = triagiere_pdf(pdf)
    assert t["befund"] == "digital" and t["mit_text"] == 5 and t["leer"] == 0
    assert "kein OCR" in t["empfehlung"]


def test_triage_scan_und_mischform(tmp_path):
    scan = triagiere_pdf(_baue_pdf(tmp_path / "scan.pdf", text_seiten=0, leer_seiten=6))
    assert scan["befund"] == "scan" and scan["anteil_ohne_text"] == 1.0
    assert "ocr-pdf" in scan["empfehlung"]

    misch = triagiere_pdf(_baue_pdf(tmp_path / "misch.pdf", text_seiten=8, leer_seiten=2))
    assert misch["befund"] == "mischform", misch     # 20% textlos: Zierseiten, kein Scan
    assert misch["mit_text"] == 8 and misch["leer"] == 2


def test_triage_duenne_altocr_zaehlt_als_scan(tmp_path):
    """Shop-Scan mit Muell-Textschicht (nur Seitenzahlen): duenne Seiten zaehlen als
    textlos -> Befund scan, Empfehlung nennt --redo (Alt-OCR ersetzen)."""
    pdf = _baue_pdf(tmp_path / "altocr.pdf", text_seiten=1, leer_seiten=0, duenn_seiten=9)
    t = triagiere_pdf(pdf)
    assert t["befund"] == "scan" and t["duenn"] == 9
    assert "--redo" in t["empfehlung"]


def test_ocr_befehl_standard_redo_voll():
    """Kommandobau pur: Standard schuetzt betextete Seiten (--skip-text) und begradigt;
    redo ersetzt Alt-OCR ohne (inkompatible) Begradigung; voll baut die Textschicht
    komplett neu (--force-ocr, Browser-Druck-PDFs mit kaputten Fonts/Kerning)."""
    std = ocr_befehl("in.pdf", "out.pdf", jobs=2)
    assert std[:3] == [sys.executable, "-m", "ocrmypdf"]
    assert ["-l", "deu+eng"] == std[3:5] and "--skip-text" in std and "--deskew" in std
    assert "--redo-ocr" not in std and std[-2:] == ["in.pdf", "out.pdf"]
    assert std[std.index("--jobs") + 1] == "2"

    redo = ocr_befehl("in.pdf", "out.pdf", modus="redo")
    assert "--redo-ocr" in redo
    assert "--deskew" not in redo and "--skip-text" not in redo   # inkompatibel

    voll = ocr_befehl("in.pdf", "out.pdf", modus="voll", sprache="eng")
    assert "--force-ocr" in voll and ["-l", "eng"] == voll[3:5]
    assert "--skip-text" not in voll and "--redo-ocr" not in voll

    with pytest.raises(ValueError, match="OCR-Modus"):
        ocr_befehl("in.pdf", "out.pdf", modus="turbo")


@pytest.mark.skipif(shutil.which("tesseract") is None or shutil.which("ocrmypdf") is None,
                    reason="Tesseract/ocrmypdf nicht installiert (laeuft im Pi-Container)")
def test_ocr_lauf_integration(tmp_path):
    """Echter Mini-OCR-Lauf (nur wo Tesseract vorhanden): ein 'Scan' (Seite als Bild)
    bekommt eine Textschicht; die Nach-Triage in fuehre_ocr_aus verifiziert das."""
    import fitz

    from importer.ocr_vorstufe import fuehre_ocr_aus
    quelle = _baue_pdf(tmp_path / "text.pdf", text_seiten=1, leer_seiten=0)
    scan = tmp_path / "scan.pdf"
    doc_q = fitz.open(str(quelle))
    pix = doc_q[0].get_pixmap(dpi=200)
    doc_q.close()
    doc = fitz.open()
    seite = doc.new_page()
    seite.insert_image(seite.rect, pixmap=pix)                   # Text nur als BILD
    doc.save(str(scan)); doc.close()
    assert triagiere_pdf(scan)["befund"] == "scan"
    ziel = tmp_path / "scan.ocr.pdf"
    fuehre_ocr_aus(scan, ziel, jobs=1)                           # wirft bei Misserfolg
    assert triagiere_pdf(ziel)["mit_text"] >= 1
