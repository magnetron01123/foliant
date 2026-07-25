"""Charakterbogen-Uebersetzer: DDB-Export (EN) -> offizieller deutscher WotC-Bogen.

Eigenstaendiges Feature neben dem Foliant-MCP. Pipeline, Module und die tragenden
Entwurfsregeln: docs/CHARAKTERBOGEN-MVP.md.

    ddb_pdf.py      Extractor    deterministisch  -> neutrales Charaktermodell (EN)
    uebersetzer.py  Uebersetzer  Claude + Foliant  -> Modell (DE, §5-Konvention)
    de_bogen.py     Renderer     deterministisch  -> Overlay auf DE-WotC-PDF

Parsen und Rendern sind reiner, testbarer Code; nur die Uebersetzung ist LLM-basiert.
Zahlen, Wuerfel und Modifikatoren laufen NIE durch das Sprachmodell; nichts geht
verloren (roh_felder protokolliert jedes befuellte Widget).
"""
