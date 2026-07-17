"""dnddeutsch.de-Anbindung: API-Zugriff, Datei-Cache und Antwort-Auswertung an EINEM Ort.

Gemeinsame Grundlage für das Glossar-Seeding (`importer/import_glossar`) und das
nachfragegetriebene Nachschlagen des Charakterbogen-Übersetzers (16.07.2026): Der Bogen -
nicht der Foliant-Bestand - bestimmt dort, welche Begriffe gebraucht werden.

Bausteine:
- `hole()`: höflicher, gedrosselter API-Zugriff mit persistentem Datei-Cache
  (`data/cache/dnddeutsch`); gecachte Begriffe kosten weder Netz noch Wartezeit.
- `zeilen_aus_antwort()`: EINE Bewertungslogik für beide Nutzer (Ulisses/Buchbeleg ->
  offiziell, Quelle, Edition) inkl. der Klammer-Lemma-Regel.
- `schreibe_zeilen()`: Upsert ins Glossar (Konflikte löst das bestehende
  Kanonisierungs-System des Imports).

Klammer-Lemma-Regel: dnddeutsch führt Grundformen teils mit Zusatz ('Oil (flask)' ->
'Öl (Flasche)'). DDB-Bögen schreiben aber das nackte Lemma ('Oil') - ein exakter Treffer
scheitert, Fuzzy ist bewusst verboten (SYN-P0-001). Ist der Kern EINDEUTIG (genau eine
Klammerform, keine Kollision mit einem exakten Lemma, keine invertierte Kommaform), wird
zusätzlich die Kern-Zeile belegt: deterministisches Lemma-Strippen, kein Raten.
"""
from __future__ import annotations

import json
import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

API_URL = "https://www.dnddeutsch.de/tools/json.php"   # Default; [glossar].api_url gewinnt
PAUSE_S = 1.0                    # Höflichkeits-Drossel nach jedem ECHTEN API-Zugriff
USER_AGENT = "Foliant (privates Glossar-Seeding, gedrosselt)"


def api_url() -> str:
    """[glossar].api_url aus der Konfiguration, sonst der Default."""
    from app import db as _db
    return str((_db.lade_konfig().get("glossar", {}) or {}).get("api_url") or API_URL)


def cache_verzeichnis() -> Path:
    """A8: Cache-Pfad projektroot-relativ, nie abhängig vom Arbeitsverzeichnis."""
    from app import db as _db
    return _db.projekt_pfad("data/cache/dnddeutsch")


