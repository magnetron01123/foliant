"""Die Plausibilitaets-Schwellen aller Import-Wege - EINE Stelle (Phase 4, Befund D3).

Vorher lagen drei Schwellen in drei Modulen, jede mit eigener Fehlermeldung und eigener
Vergleichslogik: `SCHRUMPF_SCHWELLE` (import_markdown, auch von import_open5e benutzt),
`MIN_REIMPORT_RATIO` (import_ddb) und `SCAN_SCHWELLE` (ocr_vorstufe). Wer eine anpassen
wollte, musste erst suchen, welche greift.

Vor allem aber deckten sie nur EINE Richtung ab. Ein Import, der zu WENIG liefert, bricht
seit je ab; ein Import, der unplausibel WAECHST, lief kommentarlos durch - genau der Fall
bei falschem Split-Level, wo ein Buch statt 300 Eintraegen 3000 Fragmente ergibt. Der
Wachstums-Schutz ist das fehlende Gegenstueck.

Beide Richtungen sind absichtlich weit gesetzt: sie sollen den PARSE-Unfall fangen, nicht
eine legitime Quellen-Erweiterung behindern. Wer bewusst umbaut, setzt `--force`.
"""
from __future__ import annotations

# Faellt ein Re-Import unter diesen Anteil des Altbestands, ist das fast immer ein Parse-
# oder Quellfehler -> Abbruch statt Datenverlust.
SCHRUMPF_SCHWELLE = 0.5
# DDB-Bücher liegen enger beieinander (gleicher Exporter, gleiche Struktur), deshalb darf
# der Schutz dort schaerfer greifen.
DDB_SCHRUMPF_SCHWELLE = 0.70
# Gegenstueck (Befund D3): mehr als das Dreifache des Altbestands ist kein Zuwachs mehr,
# sondern ein Zerlegungsfehler. Real gemessen beim falschen Split-Level: die 2014-Scans
# liegen komplett auf H6, ein Level daneben vervielfacht die Chunkzahl.
WACHSTUM_SCHWELLE = 3.0
# Ab diesem Anteil textloser Seiten gilt ein PDF als Scan (Triage + Import-Guardrail).
SCAN_SCHWELLE = 0.4


def pruefe_umfang(kuerzel: str, neu: int, alt: int, *, erlaubt: bool = False,
                  min_anteil: float = SCHRUMPF_SCHWELLE,
                  max_faktor: float = WACHSTUM_SCHWELLE) -> None:
    """Wirft ValueError, wenn ein Re-Import unplausibel schrumpft ODER waechst.

    `alt == 0` (Erstimport) prueft nichts - es gibt keinen Vergleichsmassstab. `erlaubt`
    (aus --force) setzt BEIDE Richtungen ausser Kraft: wer den Umbau bewusst fuehrt, will
    nicht an der Gegenrichtung haengenbleiben."""
    if erlaubt or not alt:
        return
    if neu < alt * min_anteil:
        raise ValueError(
            f"Quelle '{kuerzel}': Schrumpf-Schutz (A7) - nur {neu} neue gegenueber {alt} "
            f"bestehenden Eintraegen (< {int(min_anteil * 100)} %). Wenn beabsichtigt: "
            f"erlaube_schrumpfen=True bzw. --force.")
    if neu > alt * max_faktor:
        raise ValueError(
            f"Quelle '{kuerzel}': Wachstums-Schutz (D3) - {neu} neue gegenueber {alt} "
            f"bestehenden Eintraegen (> {max_faktor:g}x). Das ist fast immer ein "
            f"Zerlegungsfehler (falsches Split-Level), kein Zuwachs: der Bestand bliebe "
            f"unangetastet. Wenn beabsichtigt: erlaube_schrumpfen=True bzw. --force.")
