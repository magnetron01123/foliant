"""PDF -> Markdown. Standard: PyMuPDF4LLM; Fallback: Docling (schwierige Tabellen/Statbloecke).

Leer-Seiten-Check ist Pflicht: PyMuPDF4LLM liefert fuer Seiten OHNE Textebene "" zurueck - das
ist zugleich der Trigger fuer OCR.

OCR - noetig bei GESCANNTEN PDFs (kein Textlayer): die OCR-VORSTUFE ist integriert
(importer/ocr_vorstufe.py) - `admin pdf-triage` erkennt Scans, `admin ocr-pdf` (OCRmyPDF/
Tesseract, 'deu+eng') erzeugt die Textschicht nach data/ocr/, danach laeuft das OCR-PDF durch
DIESE normale Pipeline. GUARDRAIL hier: ist die MEHRHEIT der Seiten textlos (SCAN_SCHWELLE),
bricht die Konvertierung mit OCR-Hinweis ab, statt eine Rumpf-Quelle zu importieren (Q3/O3) -
das gilt auch fuer docling_ersatz (Docling laeuft hier OHNE OCR und saehe ebenfalls nichts).
OCR-Inhalt ist fehleranfaellig (v. a. Statbloecke/Tabellen/Zahlen) -> extra Stichprobe (O3). Da
einmaliger Import, ist die langsamere Verarbeitung unkritisch.

Ausgabeformat: EIN Markdown-String mit Seitenmarkern `<!-- seite:N -->` vor jeder Seite -
`import_markdown` wertet sie fuer das Seitenzitat (F7) aus und entfernt sie. Problemseiten
(leer -> vermutlich gescannt/reine Grafik) werden auf stderr protokolliert (O3)."""
from __future__ import annotations

import sys
from pathlib import Path


def _docling_fallback(pdf_pfad: Path) -> str | None:
    """Docling ist optional (requirements: auskommentiert; auf ARM zaeh). Liefert Markdown
    OHNE Seitenmarker (Eintraege zitieren dann nur Quelle/Edition - Schema erlaubt seite=NULL)."""
    try:
        from docling.document_converter import DocumentConverter
    except ImportError:
        return None
    ergebnis = DocumentConverter().convert(str(pdf_pfad))
    return ergebnis.document.export_to_markdown()


def pdf_zu_markdown(pdf_pfad: str | Path, docling_ersatz: bool = False) -> str:
    """Konvertiert ein PDF nach Markdown (Seitenmarker fuer F7-Zitate inklusive).
    Pro Seite wird auf leeren Text geprueft (PyMuPDF4LLM-Macke: textlose Seiten kommen
    kommentarlos als "") - Problemseiten gehen als Protokoll auf stderr (O3-Stichprobe).

    A11: Einzelne leere/rein grafische Seiten ersetzen NIE automatisch die gesamte gute
    PyMuPDF-Extraktion - die guten Seiten (samt Seitenmarkern) bleiben erhalten, die
    Problemseiten werden protokolliert. Ein VOLLSTAENDIGER Docling-Ersatz (verliert alle
    Seitenzitate!) passiert nur mit der ausdruecklichen Option docling_ersatz=True."""
    pdf_pfad = Path(pdf_pfad)
    if not pdf_pfad.exists():
        raise FileNotFoundError(f"PDF nicht gefunden: {pdf_pfad}")
    import pymupdf4llm  # Import hier: Server/Tools brauchen das Paket nie (Q7: Laufzeit offline)

    # use_ocr=False ZWINGEND: pymupdf4llm (>=1.28) OCRt textlose Seiten STILL selbst,
    # sobald Tesseract installiert ist (seit der OCR-Vorstufe im Image!). Das machte die
    # Konvertierung umgebungsabhaengig - auf dem Pi wurden Zierseiten ge-OCRt, deren
    # Riesen-Glyphen die GESAMTE Heading-Hierarchie verschoben (efota: 6 statt 202
    # Eintraege). OCR laeuft bei uns NUR kontrolliert ueber die Vorstufe (admin ocr-pdf).
    try:
        seiten = pymupdf4llm.to_markdown(str(pdf_pfad), page_chunks=True, use_ocr=False)
    except TypeError:      # aeltere pymupdf4llm ohne use_ocr-Parameter (OCRen nie still)
        seiten = pymupdf4llm.to_markdown(str(pdf_pfad), page_chunks=True)
    teile: list[str] = []
    problemseiten: list[int] = []
    for i, seite in enumerate(seiten, start=1):
        text = (seite.get("text") or "").strip() if isinstance(seite, dict) else str(seite).strip()
        meta = seite.get("metadata", {}) if isinstance(seite, dict) else {}
        nummer = meta.get("page", i) or i
        if not text:
            problemseiten.append(nummer)
            continue
        teile.append(f"<!-- seite:{nummer} -->\n{text}")

    # GUARDRAIL (Q3/O3): mehrheitlich textlose Seiten = gescanntes PDF -> harter Abbruch
    # mit OCR-Hinweis statt Rumpf-Import der wenigen Textseiten. Bewusst VOR dem Docling-
    # Zweig: Docling laeuft hier ohne OCR und saehe genauso wenig.
    from importer.ocr_vorstufe import SCAN_SCHWELLE
    anteil = len(problemseiten) / max(len(seiten), 1)
    if anteil >= SCAN_SCHWELLE:
        raise ValueError(
            f"{pdf_pfad.name}: {len(problemseiten)}/{len(seiten)} Seiten ohne Textebene "
            f"({anteil:.0%}) - gescanntes PDF. Erst OCR-Vorstufe: "
            f"`python -m app.admin ocr-pdf --datei {pdf_pfad}` (Befund vorab: "
            f"`python -m app.admin pdf-triage`). Import abgebrochen, Bestand bleibt (A7/Q3).")

    if problemseiten:
        print(f"WARNUNG {pdf_pfad.name}: {len(problemseiten)} Seite(n) ohne Textebene "
              f"(vermutlich Scan/Grafik): {problemseiten[:20]}"
              f"{' …' if len(problemseiten) > 20 else ''}", file=sys.stderr)
        if docling_ersatz:
            docling_md = _docling_fallback(pdf_pfad)
            if docling_md and docling_md.strip():
                print("-> Docling-VOLLERSATZ verwendet (ausdruecklich angefordert): ALLE "
                      "Seitenmarker gehen verloren, Zitate nennen nur noch Quelle/Edition.",
                      file=sys.stderr)
                return docling_md
            print("-> Docling nicht installiert/ohne Ergebnis - PyMuPDF-Seiten werden "
                  "verwendet.", file=sys.stderr)
        else:
            print("-> Gute PyMuPDF-Seiten bleiben erhalten (A11). Enthalten die "
                  "Problemseiten Regeltext: OCR-Vorstufe (OCRmyPDF, 'deu') oder bewusster "
                  "Vollersatz via docling_ersatz=True - siehe Modul-Doku.", file=sys.stderr)

    if not teile:
        raise ValueError(f"{pdf_pfad.name}: keine einzige Seite mit Textebene - gescanntes "
                         f"PDF? OCR-Vorstufe noetig (siehe Modul-Doku).")
    return "\n\n".join(teile)
