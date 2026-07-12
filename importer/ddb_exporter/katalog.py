"""DDB-Quellenkatalog: owned-IDs -> Titel, Edition, Foliant-Kuerzel + Scope-Entscheidung.

Loest die manuelle [[ddb.buch]]-Pflege ab (Automatik): das OEFFENTLICHE DDB-Verzeichnis
(api/config/json, kein Login) nennt zu jeder Quelle Name, Beschreibung und Kategorie.
Die Kategorie traegt das Editions-Signal ('5.5e ...' -> 2024, '5e ...' -> 2014).

SCOPE (Eigentuemer-Entscheidung 11.07.2026, verschaerft durch SYN-P0-007 am 12.07.2026):
David will ALLE Regel- und Abenteuerbuecher fuer die Uebersetzungsterminologie - gerade
die aelteren. Zwei Nichtziele werden ausgeschlossen: Premade-Character-Pakete
(Charakterdaten, §8; Charakter-Import ist eine spaetere Stufe) und Playtest/UA (kein
finales Regelwerk - gehoert nicht in den Spielerbestand, SYN-P0-007).
Abenteuer-/Setting-Buecher werden GELADEN, aber PERSISTENT als inhaltsart=
'abenteuer_setting' gekennzeichnet (Kampagnen-/Spoilergehalt, B6 - bewusst in Kauf
genommen; die Kennzeichnung wandert ueber Manifest und Import bis in quellen.inhaltsart,
statt wie zuvor nur als Konsolen-Print zu existieren). Ist die Edition nicht sicher aus
Kategorie/Name bestimmbar, wird sie als unsicher markiert und der Exporter bestimmt sie
autoritativ aus der Buch-DB (V1/Q3: nie raten) statt das Buch auszulassen."""
from __future__ import annotations

import html
import re

_CONFIG_URL = "https://www.dndbeyond.com/api/config/json"

# Kategorie-NAME (aus sourceCategories) -> Edition. Prefix-Match, laengster zuerst.
_EDITION_PREFIX = [("5.5e", "2024"), ("5e", "2014")]

# Einziges Nichtziel: Premade-Character-Pakete (Charakterdaten).
_SKIP_NAME_MUSTER = re.compile(r"premade character", re.IGNORECASE)


def _kuerzel(quelle: dict, prefix: str) -> str:
    """Stabiles Foliant-Kuerzel aus dem sauberen sourceURL-Slug ('sources/dnd/phb-2024'
    -> 'ddb-phb-2024-en'); Fallback auf den Namen."""
    url = str(quelle.get("sourceURL") or "")
    slug = url.rstrip("/").rsplit("/", 1)[-1] if url else ""
    if not slug:
        slug = re.sub(r"[^a-z0-9]+", "-", (quelle.get("name") or "buch").lower()).strip("-")
    return f"{prefix}-{slug}-en"


def katalog_aus_json(daten: dict) -> dict:
    """Rohes DDB-config-JSON -> {"quellen": {id: quelle}, "kategorien": {id: name}}."""
    return {
        "quellen": {int(s["id"]): s for s in daten.get("sources", [])},
        "kategorien": {int(k["id"]): k.get("name", "")
                       for k in daten.get("sourceCategories", [])},
    }


def lade_katalog(transport) -> dict:
    """Oeffentliches DDB-Verzeichnis holen (kein Login noetig)."""
    antwort = transport.get(_CONFIG_URL,
                            headers={"User-Agent": "Foliant (privater Buch-Katalog)"})
    antwort.raise_for_status()
    return katalog_aus_json(antwort.json())


def _edition(kategorie_name: str, quelle: dict) -> str | None:
    kn = (kategorie_name or "").strip().lower()
    for prefix, edition in _EDITION_PREFIX:
        if kn.startswith(prefix.lower()):
            return edition
    # Fallback: Jahreszahl in Name/Beschreibung.
    text = f"{quelle.get('name','')} {quelle.get('description','')}"
    if "2024" in text or "5.5e" in text.lower():
        return "2024"
    if "2014" in text:
        return "2014"
    return None                                       # unklar -> nicht raten


