"""OCR-Vorstufe fuer GESCANNTE PDFs (F4-Erweiterung, 11.07.2026).

Viele Buch-PDFs sind Scans ohne Textschicht - die Pipeline (PyMuPDF4LLM liest die
TEXTSCHICHT) bekaeme daraus nichts. Konzept in drei Teilen, alles VOR der bestehenden
Pipeline, die dadurch unveraendert bleibt:

  1. TRIAGE (triagiere_pdf / admin pdf-triage): zaehlt pro Seite die Zeichen der
     Textschicht und faellt einen Befund - 'digital' (direkt importieren), 'mischform'
     (einzelne Zier-/Kartenseiten ohne Text; der bestehende Leer-Seiten-Check
     protokolliert sie), 'scan' (OCR noetig). Erkennt auch Shop-PDFs mit vorhandener,
     aber duenner Alt-OCR-Schicht (-> --redo).
  2. OCR (ocr_befehl/fuehre_ocr_aus / admin ocr-pdf): OCRmyPDF + Tesseract ('deu+eng')
     legen eine unsichtbare Textschicht ins PDF. Ausgabe nach data/ocr/ (quellen/ ist im
     Container read-only gemountet; data/ ist beschreibbar und persistent). Danach laeuft
     das OCR-PDF durch die NORMALE Pipeline - Chunker, Editions-Pflicht, Seitenmarker,
     QS-Checks greifen unveraendert. Tesseract ist leicht genug fuer den Pi
     (~15-45 min/Buch, einmalig); --jobs nutzt die Kerne.
  3. GUARDRAIL (SCAN_SCHWELLE, greift in pdf_nach_markdown): ein Import, dessen Seiten
     mehrheitlich ohne Textschicht sind, bricht mit Hinweis auf die OCR-Vorstufe ab -
     statt still eine Rumpf-Quelle in die DB zu schreiben (Q3/O3).

Qualitaets-Erwartung (ehrlich): OCR-Text ist fehleranfaellig, v. a. Statbloecke/Tabellen/
Zahlen -> O3-Stichprobe vor Freigabe ist Pflicht; Scans unter ~300 dpi werden deutlich
schlechter. Fuer hartnaeckige Seiten bleibt Docling (Layout) bzw. punktuelles Abtippen."""
from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Seiten mit weniger Zeichen zaehlen als "ohne nutzbaren Text" (nur Seitenzahl/Wasserzeichen).
MIN_ZEICHEN = 100
# Ab diesem Anteil textloser Seiten gilt das PDF als Scan (Triage-Befund + Import-Guardrail).
# Zierseiten/Karten liegen erfahrungsgemaess deutlich darunter (dt. SRD: <10 %).
SCAN_SCHWELLE = 0.4
# Ausgabeverzeichnis der OCR-PDFs: data/ ist (anders als quellen/, read-only) im Container
# beschreibbar und persistent gemountet.
OCR_VERZEICHNIS = "data/ocr"


def triagiere_pdf(pfad: str | Path) -> dict:
    """Textschicht-Befund eines PDFs: {datei, seiten, mit_text, duenn, leer, mit_bildern,
    anteil_ohne_text, befund: digital|mischform|scan, empfehlung}."""
    pfad = Path(pfad)
    if not pfad.exists():
        raise FileNotFoundError(f"PDF nicht gefunden: {pfad}")
    import fitz  # PyMuPDF; lazy - Server/Tools brauchen es nie (Q7)

    doc = fitz.open(pfad)
    try:
        leer = duenn = mit_text = mit_bildern = 0
        for seite in doc:
            zeichen = len((seite.get_text("text") or "").strip())
            if seite.get_images():
                mit_bildern += 1
            if zeichen == 0:
                leer += 1
            elif zeichen < MIN_ZEICHEN:
                duenn += 1
            else:
                mit_text += 1
        seiten = doc.page_count
    finally:
        doc.close()

    anteil = ((leer + duenn) / seiten) if seiten else 1.0
    if anteil >= SCAN_SCHWELLE:
        befund = "scan"
        empfehlung = (f"OCR-Vorstufe noetig:  python -m app.admin ocr-pdf --datei {pfad}")
        if duenn or mit_text:
            empfehlung += ("  (Teil-Textschicht vorhanden - ist sie Muell/Alt-OCR, "
                           "zusaetzlich --redo)")
    elif anteil > 0.1:
        befund = "mischform"
        empfehlung = ("einzelne Seiten ohne Text (Zier-/Kartenseiten?) - direkt "
                      "importierbar; Problemseiten werden beim Import protokolliert (O3)")
    else:
        befund = "digital"
        empfehlung = "Textschicht vorhanden - direkt importieren, kein OCR noetig"
    return {"datei": str(pfad), "seiten": seiten, "mit_text": mit_text, "duenn": duenn,
            "leer": leer, "mit_bildern": mit_bildern,
            "anteil_ohne_text": round(anteil, 3), "befund": befund,
            "empfehlung": empfehlung}


