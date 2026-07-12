"""Regressionstests A11 (PDF-Fallback ohne Verlust guter Seiten) - gemockte
Konverterantworten, kein echtes PDF/Docling noetig."""
import sys
import types

import pytest

from importer import pdf_nach_markdown as pnm


@pytest.fixture()
def fake_pdf(tmp_path, monkeypatch):
    """3-Seiten-PDF-Simulation: Seite 2 ist leer (Scan/Grafik); Docling 'installiert'."""
    pdf = tmp_path / "test.pdf"
    pdf.write_bytes(b"%PDF-fake")
    fake_modul = types.SimpleNamespace(to_markdown=lambda pfad, page_chunks: [
        {"text": "# Seite Eins\n\nGuter Text eins.", "metadata": {"page": 1}},
        {"text": "", "metadata": {"page": 2}},
        {"text": "# Seite Drei\n\nGuter Text drei.", "metadata": {"page": 3}},
    ])
    monkeypatch.setitem(sys.modules, "pymupdf4llm", fake_modul)
    monkeypatch.setattr(pnm, "_docling_fallback",
                        lambda pfad: "# Docling-Gesamtdokument ohne Seitenmarker")
    return pdf


def test_a11_einzelne_leerseite_ersetzt_nicht_alles(fake_pdf):
    """Default: die guten PyMuPDF-Seiten (samt Seitenmarkern) bleiben; KEIN stiller
    Docling-Vollersatz wegen einer einzigen leeren Seite."""
    md = pnm.pdf_zu_markdown(fake_pdf)
    assert "<!-- seite:1 -->" in md and "<!-- seite:3 -->" in md
    assert "Guter Text eins." in md and "Guter Text drei." in md
    assert "Docling-Gesamtdokument" not in md


def test_a11_vollersatz_nur_mit_ausdruecklicher_option(fake_pdf):
    """Der Docling-Vollersatz (verliert Seitenzitate) verlangt docling_ersatz=True."""
    md = pnm.pdf_zu_markdown(fake_pdf, docling_ersatz=True)
    assert md == "# Docling-Gesamtdokument ohne Seitenmarker"


def test_a11_komplett_leeres_pdf_bricht_ab(tmp_path, monkeypatch):
    """Ohne eine einzige Textseite: klarer Fehler statt leerem Import."""
    pdf = tmp_path / "leer.pdf"
    pdf.write_bytes(b"%PDF-fake")
    fake_modul = types.SimpleNamespace(to_markdown=lambda pfad, page_chunks: [
        {"text": "", "metadata": {"page": 1}}])
    monkeypatch.setitem(sys.modules, "pymupdf4llm", fake_modul)
    with pytest.raises(ValueError, match="[Tt]extebene"):
        pnm.pdf_zu_markdown(pdf)


def _fake_seiten(text_seiten: int, leer_seiten: int):
    seiten = [{"text": f"# Abschnitt {i}\n\nInhalt {i}.", "metadata": {"page": i}}
              for i in range(1, text_seiten + 1)]
    seiten += [{"text": "", "metadata": {"page": text_seiten + j}}
               for j in range(1, leer_seiten + 1)]
    return seiten


def test_scan_guardrail_bricht_mehrheitlich_textloses_pdf_ab(tmp_path, monkeypatch):
    """GUARDRAIL (Q3/O3, OCR-Konzept 11.07.2026): mehrheitlich textlose Seiten = Scan ->
    Abbruch mit ocr-pdf-Hinweis statt Rumpf-Import der wenigen Textseiten. Gilt auch fuer
    docling_ersatz (Docling laeuft ohne OCR und saehe genauso wenig)."""
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"%PDF-fake")
    fake_modul = types.SimpleNamespace(
        to_markdown=lambda pfad, page_chunks: _fake_seiten(text_seiten=2, leer_seiten=3))
    monkeypatch.setitem(sys.modules, "pymupdf4llm", fake_modul)
    with pytest.raises(ValueError, match="ocr-pdf"):
        pnm.pdf_zu_markdown(pdf)                                  # 60% leer -> Scan
    with pytest.raises(ValueError, match="ocr-pdf"):
        pnm.pdf_zu_markdown(pdf, docling_ersatz=True)             # kein Schlupfloch


def test_stilles_pymupdf_ocr_ist_abgeschaltet(tmp_path, monkeypatch):
    """pymupdf4llm >=1.28 OCRt textlose Seiten STILL, sobald Tesseract installiert ist -
    das machte die Konvertierung umgebungsabhaengig (Pi-Container hat Tesseract fuer die
    OCR-Vorstufe). pdf_zu_markdown MUSS use_ocr=False anfordern."""
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-fake")
    gesehen = {}

    def fake_to_markdown(pfad, page_chunks, **kw):
        gesehen.update(kw)
        return [{"text": "# A\n\nInhalt.", "metadata": {"page": 1}}]

    monkeypatch.setitem(sys.modules, "pymupdf4llm",
                        types.SimpleNamespace(to_markdown=fake_to_markdown))
    pnm.pdf_zu_markdown(pdf)
    assert gesehen.get("use_ocr") is False


def test_scan_guardrail_laesst_zierseiten_durch(tmp_path, monkeypatch):
    """Unterhalb der Schwelle (einzelne Zier-/Kartenseiten) bleibt das A11-Verhalten:
    gute Seiten importieren, Problemseiten nur protokollieren."""
    pdf = tmp_path / "misch.pdf"
    pdf.write_bytes(b"%PDF-fake")
    fake_modul = types.SimpleNamespace(
        to_markdown=lambda pfad, page_chunks: _fake_seiten(text_seiten=8, leer_seiten=2))
    monkeypatch.setitem(sys.modules, "pymupdf4llm", fake_modul)
    md = pnm.pdf_zu_markdown(pdf)                                 # 20% leer -> ok
    assert "<!-- seite:1 -->" in md and "Inhalt 8." in md
