# Foliant - Container-Image (ARM64: Raspberry Pi 4 64-bit / Apple-Silicon Mac mini)
FROM python:3.12-slim

# build-essential als Sicherheitsnetz fuer evtl. Wheels. Tesseract (+deu) und Ghostscript
# fuer die OCR-Vorstufe gescannter PDFs (admin ocr-pdf, importer/ocr_vorstufe.py).
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        tesseract-ocr tesseract-ocr-deu tesseract-ocr-eng \
        ghostscript \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Abhaengigkeiten zuerst (Layer-Cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Projektcode
COPY . .

# Nicht als root laufen
RUN useradd -m foliant && chown -R foliant:foliant /app
USER foliant

# SQLite-DB liegt als Volume unter /app/data (persistiert ausserhalb des Containers)
EXPOSE 8000

# ASGI-Server fuer den FastMCP-HTTP-Endpunkt (hinter Cloudflare Tunnel).
# --no-access-log: der Request-Pfad ENTHAELT das Geheimpfad-Token - Access-Logs wuerden
# das Secret in jede Logzeile schreiben (SYN-P1-004); Blockierungen loggt app/zugriff.py
# selbst (redigiert).
CMD ["uvicorn", "app.server:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
