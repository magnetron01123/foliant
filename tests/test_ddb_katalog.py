"""Tests fuer die DDB-Katalog-Auto-Aufloesung (owned-ID -> Titel/Edition/Scope)."""
import pytest

pytest.importorskip("markdownify", reason="DDB-Exporter-Tests nur in .venv-ddb")

from importer.ddb_exporter.katalog import katalog_aus_json, klassifiziere

_ROH = {
    "sourceCategories": [
        {"id": 24, "name": "5.5e Core Rules"},
        {"id": 25, "name": "5.5e Expanded Rules"},
        {"id": 9, "name": "5e Core Rules"},
        {"id": 11, "name": "5e Expanded Rules"},
        {"id": 30, "name": "Playtest"},
        {"id": 40, "name": "Critical Role"},
        {"id": 50, "name": "Hidden Sources"},
    ],
    "sources": [
        {"id": 145, "name": "PHB-2024", "description": "Player&#x2019;s Handbook",
         "sourceCategoryId": 24, "sourceURL": "sources/dnd/phb-2024"},
        {"id": 232, "name": "RTHW", "description": "Ravenloft: The Horrors Within",
         "sourceCategoryId": 25, "sourceURL": "sources/dnd/rthw"},
        {"id": 1, "name": "BR", "description": "Basic Rules (2014)",
         "sourceCategoryId": 9, "sourceURL": "sources/dnd/basic-rules-2014"},
        {"id": 29, "name": "UA2014", "description": "Unearthed Arcana 2014",
         "sourceCategoryId": 30, "sourceURL": "sources/dnd/ua"},
        {"id": 62, "name": "FS", "description": "Frozen Sick",
         "sourceCategoryId": 40, "sourceURL": "sources/dnd/fs"},
        {"id": 209, "name": "BG3PC", "description": "Baldur's Gate 3: Premade Characters",
         "sourceCategoryId": 50, "sourceURL": "sources/dnd/bg3-premades"},
        {"id": 166, "name": "SAE", "description": "Sage Advice & Errata",
         "sourceCategoryId": 50, "sourceURL": "sources/dnd/sae"},
    ],
}


@pytest.fixture()
def katalog():
    return katalog_aus_json(_ROH)


def test_regelbuch_2024_wird_importiert(katalog):
    r = klassifiziere(145, katalog)
    assert r["importieren"] is True and r["edition"] == "2024"
    assert r["kuerzel"] == "ddb-phb-2024-en"                 # stabiler sourceURL-Slug
    assert r["titel"] == "Player’s Handbook (D&D Beyond)"    # HTML-Entity aufgeloest


def test_edition_aus_kategorie(katalog):
    assert klassifiziere(232, katalog)["edition"] == "2024"  # 5.5e Expanded
    assert klassifiziere(1, katalog)["edition"] == "2014"    # 5e Core


def test_premade_characters_uebersprungen(katalog):
    """Einziges Nichtziel: Charakter-Pakete (Charakter-Import ist spaetere Stufe)."""
    r = klassifiziere(209, katalog)
    assert r["importieren"] is False and "Charakterdaten" in r["grund"]


def test_abenteuer_wird_geladen_aber_gekennzeichnet(katalog):
    """Eigentuemer-Entscheidung: Abenteuer/Setting werden GELADEN (Uebersetzung), aber
    mit Spoiler-Hinweis markiert."""
    r = klassifiziere(62, katalog)
    assert r["importieren"] is True and r["hinweis"] is True
    assert "Spoiler" in r["grund"] or "Kampagne" in r["grund"]


def test_edition_sicher_aus_kategorie(katalog):
    assert klassifiziere(145, katalog)["edition_sicher"] is True   # 5.5e -> 2024 sicher
    assert klassifiziere(1, katalog)["edition_sicher"] is True     # 5e -> 2014 sicher


def test_unklare_edition_NICHT_geraten(katalog):
    """V1/Q3: unsichere Edition wird NICHT auf 2024 defaultet, sondern als unsicher
    markiert - der Exporter bestimmt sie autoritativ aus der Buch-DB, sonst Skip."""
    r = klassifiziere(166, katalog)                          # Hidden Sources, kein Jahr
    assert r["edition"] is None and r["edition_sicher"] is False
    assert r["importieren"] is True                          # Entscheidung faellt am Buch
    assert "autoritativ aus der Buch-DB" in r["grund"]


def test_unbekannte_id(katalog):
    r = klassifiziere(999999, katalog)
    assert r["importieren"] is False and "nicht im oeffentlichen" in r["grund"]
