"""Glossar aus dnddeutsch.de-API seeden. Beachten: Wildcard '*' wird hinten automatisch
angehaengt (nicht vorn); >30 Treffer = Fehler (Suchbegriff eng fassen); Ulisses-Begriff =
name_de_ulisses (offiziell). Herkunft/Edition je Begriff speichern (S9/S8).

Echte API (10.07.2026 verifiziert; das '/api/' aus der Beispiel-Config existiert nicht):
  GET https://www.dnddeutsch.de/tools/json.php?s=<begriff>&o=dict
  -> {"result": [{"name_de", "name_de_ulisses", "name_en",
                  "src_de": {"book","book_long","p"}, "type"}, ...]}

Offiziell-Logik (S3/S6): name_de_ulisses vorhanden ODER src_de-Buchbeleg -> offiziell=1
(Stufe 1-2, kein '*'); nur Community-name_de ohne Beleg -> offiziell=0 ('*').

Review-Funde (umgesetzt):
- HOEFLICH DROSSELN: 1 s Pause zwischen echten API-Calls, keine Parallelisierung.
- LOKAL CACHEN: Antworten als JSON unter data/cache/dnddeutsch/ -> Re-Runs (O2) offline.
- UPSERT statt INSERT: Schema erzwingt UNIQUE(term_en, term_de).
- ABKUERZUNGEN PFLEGEN (T7/B3): AoO/HP/AC/... als eigene Glossar-Zeilen (quelle='abkuerzung')."""
from __future__ import annotations

import json
import re
import sqlite3
import sys
import time
from pathlib import Path

API_URL = "https://www.dnddeutsch.de/tools/json.php"   # Default; [glossar].api_url gewinnt
_PAUSE_S = 1.0


def _api_url() -> str:
    """A8: die in config/foliant.toml angebotene [glossar].api_url wird tatsaechlich
    verwendet (Default: API_URL)."""
    from app import db as _db
    return str((_db.lade_konfig().get("glossar", {}) or {}).get("api_url") or API_URL)


def _cache_verzeichnis() -> Path:
    """A8: Cache-Pfad projektroot-relativ, nie abhaengig vom Arbeitsverzeichnis."""
    from app import db as _db
    return _db.projekt_pfad("data/cache/dnddeutsch")

# Kuratierte Kernbegriffe (Zustaende, Kampf, Proben, Erholung, Charakterbau) - die Begriffe,
# die am Spieltisch staendig fallen. Zauber-/Monsternamen kommen spaeter bei Bedarf (O4).
KERNBEGRIFFE_EN = [
    # Zustaende (T3/T7-relevant; im Open5e-2024-Bestand fehlen sie -> Glossar traegt mit)
    "blinded", "charmed", "deafened", "exhaustion", "frightened", "grappled",
    "incapacitated", "invisible", "paralyzed", "petrified", "poisoned", "prone",
    "restrained", "stunned", "unconscious",
    # Kampf & Aktionen
    "opportunity attack", "attack roll", "armor class", "hit points",
    "temporary hit points", "initiative", "action", "bonus action", "reaction",
    "movement", "speed", "difficult terrain", "cover", "critical hit", "damage roll",
    "resistance", "vulnerability", "immunity", "unarmed strike", "grapple", "shove",
    "dash", "disengage", "dodge", "help", "hide", "ready", "search", "attack action",
    "magic action", "surprise", "emanation", "weapon mastery",
    # Proben & Werte
    "saving throw", "ability check", "ability score", "advantage", "disadvantage",
    "difficulty class", "proficiency bonus", "expertise", "skill", "passive perception",
    "strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma",
    # Magie
    "concentration", "ritual", "spell slot", "cantrip", "spellcasting", "spell attack",
    # Erholung & Zustand des Charakters
    "short rest", "long rest", "death saving throw", "hit dice", "heroic inspiration",
    # Charakterbau (Phase 2 nutzt sie schon mit)
    "class", "subclass", "species", "background", "feat", "origin feat", "level",
    "multiclassing", "alignment", "size", "creature type", "challenge rating",
    "experience points", "darkvision", "blindsight", "truesight", "tremorsense",
]

