"""Charakterbogen-Uebersetzer: DDB-Export (EN) -> offizieller deutscher WotC-Bogen.

Eigenstaendiges Feature neben dem Foliant-MCP (Auftrag docs/CLAUDE-CODE-AUFTRAG-
CHARAKTERBOGEN-MVP.md, Konzept KONZEPT_charakterbogen-uebersetzer.md).

Pipeline (Auftrag §5 / KONZEPT §3):
    ddb_pdf.py      Extractor    deterministisch  -> neutrales Charaktermodell (EN)
    uebersetzer.py  Uebersetzer  Claude + Foliant  -> Modell (DE, §5-Konvention)
    de_bogen.py     Renderer     deterministisch  -> Overlay auf DE-WotC-PDF

Phase 1 (dieses Modul-Set) umfasst nur den Extractor + das neutrale Modell + die
DDB-Feldkarte. Parsen ist reiner, testbarer Code; nichts geht verloren (roh_felder).
"""