def _slug(begriff: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", begriff.lower()).strip("-") or "leer"


def hole(client, begriff: str, pause_s: float = PAUSE_S) -> dict:
    """Antwort aus Cache oder API (dann gedrosselt); Cache macht Re-Runs offline (O2).

    Der Cache ist eine OPTIMIERUNG, keine Pflicht: Ist er nicht beschreibbar (der
    Web-Container läuft `read_only` und mountet ihn absichtlich nur lesend), wird die
    API-Antwort trotzdem geliefert - nur eben nicht gespeichert."""
    cache_datei = _cache_datei(begriff)
    if cache_datei is not None and cache_datei.exists():
        return json.loads(cache_datei.read_text(encoding="utf-8"))
    antwort = client.get(api_url(), params={"s": begriff, "o": "dict"})
    antwort.raise_for_status()
    daten = antwort.json()
    if cache_datei is not None:
        try:
            cache_datei.write_text(json.dumps(daten, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass                        # nur-lesender Cache -> Antwort gilt trotzdem
    time.sleep(pause_s)
    return daten


def _cache_datei(begriff: str) -> Path | None:
    """Cache-Pfad des Begriffs; None, wenn kein Cache-Verzeichnis nutzbar ist."""
    cache = cache_verzeichnis()
    try:
        cache.mkdir(parents=True, exist_ok=True)
    except OSError:
        if not cache.is_dir():
            return None                 # weder vorhanden noch anlegbar -> ohne Cache weiter
    return cache / f"{_slug(begriff)}.json"


def edition_aus_buch(buch: str | None) -> str | None:
    """Konservative Heuristik für edition_quelle (S8/S9): '24' im Buchkürzel -> 2024;
    klassische (de)-Grundbücher -> 2014; sonst unbekannt (NULL) - nicht raten."""
    if not buch:
        return None
    if "24" in buch:
        return "2024"
    if re.match(r"^(PHB|DMG|MM)\(de\)$", buch):
        return "2014"
    return None


@dataclass(frozen=True)
class Zeile:
    term_en: str
    term_de: str
    offiziell: int
    quelle: str
    edition: str | None
    seite: str | None


_KLAMMER_LEMMA = re.compile(r"^(.{2,60}?)\s*\(([^()]{1,40})\)$")


def _ohne_klammer(lemma: str) -> str:
    m = _KLAMMER_LEMMA.match(lemma)
    return m.group(1).strip() if m else lemma


def zeilen_aus_antwort(daten: dict) -> list[Zeile] | None:
    """Bewertet eine dnddeutsch-Antwort zu Glossar-Zeilen. None = Fehlerantwort
    (z.B. >30 Treffer), [] = keine verwertbaren Ergebnisse."""
    ergebnisse = daten.get("result") or []
    if not isinstance(ergebnisse, list):
        return None
    zeilen: list[Zeile] = []
    for r in ergebnisse:
        name_en = (r.get("name_en") or "").strip()
        ulisses = (r.get("name_de_ulisses") or "").strip()
        name_de = ulisses or (r.get("name_de") or "").strip()
        if not name_en or not name_de:
            continue
        src = r.get("src_de") or {}
        offiziell = 1 if (ulisses or src.get("book")) else 0
        quelle = ("Ulisses-Glossar (dnddeutsch.de)" if ulisses
                  else src.get("book_long") or "dnddeutsch.de (Community)")
        zeilen.append(Zeile(name_en, name_de, offiziell, quelle,
                            edition_aus_buch(src.get("book")), src.get("p")))
    return zeilen + _kern_zeilen(zeilen)


def _kern_zeilen(zeilen: list[Zeile]) -> list[Zeile]:
    """Klammer-Lemma-Regel (s. Modul-Docstring). Eindeutigkeit innerhalb der Antwort;
    Konflikte über Antworten hinweg löst das bestehende Kanonisierungs-System."""
    vorhandene = {z.term_en.casefold() for z in zeilen}
    gruppen: dict[str, list[Zeile]] = {}
    for z in zeilen:
        m = _KLAMMER_LEMMA.match(z.term_en)
        if not m:
            continue
        kern = m.group(1).strip()
        if "," in kern:            # 'Rope, hempen (50 feet)': invertierte Form -> nicht raten
            continue
        gruppen.setdefault(kern, []).append(z)
    raus: list[Zeile] = []
    for kern, gz in gruppen.items():
        if kern.casefold() in vorhandene or len(gz) != 1:
            continue               # Kern existiert schon exakt ODER ist mehrdeutig
        z = gz[0]
        raus.append(Zeile(kern, _ohne_klammer(z.term_de), z.offiziell,
                          z.quelle, z.edition, z.seite))
    return raus


def schreibe_zeilen(con: sqlite3.Connection, zeilen: list[Zeile]) -> int:
    """Upsert der Zeilen ins Glossar (ohne Commit - der Aufrufer entscheidet)."""
    for z in zeilen:
        con.execute(
            "INSERT INTO glossar (term_en, term_de, offiziell, quelle, edition_quelle, seite) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(term_en, term_de) DO UPDATE SET offiziell=excluded.offiziell, "
            "quelle=excluded.quelle, edition_quelle=excluded.edition_quelle, "
            "seite=excluded.seite",
            (z.term_en, z.term_de, z.offiziell, z.quelle, z.edition, z.seite))
    return len(zeilen)