# Abkuerzungen als eigene Glossar-Zeilen (T7: 'AoO' -> selber Eintrag wie 'Gelegenheitsangriff').
# Beide Richtungen, wo am Tisch ueblich: englische Kuerzel (AoO, HP) UND deutsche (RK, SG).
ABKUERZUNGEN: list[tuple[str, str]] = [
    ("AoO", "Gelegenheitsangriff"), ("HP", "Trefferpunkte"), ("AC", "Rüstungsklasse"),
    ("DC", "Schwierigkeitsgrad"), ("CR", "Herausforderungsgrad"), ("XP", "Erfahrungspunkte"),
    ("PB", "Übungsbonus"), ("THP", "Temporäre Trefferpunkte"), ("ASI", "Attributswerterhöhung"),
    ("Armor Class", "RK"), ("Difficulty Class", "SG"), ("Hit Points", "TP"),
]

# Begriffspaare, die dnddeutsch (noch) nicht kennt, die aber aus den BEIDEN SRD-Bestaenden
# belegt sind: SRD 5.2.1 (Deutsch) IST die offizielle Uebersetzung des SRD 5.2 - dieselbe
# Option traegt dort den deutschen, hier den englischen Namen (Phase-2-Fund 10.07.2026:
# ohne diese Paare dedupen die Options-Listen nicht und deutsche Suchen nach z. B.
# 'Boon of Fate' verfehlen den deutschen Eintrag). offiziell=1: beides offizielle Quellen
# (S3 Stufe 1). Zuordnung an den Eintragstexten verifiziert (z. B. Truesight 60 feet =
# Wahrer Blick 18 Meter; Unterklasse samt Klassenzuordnung im srd-de-Namen).
SRD_2024_BEGRIFFSPAARE: list[tuple[str, str]] = [
    # Unterklassen (Rest ist ueber dnddeutsch abgedeckt)
    ("Path of the Berserker", "Pfad des Berserkers"),
    ("Fiend Patron", "Unhold-Schutzherr"),
    ("Warrior of the Open Hand", "Krieger der Offenen Hand"),
    ("Draconic Sorcery", "Drakonische Zauberei"),
    # Epische-Gabe-Talente (Boons)
    ("Boon of Combat Prowess", "Gabe der Kampffertigkeit"),
    ("Boon of Dimensional Travel", "Gabe des Dimensionsreisens"),
    ("Boon of Fate", "Gabe des Schicksals"),
    ("Boon of Irresistible Offense", "Gabe des Unwiderstehlichen Angriffs"),
    ("Boon of Spell Recall", "Gabe der Zaubererinnerung"),
    ("Boon of the Night Spirit", "Gabe des Nachtgeists"),
    ("Boon of Truesight", "Gabe des Wahren Blicks"),
    # 2024-Umbenennung (dnddeutsch fuehrt die 2014-Fassung 'Kampf mit zwei Waffen';
    # S8: der neuere offizielle Begriff gewinnt in der Sortierung)
    ("Two-Weapon Fighting", "Zwei-Waffen-Kampf"),
    # 2024-Flexionsform (dnddeutsch: 'Drachenblütige'; SRD 5.2.1: 'Drachenblütiger')
    ("Dragonborn", "Drachenblütiger"),
    # Zauber, deren 5.2.1-Namen von den dnddeutsch-Begriffen abweichen (2024-Umbenennungen,
    # Schweizer ss-Schreibung, Neuzugaenge). JEDES Paar am Bestand verifiziert: gleicher
    # Zaubergrad + gleiche Schule in beiden SRD-Fassungen (Kuratierung 10.07.2026).
    ("Arcane Hand", "Arkane Hand"),
    ("Arcane Sword", "Arkanes Schwert"),
    ("Arcanist's Magic Aura", "Magische Aura des Arkanisten"),
    ("Befuddlement", "Wirrnis"),
    ("Chain Lightning", "Kettenblitz"),
    ("Conjure Celestial", "Celestisches Wesen beschwören"),
    ("Elementalism", "Elementalismus"),
    ("Enlarge/Reduce", "Vergrößern/Verkleinern"),
    ("Fly", "Flug"),
    ("Glibness", "Redegewandtheit"),
    ("Gust of Wind", "Windstoß"),
    ("Hex", "Verwünschung"),
    ("Instant Summons", "Sofortige Beschwörung"),
    ("Jump", "Sprung"),
    ("Locate Animals or Plants", "Tiere oder Pflanzen aufspüren"),
    ("Mass Suggestion", "Massen-Einflüsterung"),
    ("Resistance", "Widerstand"),
    ("Seeming", "Äußerlichkeiten"),
    ("Shining Smite", "Strahlendes Niederstrecken"),
    ("Sorcerous Burst", "Explosion der Zauberei"),
    ("Spare the Dying", "Verschonung der Sterbenden"),
    ("Starry Wisp", "Sternenfunke"),
    ("Suggestion", "Einflüsterung"),
    ("Summon Dragon", "Drachen herbeirufen"),
    ("Telepathic Bond", "Telepathische Bindung"),
    ("Time Stop", "Zeitstopp"),
    ("Word of Recall", "Wort des Rückrufs"),
]