def ocr_befehl(eingabe: str | Path, ausgabe: str | Path, sprache: str = "deu+eng",
               modus: str = "standard", jobs: int = 0) -> list[str]:
    """OCRmyPDF-Kommandozeile (pur, testbar). Drei Modi:
      standard - --skip-text (bereits betextete Seiten unangetastet, sicher fuer
                 Mischformen) + --deskew/--rotate-pages (Scan-Begradigung).
      redo     - --redo-ocr: ERSETZT eine vorhandene (schlechte) Alt-OCR-Schicht;
                 mit --deskew/--clean inkompatibel -> ohne Begradigung.
      voll     - --force-ocr: baut die KOMPLETTE Textschicht aus den Pixeln neu.
                 Der Weg fuer Browser-Druck-PDFs (z. B. DDB-Ausdrucke) mit kaputter
                 Font-Zuordnung (Mojibake-Headings) oder Kerning-Rissen ('Ar tificer') -
                 dort ist die vorhandene Textschicht schlechter als frisches OCR.
    --output-type pdf (kein PDF/A-Umbau) und -O0 halten den Lauf schnell/verlustfrei."""
    if modus not in ("standard", "redo", "voll"):
        raise ValueError(f"unbekannter OCR-Modus: {modus!r} (standard|redo|voll)")
    befehl = [sys.executable, "-m", "ocrmypdf", "-l", sprache,
              "--output-type", "pdf", "--optimize", "0",
              "--jobs", str(jobs or min(os.cpu_count() or 2, 4))]
    befehl += {"standard": ["--skip-text", "--deskew", "--rotate-pages"],
               "redo": ["--redo-ocr"], "voll": ["--force-ocr"]}[modus]
    return befehl + [str(eingabe), str(ausgabe)]


def fuehre_ocr_aus(eingabe: str | Path, ausgabe: str | Path, sprache: str = "deu+eng",
                   modus: str = "standard", jobs: int = 0) -> None:
    """OCR ausfuehren (Live-Ausgabe durchgereicht). Prueft die Werkzeuge vorab und
    verifiziert das Ergebnis per Nach-Triage; wirft RuntimeError bei jedem Fehler."""
    if importlib.util.find_spec("ocrmypdf") is None:
        raise RuntimeError("ocrmypdf ist nicht installiert - Image neu bauen "
                           "(requirements.txt) bzw. `pip install ocrmypdf`.")
    if shutil.which("tesseract") is None:
        raise RuntimeError("tesseract fehlt - Image neu bauen (Dockerfile installiert "
                           "tesseract-ocr + tesseract-ocr-deu).")
    ausgabe = Path(ausgabe)
    ausgabe.parent.mkdir(parents=True, exist_ok=True)
    befehl = ocr_befehl(eingabe, ausgabe, sprache=sprache, modus=modus, jobs=jobs)
    print("OCR-Lauf:", " ".join(befehl))
    ergebnis = subprocess.run(befehl)
    if ergebnis.returncode != 0:
        raise RuntimeError(f"ocrmypdf endete mit Code {ergebnis.returncode} - Ausgabe oben; "
                           f"bei vorhandener Alt-Textschicht --redo probieren.")
    kontrolle = triagiere_pdf(ausgabe)
    print(f"Nach-Triage: befund={kontrolle['befund']}, "
          f"{kontrolle['mit_text']}/{kontrolle['seiten']} Seiten mit Text.")
    if kontrolle["befund"] == "scan":
        raise RuntimeError("Nach-Triage: weiterhin ueberwiegend textlos - OCR hat nicht "
                           "gegriffen (Scan-Qualitaet? Sprache? --redo noetig?).")
