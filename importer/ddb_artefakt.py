"""DDB-Artefaktvertrag Version 1 (Validator + Kategorien-Mapping) — architekturneutral.

Der kurzlebige DDB-Exporter (separater Prozess mit Netz+Secret, noch nicht gebaut -
Machbarkeits-Gate, s. docs/ddb-architektur-entscheidung.md) schreibt pro Buch ein
unveraenderliches Artefakt:

    data/private/ddb-artifacts/<quellenkuerzel>/<export-id>/
      manifest.json     (Metadaten, Zaehler, Hashes)
      entries.jsonl     (eine Zeile je logischem Buch-Datensatz)

Dieser Validator ist die EINZIGE Eintrittspruefung des Offline-Imports: Er kennt weder
HTTP noch Cobalt noch Entschluesselung und laeuft vollstaendig offline. Der Vertrag wird
mit synthetischen Fixtures getestet (tests/fixtures/ddb/); echte Buchtexte, Schluessel
oder API-Antworten gehoeren nie in Fixtures (Leitplanken des DDB-Auftrags)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

SCHEMA_VERSIONEN = {1}
KATEGORIEN_ERLAUBT = {"regel", "zauber", "monster", "gegenstand", "spezies", "klasse",
                      "hintergrund", "talent"}
_MANIFEST_PFLICHT = ["schema_version", "status", "source_key", "ddb_source_id", "title",
                     "language", "edition", "license", "exported_at", "entry_count",
                     "entries_sha256"]
_EINTRAG_PFLICHT = ["ddb_id", "title", "breadcrumb", "category", "body_md", "body_sha256"]

# Zentrales, deterministisches Kategorien-Mapping (Breadcrumb-Signal -> Foliant-Kategorie).
# Der Exporter nutzt es beim Schreiben, der Validator als erlaubte Zielmenge; unbekannte
# Pfade werden 'regel' und im Manifest gezaehlt (unknown_category_count) - nie geraten.
_BREADCRUMB_SIGNALE = [
    ("spells", "zauber"),
    ("monsters", "monster"), ("bestiary", "monster"),
    ("equipment", "gegenstand"), ("magic items", "gegenstand"),
    ("classes", "klasse"),
    ("species", "spezies"), ("races", "spezies"),
    ("backgrounds", "hintergrund"),
    ("feats", "talent"),
]


def kategorie_aus_breadcrumb(breadcrumb: list[str]) -> str:
    """Mappt den VOLLSTAENDIGEN Breadcrumb (nicht nur den Zeilentitel) auf die
    Foliant-Kategorie; alles Unbekannte ist 'regel' (im Abdeckungsbericht gezaehlt)."""
    pfad = " > ".join(b.lower() for b in breadcrumb if b)
    for signal, kategorie in _BREADCRUMB_SIGNALE:
        if signal in pfad:
            return kategorie
    return "regel"


def _sha256_datei(pfad: Path) -> str:
    h = hashlib.sha256()
    with open(pfad, "rb") as f:
        for block in iter(lambda: f.read(1 << 16), b""):
            h.update(block)
    return h.hexdigest()


def pruefe_artefakt(verzeichnis: str | Path, erwartet: dict | None = None) -> dict:
    """Validiert ein Artefakt vollstaendig, BEVOR irgendetwas eine Datenbank beruehrt.
    erwartet: secret-freie Buch-Konfiguration ({source_key, ddb_source_id, language,
    edition, ...}) - Manifestwerte muessen exakt uebereinstimmen (nichts wird geraten).
    Rueckgabe: {"manifest": dict, "eintraege": list[dict]}; jeder Verstoss -> ValueError."""
    verzeichnis = Path(verzeichnis)
    if verzeichnis.name.startswith(".partial"):
        raise ValueError(f"Artefakt {verzeichnis.name}: unvollstaendiges "
                         f"'.partial'-Verzeichnis ist niemals importierbar.")
    manifest_pfad = verzeichnis / "manifest.json"
    eintraege_pfad = verzeichnis / "entries.jsonl"
    for p in (manifest_pfad, eintraege_pfad):
        if not p.is_file():
            raise ValueError(f"Artefakt unvollstaendig: {p.name} fehlt in {verzeichnis}.")

    manifest = json.loads(manifest_pfad.read_text(encoding="utf-8"))
    fehlt = [f for f in _MANIFEST_PFLICHT if manifest.get(f) in (None, "")]
    if fehlt:
        raise ValueError(f"Manifest: Pflichtfelder fehlen/leer: {', '.join(fehlt)}.")
    if manifest["status"] != "complete":
        raise ValueError(f"Manifest: status={manifest['status']!r} - nur 'complete' ist "
                         f"importierbar.")
    if manifest["schema_version"] not in SCHEMA_VERSIONEN:
        raise ValueError(f"Manifest: unbekannte schema_version "
                         f"{manifest['schema_version']!r} (bekannt: "
                         f"{sorted(SCHEMA_VERSIONEN)}).")
    for feld in ("source_key", "ddb_source_id", "language", "edition"):
        if erwartet is not None and feld in erwartet \
                and manifest.get(feld) != erwartet[feld]:
            raise ValueError(f"Manifest passt nicht zur Konfiguration: {feld}="
                             f"{manifest.get(feld)!r}, erwartet {erwartet[feld]!r}.")

    ist_hash = _sha256_datei(eintraege_pfad)
    if ist_hash != manifest["entries_sha256"]:
        raise ValueError("entries.jsonl-Hash stimmt nicht mit dem Manifest ueberein - "
                         "Artefakt beschaedigt oder manipuliert.")

    eintraege: list[dict] = []
    ids: set[str] = set()
    nicht_leer = 0
    with open(eintraege_pfad, encoding="utf-8") as f:
        for nr, zeile in enumerate(f, start=1):
            if not zeile.strip():
                continue
            e = json.loads(zeile)
            fehlt = [x for x in _EINTRAG_PFLICHT if e.get(x) in (None, "")]
            if fehlt:
                raise ValueError(f"entries.jsonl Zeile {nr}: Pflichtfelder fehlen: "
                                 f"{', '.join(fehlt)}.")
            if e["category"] not in KATEGORIEN_ERLAUBT:
                raise ValueError(f"entries.jsonl Zeile {nr}: unbekannte Kategorie "
                                 f"{e['category']!r}.")
            if not isinstance(e["breadcrumb"], list):
                raise ValueError(f"entries.jsonl Zeile {nr}: breadcrumb muss eine Liste sein.")
            if hashlib.sha256(e["body_md"].encode("utf-8")).hexdigest() != e["body_sha256"]:
                raise ValueError(f"entries.jsonl Zeile {nr}: body_sha256 stimmt nicht.")
            eid = str(e["ddb_id"])
            if eid in ids:
                raise ValueError(f"entries.jsonl Zeile {nr}: doppelte ddb_id {eid!r}.")
            ids.add(eid)
            if e["body_md"].strip():
                nicht_leer += 1
            eintraege.append(e)

    if len(eintraege) != manifest["entry_count"]:
        raise ValueError(f"entry_count={manifest['entry_count']} passt nicht zu "
                         f"{len(eintraege)} Zeilen.")
    if nicht_leer == 0:
        raise ValueError("Artefakt enthaelt keinen einzigen nicht-leeren Eintrag - ein "
                         "leeres Buch ist ein Fehler.")
    # Parent-Graph: Zyklen sind ein Fehler; fehlende Parents nur zaehlen (nicht raten).
    # ParentID referenziert je nach Buch die ddb_id ODER die cobalt_id (DDB-Quirk) -
    # beide gelten als aufloesbar, damit der Bericht mit dem Exporter uebereinstimmt.
    aufloesbar = set(ids) | {str(e["cobalt_id"]) for e in eintraege if e.get("cobalt_id")}
    parents = {str(e["ddb_id"]): str(e["parent_id"]) for e in eintraege
               if e.get("parent_id") not in (None, "")}
    for start in parents:
        gesehen, knoten = set(), start
        while knoten in parents:
            if knoten in gesehen:
                raise ValueError(f"Parent-Zyklus an ddb_id {start!r}.")
            gesehen.add(knoten)
            knoten = parents[knoten]
    fehlende_parents = sum(1 for p in parents.values() if p not in aufloesbar)
    return {"manifest": manifest, "eintraege": eintraege,
            "fehlende_parents": fehlende_parents}