def klassifiziere(buch_id: int, katalog: dict, kuerzel_prefix: str = "ddb") -> dict:
    """Eine owned-Sourcebook-ID -> Foliant-Buchkonfig + Entscheidung.
    Rueckgabe: {id, titel, kuerzel, sprache, edition, kategorie_ddb, inhaltsart,
    importieren: bool, grund: str}. importieren=False heisst: bewusst uebersprungen
    (grund erklaert es); edition=None heisst: Edition unklar -> manuell setzen.
    inhaltsart ('regelwerk' | 'abenteuer_setting') ist die PERSISTENTE Kennzeichnung
    (SYN-P0-007): sie wandert ueber das Artefakt-Manifest bis in quellen.inhaltsart."""
    quelle = katalog["quellen"].get(int(buch_id))
    if quelle is None:
        return {"id": buch_id, "titel": f"DDB-Quelle {buch_id}",
                "kuerzel": f"{kuerzel_prefix}-{buch_id}", "importieren": False,
                "grund": "nicht im oeffentlichen DDB-Verzeichnis (Name/Edition unbekannt)"}
    name = html.unescape(quelle.get("description") or quelle.get("name") or str(buch_id))
    kategorie_name = katalog["kategorien"].get(quelle.get("sourceCategoryId"), "")
    edition = _edition(kategorie_name, quelle)       # aus 5e/5.5e-Kategorie, sonst None
    eintrag = {"id": int(buch_id), "titel": f"{name} (D&D Beyond)",
               "kuerzel": _kuerzel(quelle, kuerzel_prefix), "sprache": "en",
               "edition": edition, "edition_sicher": edition is not None,
               "kategorie_ddb": kategorie_name,
               # Playtest hat KEINE eigene inhaltsart: es wird unten ausgeschlossen und
               # erreicht die Datenbank nie (SYN-P0-007).
               "inhaltsart": ("abenteuer_setting" if _ist_abenteuer_setting(kategorie_name)
                              else "regelwerk")}

    # Nichtziel 1: Premade-Character-Pakete (Charakterdaten, §8).
    if _SKIP_NAME_MUSTER.search(name):
        return {**eintrag, "importieren": False,
                "grund": "Premade-Character-Paket (Charakterdaten - spaetere Stufe, §8)"}

    # Nichtziel 2 (SYN-P0-007): Playtest/UA-Material ist vorlaeufig und wird von WotC
    # laufend ueberschrieben - als "Regel-Auskunft" waere es irrefuehrend, deshalb
    # gar nicht erst in den Spielerbestand (statt es nur zu kennzeichnen).
    if _ist_playtest(kategorie_name):
        return {**eintrag, "importieren": False,
                "grund": "Playtest/UA ist kein finales Regelwerk - nicht in den "
                         "Spielerbestand (SYN-P0-007)"}

    # Edition wird NICHT geraten (V1/Q3): ist sie hier unsicher, bestimmt der Exporter sie
    # autoritativ aus der Buch-DB (RPGSourceCategory/ReleaseDate); bleibt sie unbestimmbar,
    # wird das Buch beim Export uebersprungen, nicht mit Default-Edition geladen.
    hinweise = []
    if not eintrag["edition_sicher"]:
        hinweise.append("Edition aus Katalog unsicher -> autoritativ aus der Buch-DB")
    if eintrag["inhaltsart"] == "abenteuer_setting":
        hinweise.append(f"Kategorie '{kategorie_name}': Kampagnen-/Setting-Inhalt "
                        f"(Spoiler moeglich, B6 - bewusst geladen, persistent als "
                        f"inhaltsart='abenteuer_setting' gekennzeichnet)")
    return {**eintrag, "importieren": True,
            "grund": "; ".join(hinweise) if hinweise else "Regelinhalt",
            "hinweis": bool(hinweise)}


# Kategorien mit Kampagnen-/Spoilergehalt: geladen, aber persistent als
# inhaltsart='abenteuer_setting' gekennzeichnet (SYN-P0-007). 'playtest' steht hier
# BEWUSST nicht mehr: Playtest/UA wird gar nicht importiert (s. klassifiziere).
_HINWEIS_KATEGORIEN = {"critical role", "adventures", "campaign"}


def _ist_abenteuer_setting(kategorie_name: str) -> bool:
    kn = (kategorie_name or "").strip().lower()
    return any(a in kn for a in _HINWEIS_KATEGORIEN)


def _ist_playtest(kategorie_name: str) -> bool:
    """Substring-Match wie bei den Hinweis-Kategorien (DDB nennt die Kategorie mal
    'Playtest', mal z. B. 'Playtest Material')."""
    return "playtest" in (kategorie_name or "").strip().lower()
