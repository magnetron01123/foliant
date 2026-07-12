"""Artefakt-Schreiber: Content-Zeilen -> manifest.json + entries.jsonl (Vertrag v1,
Gegenstueck zum Validator importer/ddb_artefakt.py - der Schreiber erzeugt NUR, der
Validator prueft; beide teilen das Kategorien-Mapping).

Atomar: geschrieben wird in '.partial-<export_id>', das Verzeichnis wird erst nach dem
fsync auf den endgueltigen Namen gesetzt und ABSCHLIESSEND mit dem Vertrags-Validator
geprueft - ein Artefakt, das die Import-Pruefung nicht besteht, bleibt nicht liegen.
Deterministisch: Eintraege nach ddb_id sortiert, feste JSON-Form."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path

from importer.ddb_artefakt import kategorie_aus_breadcrumb, pruefe_artefakt

SCHEMA_VERSION = 1


def _parent_schluessel(zeile: dict) -> str | None:
    p = zeile.get("parent_id")
    return str(p) if p not in (None, "", 0, "0") else None


def _breadcrumb(zeile: dict, aufloesung: dict[str, dict], buch_titel: str) -> list[str]:
    """Voller Pfad [Buch, ..., Eltern, eigener Titel] aus der ParentID-Kette.
    aufloesung bildet SOWOHL id ALS AUCH cobalt_id auf die Zeile ab (DDB-Quirk: ParentID
    referenziert je nach Buch die numerische ID oder die CobaltID/Slug). Zyklen sind ein
    Fehler; fehlende Parents brechen die Kette einfach ab (nichts wird geraten)."""
    kette: list[str] = []
    knoten: dict | None = zeile
    gesehen: set[str] = set()
    while knoten is not None:
        kid = str(knoten["id"])
        if kid in gesehen:
            raise ValueError(f"Parent-Zyklus an Content-ID {kid}.")
        gesehen.add(kid)
        kette.append(str(knoten.get("title") or knoten.get("slug") or kid))
        parent = _parent_schluessel(knoten)
        knoten = aufloesung.get(parent) if parent else None
    return [buch_titel, *reversed(kette)]


def baue_eintraege(content_zeilen: list[dict], buch_titel: str,
                   html_zu_markdown) -> tuple[list[dict], dict]:
    """Content-Zeilen -> Vertragseintraege + Zaehler fuer den Abdeckungsbericht."""
    # Auf id UND cobalt_id abbilden - so greift die Parent-Aufloesung unabhaengig davon,
    # worauf ParentID im jeweiligen Buch verweist (id_kollisionsfrei: cobalt_id ist ein
    # Slug-String, numerische IDs kollidieren praktisch nicht).
    aufloesung: dict[str, dict] = {}
    for z in content_zeilen:
        aufloesung[str(z["id"])] = z
        if z.get("cobalt_id"):
            aufloesung.setdefault(str(z["cobalt_id"]), z)
    eintraege: list[dict] = []
    leer = unbekannt = fehlende_parents = 0

    def _sortschluessel(x):
        s = str(x["id"])
        return (0, int(s), "") if s.isdigit() else (1, 0, s)   # numerisch vor String

    for z in sorted(content_zeilen, key=_sortschluessel):
        body = html_zu_markdown(z.get("html") or "")
        if not body.strip():
            leer += 1                                   # leere Containerzeilen zaehlen
            continue
        parent = _parent_schluessel(z)
        if parent and parent not in aufloesung:
            fehlende_parents += 1
        # Strukturierte Eintraege (aus Detailtabellen) tragen ihre Kategorie schon und
        # haben keine Hierarchie -> Kategorie beibehalten, flacher Breadcrumb.
        if z.get("category"):
            kategorie = z["category"]
            krume = [buch_titel, str(z.get("title") or z["id"])]
        else:
            krume = _breadcrumb(z, aufloesung, buch_titel)
            kategorie = kategorie_aus_breadcrumb(krume)
            if kategorie == "regel":
                unbekannt += 1                          # Fallback-Pfade sichtbar machen
        slug = str(z.get("slug") or "")
        eintraege.append({
            "ddb_id": str(z["id"]),
            "cobalt_id": str(z.get("cobalt_id") or "") or None,
            "parent_id": str(z["parent_id"]) if z.get("parent_id") not in (None, "")
            else None,
            "slug": slug or None,
            "title": str(z.get("title") or slug or z["id"]),
            "breadcrumb": krume,
            "category": kategorie,
            "source_url": f"https://www.dndbeyond.com/sources/{slug}" if slug else None,
            "body_md": body,
            "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        })
    zaehler = {"leer": leer, "unbekannte_kategorie": unbekannt,
               "fehlende_parents": fehlende_parents}
    return eintraege, zaehler


def schreibe_artefakt(basis_verzeichnis: Path, buch: dict, eintraege: list[dict],
                      zaehler: dict, export_id: str, exported_at: str) -> Path:
    """Schreibt das Artefakt atomar; die abschliessende Validierung laeuft mit dem
    ECHTEN Vertrags-Validator gegen das fertige Verzeichnis."""
    ziel = basis_verzeichnis / buch["kuerzel"] / export_id
    if ziel.exists():
        raise ValueError(f"Artefakt {ziel} existiert bereits - Export-ID muss neu sein.")
    partial = ziel.parent / f".partial-{export_id}"
    partial.mkdir(parents=True, exist_ok=False)
    try:
        jsonl = "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in eintraege)
        (partial / "entries.jsonl").write_text(jsonl, encoding="utf-8")
        manifest = {
            "schema_version": SCHEMA_VERSION, "status": "complete",
            "source_key": buch["kuerzel"], "ddb_source_id": buch["id"],
            "title": buch["titel"], "language": buch["sprache"],
            "edition": buch["edition"], "license": buch.get("lizenz", "privat"),
            "exported_at": exported_at, "exporter_version": "1.0.0",
            "book_version": buch.get("version"),
            "entry_count": len(eintraege),
            "empty_content_count": zaehler["leer"],
            "unknown_category_count": zaehler["unbekannte_kategorie"],
            "entries_sha256": hashlib.sha256(jsonl.encode("utf-8")).hexdigest(),
            "archive_sha256": buch.get("archive_sha256", ""),
            # SYN-P0-007: Inhaltsklasse ('regelwerk' | 'abenteuer_setting') wandert bis
            # in quellen.inhaltsart - OPTIONALES Feld, Alt-Artefakte bleiben gueltig.
            "inhaltsart": buch.get("inhaltsart", "regelwerk"),
        }
        (partial / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
        with open(partial / "manifest.json", "rb") as f:
            os.fsync(f.fileno())
        os.replace(partial, ziel)
    except BaseException:
        shutil.rmtree(partial, ignore_errors=True)
        raise
    pruefe_artefakt(ziel, erwartet={"source_key": buch["kuerzel"],
                                    "ddb_source_id": buch["id"],
                                    "language": buch["sprache"],
                                    "edition": buch["edition"]})
    return ziel