# Kuratierte Kern-SINGULARE (SYN-P1-006, Synthese 2026-07-12): dnddeutsch liefert fuer
# einige Alltagsbegriffe nur Plural-Zeilen ('Opportunity Attacks') - seit Fuzzy-Treffer
# keine bestaetigte Uebersetzung mehr sind (SYN-P0-001), braucht der Singular eine EXAKTE
# Zeile. Dazu zwei 2024-Neubegriffe ohne dnddeutsch-Eintrag (am Bestand belegt:
# srd-de 'Waffenbeherrschung'-Klassenmerkmal, 'Ausströmung (Wirkungsbereich)').
KERN_SINGULAR_PAARE: list[tuple[str, str, str | None]] = [
    ("Opportunity Attack", "Gelegenheitsangriff", "2024"),
    ("Grappled", "Gepackt", "2024"),
    ("Weapon Mastery", "Waffenbeherrschung", "2024"),
    # PHB-2024-Terminologie 'Waffenmeisterschaft' als zweite offizielle dt. Fassung
    # (claude DND-006): srd-de nutzt 'Waffenbeherrschung', das dt. PHB 'Waffenmeisterschaft'
    # - beide muessen auf denselben Bestandsinhalt bruecken (Zwei-Hop ueber 'Weapon Mastery').
    ("Weapon Mastery", "Waffenmeisterschaft", "2024"),
    ("Mastery Property", "Meisterschaftseigenschaft", "2024"),
    ("Emanation", "Ausströmung", "2024"),
    # Die 8 Meisterschaftseigenschaften (EN offiziell <-> srd-de-Name), damit englische
    # Suchen sie finden und die Begriffe zweisprachig aufloesbar sind (SYN-P1-006):
    ("Topple", "Umstoßen", "2024"),
    ("Cleave", "Spalten", "2024"),
    ("Graze", "Streifen", "2024"),
    ("Nick", "Einkerben", "2024"),
    ("Push", "Stoßen", "2024"),
    ("Sap", "Auslaugen", "2024"),
    ("Slow", "Verlangsamen", "2024"),
    ("Vex", "Plagen", "2024"),
]


def seed_kern_singulare(con: sqlite3.Connection) -> int:
    """Bestands-belegte Singular-/2024-Kernpaare (offline, Upsert)."""
    for term_en, term_de, edition in KERN_SINGULAR_PAARE:
        _upsert(con, term_en, term_de, 1, "Kernbegriff (kuratiert, bestandsbelegt)",
                edition, None)
    con.commit()
    return len(KERN_SINGULAR_PAARE)


def _slug(begriff: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", begriff.lower()).strip("-") or "leer"


def _hole_api(client, begriff: str) -> dict:
    """Antwort aus Cache oder API (dann gedrosselt); Cache macht Re-Runs offline (O2)."""
    cache = _cache_verzeichnis()
    cache.mkdir(parents=True, exist_ok=True)
    cache_datei = cache / f"{_slug(begriff)}.json"
    if cache_datei.exists():
        return json.loads(cache_datei.read_text(encoding="utf-8"))
    antwort = client.get(_api_url(), params={"s": begriff, "o": "dict"})
    antwort.raise_for_status()
    daten = antwort.json()
    cache_datei.write_text(json.dumps(daten, ensure_ascii=False), encoding="utf-8")
    time.sleep(_PAUSE_S)
    return daten


def _edition_aus_buch(buch: str | None) -> str | None:
    """Konservative Heuristik fuer edition_quelle (S8/S9): '24' im Buchkuerzel -> 2024;
    klassische (de)-Grundbuecher -> 2014; sonst unbekannt (NULL) - nicht raten."""
    if not buch:
        return None
    if "24" in buch:
        return "2024"
    if re.match(r"^(PHB|DMG|MM)\(de\)$", buch):
        return "2014"
    return None


def _upsert(con: sqlite3.Connection, term_en: str, term_de: str, offiziell: int,
            quelle: str | None, edition_quelle: str | None, seite: str | None) -> None:
    con.execute(
        "INSERT INTO glossar (term_en, term_de, offiziell, quelle, edition_quelle, seite) "
        "VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(term_en, term_de) DO UPDATE SET offiziell=excluded.offiziell, "
        "quelle=excluded.quelle, edition_quelle=excluded.edition_quelle, seite=excluded.seite",
        (term_en, term_de, offiziell, quelle, edition_quelle, seite))


def seed_glossar(con: sqlite3.Connection, begriffe_en: list[str]) -> int:
    """Holt je Begriff die deutsche Entsprechung; offiziell=1 bei name_de_ulisses ODER
    src_de-Buchbeleg, sonst 0 (-> '*'). Drossel + Cache + Upsert. Gibt die Zahl
    geschriebener Glossar-Zeilen zurueck."""
    import httpx  # nur der Importer braucht Netz (Q7)

    geschrieben = 0
    with httpx.Client(timeout=20.0, headers={"User-Agent": "Foliant (privates Glossar-Seeding, gedrosselt)"}) as client:
        for i, begriff in enumerate(begriffe_en, start=1):
            try:
                daten = _hole_api(client, begriff)
            except Exception as fehler:  # Einzelfehler ueberspringen, Lauf fortsetzen
                print(f"  [{i}/{len(begriffe_en)}] {begriff}: FEHLER {fehler}", file=sys.stderr)
                continue
            ergebnisse = daten.get("result") or []
            if not isinstance(ergebnisse, list):  # >30 Treffer o. ae. -> Fehlerantwort
                print(f"  [{i}/{len(begriffe_en)}] {begriff}: unerwartete Antwort "
                      f"(zu viele Treffer? Begriff enger fassen)", file=sys.stderr)
                continue
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
                # A9: 'ulisses' heisst OFFIZIELL, aber nicht automatisch Edition 2024 -
                # Ulisses uebersetzt seit Jahren auch 2014-Buecher. Die Edition kommt
                # KONSERVATIV aus dem belegten Buch; ohne sicheren Beleg bleibt sie
                # unbekannt (NULL) statt geraten.
                edition = _edition_aus_buch(src.get("book"))
                _upsert(con, name_en, name_de, offiziell, quelle, edition, src.get("p"))
                geschrieben += 1
    con.commit()
    return geschrieben


def seed_glossar_aus_bestand(con: sqlite3.Connection) -> int:
    """Vollseeding (Review-Fund: '~1000+ Begriffe (Zauber+Monster+Items)'): alle englischen
    Eintragsnamen des Bestands durch die dnddeutsch-API schicken - damit deutsche Suchen
    ('Feuerball') ueber die Glossar-Bruecke die englischen Eintraege treffen. Dank Cache
    sind Re-Runs offline; die Drossel macht den Erstlauf bewusst langsam (hoeflich)."""
    # Deutsch-Qualitaet 12.07.2026: 'regel' JETZT mitseeden - Zustaende/Kampf-/Proben-
    # Abschnittsnamen sind echte Fachbegriffe, die dnddeutsch kennt (frueher ausgeschlossen,
    # obwohl der groesste englischsprachige Anteil des bedienten Korpus regel ist). Nicht-
    # Begriffe (lange Kapiteltitel) liefern schlicht keinen Treffer - harmlos, gecacht.
    namen = [r[0] for r in con.execute(
        "SELECT DISTINCT name_en FROM eintraege WHERE name_en IS NOT NULL "
        "AND kategorie IN ('regel','zauber','monster','gegenstand','spezies','klasse',"
        "'hintergrund','talent') ORDER BY name_en")]
    print(f"Vollseeding: {len(namen)} Bestandsnamen (Drossel {_PAUSE_S}s; Cache macht "
          f"Re-Runs offline).", file=sys.stderr)
    return seed_glossar(con, namen)


# Kurze Fuellwoerter, die in einem sauberen Monsternamen vorkommen duerfen; alles andere
# <=2 Zeichen ist ein PDF-Zerlege-Artefakt ('Gar l gy', 'Atterko pp', 'Har ie py').
_NAME_WL = {"der", "die", "das", "des", "dem", "den", "im", "am", "zu", "zum", "zur",
            "vom", "von", "und", "mit", "auf", "aus"}
# Konsonanten-Bigramme, die in echten deutschen (Monster-)Namen praktisch nie vorkommen,
# aber typisch fuer PDF-Zerlege-Garble sind ('Belebtesgfie...' -> 'gf').
_IMPLAUSIBEL = ("gf", "tk", "pk", "gk", "kp", "tg", "dk", "fk", "vk")


def _name_sauber(name: str | None) -> bool:
    """True, wenn der deutsche Name keine offensichtlichen PDF-Zerlege-Artefakte traegt:
    Kurz-Fragmente ('l', 'gy', 'pp' mitten im Namen) ODER unplausible Bigramme ('gfie').
    Konservativ - lieber eine Bruecke weniger als einen kaputten Namen als 'offiziell'
    ins Glossar schreiben (Kernregel: falsches Deutsch ist schlimmer als ein Duplikat)."""
    if not name:
        return False
    for tok in name.replace("-", " ").split():
        t = tok.strip(".,;:()'’`").lower()
        if not t:
            continue
        if len(t) <= 2 and t not in _NAME_WL:
            return False
        if any(b in t for b in _IMPLAUSIBEL):
            return False
    return True


def _finde_monster_paare(con: sqlite3.Connection) -> list[tuple[str, str, tuple]]:
    """Paart dieselbe Kreatur ueber die deutsche (srd-de) und englische (Open5e/DDB)
    SRD-Fassung per STRUKTUR-Fingerabdruck (Typ+HG+RK+TP). Das ist keine Uebersetzungs-
    Vermutung, sondern strukturelle Identitaet desselben offiziellen Statblocks. STRIKT
    1:1: nur wenn ein vollstaendiger Schluessel auf GENAU einen deutschen UND genau einen
    englischen Namen zeigt (sonst nicht raten, B4). Korrupte deutsche Namen (PDF) werden
    ausgeschlossen. Liefert (term_en, term_de, schluessel)."""
    from app import facetten as _f
    from app.glossar import norm_begriff as _norm

    de_by_key: dict[tuple, set[str]] = {}
    en_by_key: dict[tuple, set[str]] = {}
    for r in con.execute("SELECT name_de, name_en, sprache, body_md FROM eintraege "
                         "WHERE kategorie='monster'"):
        key = _f.monster_statschluessel(r["body_md"])
        if any(x is None for x in key):          # unvollstaendiger Statblock -> nicht abgleichen
            continue
        if r["sprache"] == "de" and r["name_de"]:
            de_by_key.setdefault(key, set()).add(r["name_de"])
        elif r["sprache"] == "en" and r["name_en"]:
            en_by_key.setdefault(key, set()).add(r["name_en"])
    paare: list[tuple[str, str, tuple]] = []
    for key, de_namen in de_by_key.items():
        en_namen = en_by_key.get(key, set())
        if len(de_namen) != 1 or len(en_namen) != 1:
            continue                             # nicht eindeutig -> nicht raten
        de_name, en_name = next(iter(de_namen)), next(iter(en_namen))
        if _norm(de_name) == _norm(en_name):     # gleicher Name -> keine Bruecke noetig
            continue
        if not _name_sauber(de_name):            # korrupter dt. Name -> NIE seeden
            continue
        paare.append((en_name, de_name, key))
    return paare


def seed_monster_bruecke_aus_bestand(con: sqlite3.Connection) -> int:
    """Schreibt die per Struktur-Abgleich (_finde_monster_paare) gefundenen Monster-Paare als
    OFFIZIELLE Glossar-Bruecke - so verschmelzen deutsche und englische Fassung desselben
    Monsters in der Suche/Dedup (statt als Dublette 'Goblin Warrior' + 'Goblinkrieger'
    getrennt zu erscheinen). Schliesst die Luecke der 2024-neuen Kreaturen, die dnddeutsch
    (noch) nicht fuehrt. Selbst-bereinigend: verwirft zuerst die eigenen Alt-Zeilen, damit
    ein verbesserter Abgleich keine ueberholten Bruecken zuruecklaesst. Gibt die Zahl
    geschriebener Zeilen zurueck."""
    con.execute("DELETE FROM glossar WHERE quelle = 'SRD 5.2.1 (Strukturabgleich)'")
    n = 0
    for term_en, term_de, _key in _finde_monster_paare(con):
        _upsert(con, term_en, term_de, 1, "SRD 5.2.1 (Strukturabgleich)", "2024", None)
        n += 1
    con.commit()
    return n


def seed_abkuerzungen(con: sqlite3.Connection) -> int:
    """Gaengige Kuerzel als eigene Zeilen (T7/B3); offiziell=1: die Zielbegriffe sind
    offizielles Deutsch, das Kuerzel selbst ist nur ein Suchschluessel."""
    for kurz, lang in ABKUERZUNGEN:
        _upsert(con, kurz, lang, 1, "abkuerzung", None, None)
    con.commit()
    return len(ABKUERZUNGEN)


def seed_srd_paare(con: sqlite3.Connection) -> int:
    """Bestands-belegte SRD-5.2/5.2.1-Begriffspaare (Modul-Doku oben); offline."""
    for term_en, term_de in SRD_2024_BEGRIFFSPAARE:
        _upsert(con, term_en, term_de, 1, "SRD 5.2/5.2.1-Begriffspaar", "2024", None)
    con.commit()
    return len(SRD_2024_BEGRIFFSPAARE)


def kanonisiere_konflikte(con: sqlite3.Connection) -> int:
    """Deutsch-Qualitaet 12.07.2026: wo eine KURATIERTE Fassung (SRD-Paar / Kern-Singular =
    handverifiziert am Bestand) existiert, ist SIE die kanonische offizielle 2024-Fassung.
    Konkurrierende Glossarzeilen mit demselben term_en, aber ABWEICHENDEM term_de
    (dnddeutsch-Alt-/Schweizer-ss-/Tippfehler-Formen wie 'Kugelblitz' statt 'Kettenblitz',
    'Redegewandheit' statt 'Redegewandtheit', 'Windstoss' statt 'Windstoß') werden auf
    offiziell=0 demotet - sie bleiben als Such-/Schreibvariante erhalten, konkurrieren aber
    nicht mehr als zweiter 'offizieller' Begriff (das war das 'falsches Deutsch'-Risiko,
    schlimmer als *). HOMONYME OHNE kuratierte Fassung (Hide -> Fell/Verstecken, Divination ->
    Erkenntnismagie/Weissagung) bleiben UNBERUEHRT. Gibt die Zahl demoteter Zeilen zurueck."""
    kuratiert: dict[str, set[str]] = {}
    for term_en, term_de in SRD_2024_BEGRIFFSPAARE:
        kuratiert.setdefault(term_en.lower(), set()).add(term_de)
    for term_en, term_de, _ed in KERN_SINGULAR_PAARE:
        kuratiert.setdefault(term_en.lower(), set()).add(term_de)
    demotet = 0
    for te, kanonische_de in kuratiert.items():
        for rid, tde in con.execute(
                "SELECT id, term_de FROM glossar WHERE lower(term_en)=? AND offiziell=1",
                (te,)).fetchall():
            if tde not in kanonische_de:
                con.execute("UPDATE glossar SET offiziell=0, "
                            "quelle=coalesce(quelle,'')||' (demotet: kuratierte Fassung ist offiziell)' "
                            "WHERE id=?", (rid,))
                demotet += 1
    con.commit()
    return demotet


if __name__ == "__main__":
    from app import db as _db
    pfad = _db.standard_pfad()
    if not pfad.exists():
        sys.exit(f"DB fehlt: {pfad} -> erst `python db/init_db.py` ausfuehren.")
    con = _db.connect(str(pfad))
    try:
        n = seed_glossar(con, KERNBEGRIFFE_EN)
        a = seed_abkuerzungen(con)
        p = seed_srd_paare(con)
        k = seed_kern_singulare(con)
        b = seed_glossar_aus_bestand(con)
        d = kanonisiere_konflikte(con)
        print(f"Fertig: {n} Kern-Zeilen, {a} Abkuerzungen, {p} SRD-Paare, {k} Kern-Singulare, "
              f"{b} Zeilen aus Bestandsnamen, {d} Konflikte kanonisiert.")
    finally:
        con.close()
