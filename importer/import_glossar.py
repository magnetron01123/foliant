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

from app import dnddeutsch

API_URL = dnddeutsch.API_URL                     # Default; [glossar].api_url gewinnt
_PAUSE_S = dnddeutsch.PAUSE_S


def _api_url() -> str:
    """A8: die in config/foliant.toml angebotene [glossar].api_url wird tatsaechlich
    verwendet (Default: API_URL)."""
    return dnddeutsch.api_url()


def _cache_verzeichnis() -> Path:
    """A8: Cache-Pfad projektroot-relativ, nie abhaengig vom Arbeitsverzeichnis."""
    return dnddeutsch.cache_verzeichnis()

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
    # Heldische Inspiration: srd-de-Regeleintrag UND vorgedrucktes Feld des offiziellen
    # dt. Charakterbogens 2024 (Befund 16.07.2026: LLM erfand "Heldenhafte Inspiration"
    # direkt neben dem Vordruck "HELDISCHE INSPIRATION").
    ("Heroic Inspiration", "Heldische Inspiration", "2024"),
    # Physische Schadensarten (352 srd-de-Einträge belegen Wucht-/Stich-/Hiebschaden;
    # Befund 16.07.2026: ohne Vorgabe schwankte das LLM zwischen "Wuchtschaden" und
    # "stumpfer Schaden" je Lauf).
    ("Bludgeoning", "Wucht", "2024"),
    ("Piercing", "Stich", "2024"),
    ("Slashing", "Hieb", "2024"),
]


def seed_kern_singulare(con: sqlite3.Connection) -> int:
    """Bestands-belegte Singular-/2024-Kernpaare (offline, Upsert)."""
    for term_en, term_de, edition in KERN_SINGULAR_PAARE:
        _upsert(con, term_en, term_de, 1, "Kernbegriff (kuratiert, bestandsbelegt)",
                edition, None)
    con.commit()
    return len(KERN_SINGULAR_PAARE)


# Die 12 Aktionen der 2024-Regeln: EN = kanonische SRD-Aktionsnamen, DE = srd-de-Regelglossar
# ("<Name> (Aktion)"-Eintraege). Kuratiert, aber beim Seeden BESTANDSVERIFIZIERT: eine Zeile
# wird nur geschrieben, wenn der srd-de-Eintrag existiert (nichts raten, Datenprinzip).
# "Magie wirken" ist die Tabellen-/Anzeigeform der srd-de (Eintrag "Magie (Aktion)").
QUELLE_AKTIONEN = "SRD 5.2.1 (Aktionen)"
AKTIONS_PAARE: list[tuple[str, str, str]] = [
    ("Attack", "Angriff", "Angriff (Aktion)"),
    ("Dash", "Spurt", "Spurt (Aktion)"),
    ("Disengage", "Rückzug", "Rückzug (Aktion)"),
    ("Dodge", "Ausweichen", "Ausweichen (Aktion)"),
    ("Help", "Helfen", "Helfen (Aktion)"),
    ("Hide", "Verstecken", "Verstecken (Aktion)"),
    ("Influence", "Beeinflussen", "Beeinflussen (Aktion)"),
    ("Magic", "Magie wirken", "Magie (Aktion)"),
    ("Ready", "Vorbereiten", "Vorbereiten (Aktion)"),
    ("Search", "Suchen", "Suchen (Aktion)"),
    ("Study", "Studieren", "Studieren (Aktion)"),
    ("Utilize", "Verwenden", "Verwenden (Aktion)"),
]


def seed_aktionen(con: sqlite3.Connection) -> int:
    """2024-Aktionsnamen als Glossar-Bruecken, je Paar gegen den srd-de-Bestand verifiziert.
    Die EN-Lemmata sind Alltagswoerter (Attack, Magic, Hide ...) -> sie stehen in
    glossar._HOMONYM_STOP und werden vom Inline-Annotator NIE benutzt; die exakte Suche
    (foliant_uebersetze_begriff, Charakterbogen-Uebersetzer) nutzt sie voll."""
    n = 0
    for term_en, term_de, beleg in AKTIONS_PAARE:
        (vorhanden,) = con.execute(
            "SELECT COUNT(*) FROM eintraege e JOIN quellen q ON q.id = e.quelle_id "
            "WHERE q.kuerzel = 'srd-de' AND e.name_de = ?", (beleg,)).fetchone()
        if not vorhanden:
            continue                       # kein srd-de-Beleg -> Zeile entfaellt (nicht raten)
        _upsert(con, term_en, term_de, 1, QUELLE_AKTIONEN, "2024", None)
        n += 1
    con.commit()
    return n


# API-Zugriff, Cache und Antwort-Bewertung leben seit 16.07.2026 in app/dnddeutsch.py
# (gemeinsame Grundlage mit dem nachfragegetriebenen Lookup des Charakterbogen-Übersetzers).
# Die duennen Wrapper hier bleiben fuer Tests/Aufrufer stabil (Monkeypatch auf _hole_api).

def _slug(begriff: str) -> str:
    return dnddeutsch._slug(begriff)


def _hole_api(client, begriff: str) -> dict:
    """Antwort aus Cache oder API (dann gedrosselt); Cache macht Re-Runs offline (O2)."""
    return dnddeutsch.hole(client, begriff, pause_s=_PAUSE_S)


def _edition_aus_buch(buch: str | None) -> str | None:
    return dnddeutsch.edition_aus_buch(buch)


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
            # Bewertung (Ulisses/Buchbeleg -> offiziell, konservative Edition, A9) und die
            # Klammer-Lemma-Regel liegen zentral in app/dnddeutsch.zeilen_aus_antwort.
            zeilen = dnddeutsch.zeilen_aus_antwort(daten)
            if zeilen is None:  # >30 Treffer o. ae. -> Fehlerantwort
                print(f"  [{i}/{len(begriffe_en)}] {begriff}: unerwartete Antwort "
                      f"(zu viele Treffer? Begriff enger fassen)", file=sys.stderr)
                continue
            geschrieben += dnddeutsch.schreibe_zeilen(con, zeilen)
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


def seed_glossar_de_aus_bestand(con: sqlite3.Connection) -> int:
    """RUECKWAERTS-Seeding: deutsche Eintragsnamen OHNE englisches Gegenstueck bei
    dnddeutsch abfragen.

    Das Vollseeding (seed_glossar_aus_bestand) fragt mit ENGLISCHEN Namen - fuer die
    deutschen 2014-Baende gibt es aber keine englische Ausgabe im Bestand, ihre Begriffe
    blieben deshalb ohne Bruecke (47 Zaubernamen allein aus Xanathar). Die API loest
    auch deutsche Begriffe auf (verifiziert 27.07.2026: Chaospfeil -> Chaos Bolt,
    Donnerschritt -> Thunder Step, Seelenkaefig -> Soul Cage) - genau dieser Weg
    erschliesst sie.

    Abgefragt werden nur PLAUSIBLE Fachbegriffe ohne bestehendes exaktes Gegenstueck:
    Kapitelkoepfe und Fliesstext-Fragmente wuerden nur die Drossel belasten (die API
    antwortet dort schlicht leer - harmlos, aber gecacht kostet es trotzdem Zeit)."""
    from app import glossar as _glossar

    kandidaten = []
    for (name,) in con.execute(
            "SELECT DISTINCT name_de FROM eintraege WHERE sprache='de' "
            "AND name_de IS NOT NULL ORDER BY name_de"):
        sauber = (name or "").strip()
        # Fachbegriffe sind kurz und wortartig; alles andere ist Kapitel-/Layout-Rest.
        if not (2 <= len(sauber.split()) <= 4 or (sauber and len(sauber.split()) == 1)):
            continue
        if len(sauber) < 4 or len(sauber) > 48 or any(c.isdigit() for c in sauber):
            continue
        if not _name_sauber(sauber):
            continue
        if any(z["match"] == "exakt"
               for z in _glossar.lookup(con, sauber, richtung="de_en")):
            continue                       # Bruecke existiert bereits
        kandidaten.append(sauber)
    print(f"Rueckwaerts-Seeding: {len(kandidaten)} deutsche Begriffe ohne Gegenstueck "
          f"(Drossel {_PAUSE_S}s; Cache macht Re-Runs offline).", file=sys.stderr)
    return seed_glossar(con, kandidaten)


# Kurze Fuellwoerter, die in einem sauberen Monsternamen vorkommen duerfen; alles andere
# <=2 Zeichen ist ein PDF-Zerlege-Artefakt ('Gar l gy', 'Atterko pp', 'Har ie py').
_NAME_WL = {"der", "die", "das", "des", "dem", "den", "im", "am", "zu", "zum", "zur",
            "vom", "von", "und", "mit", "auf", "aus"}


def _name_sauber(name: str | None) -> bool:
    """True, wenn der deutsche Name keine PDF-Zerlege-Kurzfragmente traegt ('Gar l gy' -> 'l',
    'Atterko pp' -> 'pp'). Sicherheitsnetz fuer die Bruecke; die bekannten korrupten Namen
    werden ohnehin vorher per MONSTER_NAME_REPARATUR korrigiert. BEWUSST OHNE Bigramm-Heuristik:
    'dk'/'tk' u. ae. stehen in echten deutschen Komposita an der Wortfuge (Schild-kroete,
    Kobold-krieger, Grottenschrat-krieger) und wurden faelschlich als korrupt aussortiert."""
    if not name:
        return False
    for tok in name.replace("-", " ").split():
        t = tok.strip(".,;:()'’`").lower()
        # Ziffern/Zahlen sind legitime kurze Tokens ('Auf 0 Trefferpunkte', '1W10 Effekt') -
        # nur BUCHSTABEN-Kurzfragmente ('l', 'gy', 'pp') sind Zerlege-Artefakte.
        if t and len(t) <= 2 and t not in _NAME_WL and not any(c.isdigit() for c in t):
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
    de_by_teil: dict[tuple, set[str]] = {}
    en_by_teil: dict[tuple, set[str]] = {}
    attr_von: dict[str, tuple] = {}              # lesbare Attributstabelle je Name
    for r in con.execute("SELECT name_de, name_en, sprache, body_md FROM eintraege "
                         "WHERE kategorie='monster'"):
        key = _f.monster_statschluessel(r["body_md"])
        teil = key[:4]                           # (typ, hg, rk, tp) ohne Attributstabelle
        name = r["name_de"] if r["sprache"] == "de" else r["name_en"]
        if name and key[4] is not None:
            attr_von[name] = key[4]
        if r["sprache"] == "de" and r["name_de"]:
            if not any(x is None for x in key):
                de_by_key.setdefault(key, set()).add(r["name_de"])
            if not any(x is None for x in teil):
                de_by_teil.setdefault(teil, set()).add(r["name_de"])
        elif r["sprache"] == "en" and r["name_en"]:
            if not any(x is None for x in key):
                en_by_key.setdefault(key, set()).add(r["name_en"])
            if not any(x is None for x in teil):
                en_by_teil.setdefault(teil, set()).add(r["name_en"])

    def _eindeutige(de_namen: set[str], en_namen: set[str]) -> tuple[str, str] | None:
        if len(de_namen) != 1 or len(en_namen) != 1:
            return None                          # nicht eindeutig -> nicht raten
        de_name, en_name = next(iter(de_namen)), next(iter(en_namen))
        if _norm(de_name) == _norm(en_name):     # gleicher Name -> keine Bruecke noetig
            return None
        if not _name_sauber(de_name):            # korrupter dt. Name -> NIE seeden
            return None
        return en_name, de_name

    paare: list[tuple[str, str, tuple]] = []
    for key, de_namen in de_by_key.items():
        p = _eindeutige(de_namen, en_by_key.get(key, set()))
        if p:
            paare.append((*p, key))
    # Stufe 2 (Teil-Fingerabdruck): Statbloecke mit unlesbarer Attributstabelle
    # (srd-de 'Koboldkrieger') fielen aus Stufe 1, obwohl (typ, hg, rk, tp) beidseitig
    # eindeutig auf dieselbe Kreatur zeigt. Ausschlussprinzip NACH Abzug der bereits
    # gepaarten Namen - der Teil-Schluessel darf nie ein Stufe-1-Paar umdeuten.
    vergeben = {n for en, de, _k in paare for n in (en, de)}
    for teil, de_namen in de_by_teil.items():
        p = _eindeutige(de_namen - vergeben, en_by_teil.get(teil, set()) - vergeben)
        if not p:
            continue
        en_name, de_name = p
        a_de, a_en = attr_von.get(de_name), attr_von.get(en_name)
        if a_de is not None and a_en is not None and a_de != a_en:
            continue    # beidseitig lesbare, ABWEICHENDE Attribute = verschiedene Kreaturen
        paare.append((en_name, de_name, teil))
    return paare


# Rest-NOTFALL (srd-de-Zerlegungen mit Buchstaben-VERLUST, beide Male ein fehlendes 'l'
# in 'flieg...'): kein sicheres Anagramm-/Sequenz-Signal, also dokumentierte Einzelfixe.
# Ziele autoritativ belegt: 'Belebtes fliegendes Schwert' aus dem PDF-Inhaltsverzeichnis;
# 'Riesenfliege' hat KEINEN TOC-Anker (Statblock im Magische-Gegenstaende-Anhang), die
# korrekte Form steht aber im Fliesstext des Bestands (Befund 26.07.2026, Monster-
# Bruecken-Vorschau haette sonst den Tippfehler als offizielles Deutsch geseedet).
# Alles andere loest der Algorithmus (importer.namensreparatur) selbst.
SRD_DE_NAME_NOTFALL = {"Belebtesgfie endes Schwert": "Belebtes fliegendes Schwert",
                       "Riesenfiege": "Riesenfliege"}


def repariere_srd_de_namen(con: sqlite3.Connection) -> int:
    """Korrigiert aus der srd-de-PDF zerlegte Eintragsnamen ALGORITHMISCH gegen die autoritative
    Namensliste der Quelle - das PDF-Inhaltsverzeichnis + die sauberen Bestandsnamen
    (importer.namensreparatur: Kurzfragment->Anagramm, Leerzeichen-Anomalie->TOC-Form; KEIN
    festes corrupt->korrekt, nur EIN Rest-Notfall mit Buchstabenverlust). Idempotent (saubere
    Namen bleiben unberuehrt); FTS-Rebuild bei Aenderung. Der Name ist mitindiziert."""
    from app import db as _db
    from importer import namensreparatur as nr

    pdf = next((q.get("dateipfad") for q in _db.lade_konfig().get("quelle", [])
                if q.get("kuerzel") == "srd-de"), None)
    toc = nr.toc_namen(str(_db.projekt_pfad(pdf))) if pdf else []
    namen = [r[0] for r in con.execute(
        "SELECT DISTINCT e.name_de FROM eintraege e JOIN quellen q ON q.id = e.quelle_id "
        "WHERE q.kuerzel = 'srd-de' AND e.name_de IS NOT NULL")]
    korrekturen = nr.repariere(namen, list(set(toc + namen)), _name_sauber, toc_namen=toc)
    korrekturen.update({k: v for k, v in SRD_DE_NAME_NOTFALL.items() if k in namen})
    n = 0
    for falsch, richtig in korrekturen.items():
        n += con.execute("UPDATE eintraege SET name_de = ? WHERE name_de = ?",
                         (richtig, falsch)).rowcount
    con.commit()
    if n:
        _db.fts_rebuild(con)
    return n


# Typische OCR-Schaeden in den 2014-Scans, die den Namen VERGLEICHBAR machen, ohne ihn
# zu raten: zerrissene Komposita ('SEELEN KÄFIG'), verdoppelte Woerter ('FERN SCHRITT
# SCHRITT', 'INVESTITUR DES DES GESTEIN S' - der Scanner las eine Zeilenumbruch-Silbe
# doppelt) und angehaengte Satzzeichen ('OTTOS UNWIDERSTEHLICHER TANZ.').
def _namensvarianten(name: str) -> list[str]:
    """Vergleichsformen eines moeglicherweise zerrissenen Namens - KEINE Korrektur:
    welche Variante gilt, entscheidet erst der Beleg (Glossar oder dnddeutsch)."""
    roh = re.sub(r"[.,;:]+$", "", (name or "").strip())
    varianten = [roh]
    ohne_dopplung = re.sub(r"\b(\w+)(\s+\1)+\b", r"\1", roh, flags=re.I)
    if ohne_dopplung != roh:
        varianten.append(ohne_dopplung)
    for v in list(varianten):
        # Einzelne verirrte Endbuchstaben anhaengen ('GESTEIN S' -> 'GESTEINS')
        geklebt = re.sub(r"\b(\w{3,})\s+(\w)\b", r"\1\2", v)
        if geklebt != v:
            varianten.append(geklebt)
    return varianten


def repariere_2014_namen(con: sqlite3.Connection, mit_netz: bool = True) -> int:
    """Zerrissene Eintragsnamen der deutschen 2014-Scans reparieren - BELEGT, nie geraten.

    Zwei Belegquellen, in dieser Reihenfolge:
      1. das Glossar selbst (3000+ kuratierte deutsche Begriffe),
      2. dnddeutsch (die Autoritaet fuer deutsche Begriffe) - nur wenn die Antwort die
         Variante EXAKT bestaetigt.
    Ein Treffer muss eindeutig sein und `_name_sauber` bestehen; sonst bleibt der Name
    unberuehrt. Damit werden Namen wie 'SEELEN KÄFIG' zu 'Seelenkäfig' - und erst dadurch
    per Suche und Uebersetzung auffindbar (Befund 27.07.2026: 27 deutsche Zauber ohne
    Gegenstueck, die Mehrzahl davon nur wegen des zerrissenen Namens)."""
    from app import glossar as _glossar
    from app import db as _db

    def vergleichsform(s: str) -> str:
        """Normalisiert UND entspacet - genau der Schaden, um den es geht: 'SEELEN KÄFIG'
        und 'Seelenkäfig' muessen dieselbe Form ergeben, sonst findet der Abgleich nie
        etwas (norm_begriff allein laesst Leerzeichen stehen)."""
        return re.sub(r"[\s-]+", "", _glossar.norm_begriff(s))

    referenz = {}
    for z in _glossar._alle_zeilen(con):
        if z["term_de"]:
            referenz.setdefault(vergleichsform(z["term_de"]), z["term_de"])

    namen = [r[0] for r in con.execute(
        "SELECT DISTINCT e.name_de FROM eintraege e JOIN quellen q ON q.id = e.quelle_id "
        "WHERE q.kuerzel LIKE '%2014-de' AND e.name_de IS NOT NULL")]
    offen: list[tuple[str, list[str]]] = []
    korrekturen: dict[str, str] = {}
    for name in namen:
        if _name_sauber(name) and _glossar.norm_begriff(name) in {
                _glossar.norm_begriff(w) for w in referenz.values()}:
            continue                                   # bereits exakt die belegte Form
        varianten = _namensvarianten(name)
        ziel = next((referenz[vergleichsform(v)] for v in varianten
                     if vergleichsform(v) in referenz), None)
        if ziel and _name_sauber(ziel) and ziel != name:
            korrekturen[name] = ziel
        elif len(varianten) > 1 or " " in name.strip():
            offen.append((name, varianten))

    if mit_netz and offen:
        import httpx
        with httpx.Client(timeout=20.0, headers={"User-Agent": "Foliant (Namensreparatur)"}) as client:
            for name, varianten in offen:
                for variante in varianten:
                    entspacet = re.sub(r"\s+", "", variante)
                    if len(entspacet) < 5:
                        continue
                    try:
                        daten = _hole_api(client, entspacet)
                    except Exception:
                        continue
                    zeilen = dnddeutsch.zeilen_aus_antwort(daten) or []
                    passend = {z.term_de for z in zeilen
                               if _glossar.norm_begriff(z.term_de) == _glossar.norm_begriff(entspacet)}
                    if len(passend) == 1:
                        ziel = next(iter(passend))
                        if _name_sauber(ziel):
                            korrekturen[name] = ziel
                            dnddeutsch.schreibe_zeilen(con, zeilen)
                        break

    n = 0
    for falsch, richtig in korrekturen.items():
        n += con.execute("UPDATE eintraege SET name_de = ? WHERE name_de = ?",
                         (richtig, falsch)).rowcount
        print(f"  name-2014: {falsch!r} -> {richtig!r}", file=sys.stderr)
    con.commit()
    if n:
        _db.fts_rebuild(con)
        _glossar._GLOSSAR_CACHE.clear()
    return n


def kanonisiere_schreibvarianten(con: sqlite3.Connection) -> int:
    """Regelbasiert & QUELLENGETRIEBEN (keine Einzelentscheidung des Admins, keine kuratierte
    Wortliste): hat EIN englischer Begriff mehrere OFFIZIELLE deutsche Formen, die dieselbe
    Bezeichnung sind (unterscheiden sich NUR in ß/ss oder Gross-/Kleinschreibung), entscheidet
    die QUELLEN-PRIORITAET, welche kanonisch bleibt - exakt dieselbe Leiter, mit der Foliant
    auch Eintrags-Dubletten aufloest (glossar._auswahlschluessel: belegte Buchquelle vor
    Community, neuere Edition vor aelterer). ß-vor-ss nur als deterministischer Orthografie-
    Tiebreak, wenn die Quellenprioritaet gleich ist. Die uebrigen Formen -> offiziell=0
    (bleiben Such-/Schreibvariante). Echte Dual-Uebersetzungen/Homonyme (NICHT fold-gleich,
    z. B. Hide->Fell/Verstecken) bleiben unberuehrt. Skaliert auf neue Quellen ohne Kuratierung
    (jede Quelle bringt ihre Prioritaet mit). Gibt die Zahl demoteter Zeilen zurueck."""
    import unicodedata
    from collections import defaultdict

    from app.glossar import _auswahlschluessel

    def fold(s):
        return "".join(c for c in unicodedata.normalize("NFKD", s.lower().replace("ß", "ss"))
                       if not unicodedata.combining(c))

    def prioritaet(z):
        # Quellenprioritaet zuerst (kanonische Regel OHNE ihren alphabetischen End-Anker),
        # dann ß>ss als deterministischer Orthografie-Tiebreak, zuletzt alphabetisch. So
        # entscheidet die QUELLE - nicht der Admin und keine Grammatik-Vermutung.
        return (_auswahlschluessel(z)[:-1], 0 if "ß" in (z["term_de"] or "") else 1,
                z["term_de"] or "")

    grp: dict[str, list] = defaultdict(list)
    for r in con.execute("SELECT id, term_en, term_de, offiziell, quelle, edition_quelle "
                         "FROM glossar WHERE offiziell=1 "
                         "AND coalesce(quelle,'') NOT LIKE 'abkuerzung%'"):
        grp[r["term_en"].lower()].append(dict(r))
    demotet = 0
    for zeilen in grp.values():
        formen = {z["term_de"] for z in zeilen}
        if len(formen) < 2 or len({fold(f) for f in formen}) != 1:
            continue                              # nur PURE Schreibvarianten; Homonyme unberuehrt
        kanon = min(zeilen, key=prioritaet)["term_de"]
        for z in zeilen:
            if z["term_de"] != kanon:
                con.execute("UPDATE glossar SET offiziell=0 WHERE id=?", (z["id"],))
                demotet += 1
    con.commit()
    return demotet


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


def seed_klassenmerkmale_aus_bestand(con: sqlite3.Connection) -> int:
    """2024-Klassenmerkmalsnamen (inkl. Sub-Features wie Schlaghagel/Windschritt) als
    OFFIZIELLE Glossar-Bruecke per Struktur-Abgleich srd-de <-> ddb-br-2024-en (Modul
    importer/srd_klassenmerkmale). Schliesst die Charakterbogen-Luecke 'Angriffe abwehren*'
    statt amtlich 'Angriffe umleiten'. Selbst-bereinigend; Apostroph-Varianten (U+2019/')
    werden beide belegt. Braucht die Klassennamen-Bruecke im Glossar -> NACH dem
    dnddeutsch-Seeding laufen. Auf einer DB ohne ddb-br-2024-en (Mac-Subset) findet der
    Abgleich schlicht nichts - harmlos, der Pi-Lauf traegt die Paare."""
    from app import glossar as _glossar
    from importer.srd_klassenmerkmale import (QUELLE, apostroph_varianten, en_subnamen,
                                              finde_container_sub_paare, finde_paare)
    # LIKE-Praefix: kanonisiere_konflikte haengt an demotete Zeilen ein '(demotet: ...)'
    # an die Quelle - ein exakter Vergleich liesse solche Alt-Zeilen als Zombies stehen
    # (real: 'Weapon Mastery -> Zauberwirken (demotet)' ueberlebte den Re-Lauf).
    con.execute("DELETE FROM glossar WHERE quelle LIKE ?", (QUELLE + "%",))
    # Cache leeren, sonst saehe der Ausschluss-Abgleich die soeben GELOESCHTEN eigenen
    # Alt-Zeilen noch als 'belegt' (und ein Re-Lauf wuerde alte Fehlpaare fortschreiben).
    _glossar._GLOSSAR_CACHE.clear()
    paare, report = finde_paare(con)
    # Spezies-/Talent-Sub-Features ('Fey Ancestry') sind KEINE Eintragsnamen - das
    # Vollseeding hat sie nie bei dnddeutsch angefragt. Hier gezielt nachholen (Cache
    # macht Re-Runs offline), damit die belegte-Paare-Stufe der Container-Paarung greift.
    subnamen = sorted({s for kat in ("spezies", "talent") for s in en_subnamen(con, kat)})
    if subnamen:
        seed_glossar(con, subnamen)
        _glossar._GLOSSAR_CACHE.clear()
    for kategorie in ("spezies", "talent"):
        p2, r2 = finde_container_sub_paare(con, kategorie)
        paare += [p for p in p2 if p not in paare]
        report += r2
    n = 0
    for term_en, term_de in paare:
        for variante in apostroph_varianten(term_en):
            _upsert(con, variante, term_de, 1, QUELLE, "2024", None)
            n += 1
    for zeile in report:
        print(f"  klassenmerkmale: {zeile}", file=sys.stderr)
    con.commit()
    _glossar._GLOSSAR_CACHE.clear()   # Folge-Seeder sollen die neuen Paare sehen
    return n


def seed_gegenstands_bruecke_aus_bestand(con: sqlite3.Connection) -> int:
    """Gegenstands-Paare per Struktur-Abgleich (Preis-Bucket + Glossar-Hop/Ausschluss,
    Modul importer/srd_begriffsbruecken) als OFFIZIELLE Bruecke - schliesst die groesste
    Audit-Luecke (Open5e-Preissuffixe liessen das dnddeutsch-Seeding leerlaufen).
    Selbst-bereinigend; belegt vollen Namen UND suffixfreie Kurzform. Auf einer DB ohne
    open5e-srd-2024 findet der Abgleich schlicht nichts - harmlos (Subset-Muster)."""
    from app import glossar as _glossar
    from importer.srd_begriffsbruecken import (QUELLE, finde_gegenstands_paare,
                                               seed_paar)
    con.execute("DELETE FROM glossar WHERE quelle LIKE ?", (QUELLE + "%",))
    _glossar._GLOSSAR_CACHE.clear()   # geloeschte Alt-Zeilen duerfen nicht als 'belegt' zaehlen
    paare, report = finde_gegenstands_paare(con)
    n = 0
    gesehen: set[tuple[str, str]] = set()
    for term_en, term_de, _stufe in paare:
        v_en, v_de = seed_paar(term_en, term_de)
        if (v_en, v_de) in gesehen:
            continue
        gesehen.add((v_en, v_de))
        # Bereits belegte Paare (z. B. dnddeutsch) NICHT kapern: der Upsert wuerde ihre
        # quelle ueberschreiben und die Selbstbereinigung des naechsten Laufs loeschte
        # dann eine fremde Zeile, falls der Abgleich sie nicht wiederfindet.
        belegt = {_glossar.norm_begriff(z["term_de"])
                  for z in _glossar.lookup(con, v_en, richtung="en_de")
                  if z["match"] == "exakt"}
        if _glossar.norm_begriff(v_de) in belegt:
            continue
        _upsert(con, v_en, v_de, 1, QUELLE, "2024", None)
        n += 1
    for zeile in report:
        print(f"  gegenstaende: {zeile}", file=sys.stderr)
    con.commit()
    _glossar._GLOSSAR_CACHE.clear()
    return n


def seed_zauber_bruecke_aus_bestand(con: sqlite3.Connection) -> int:
    """Zauber-Paare ueber den Zauberkopf (Modul importer/srd_zauberbruecken) als
    OFFIZIELLE Bruecke - editionsuebergreifend (S7: der alte offizielle Begriff gilt
    ohne '*', S8: der neuere gewinnt). Schliesst die Luecke, die mit den deutschen
    2014-Baenden entstand: ~290 deutsche Zaubernamen ohne Glossar-Gegenstueck.
    Selbst-bereinigend; nur beidseitig eindeutige Abdruecke, Widersprueche zu belegten
    Zeilen werden verworfen und gemeldet."""
    from app import glossar as _glossar
    from importer.srd_zauberbruecken import QUELLE, finde_zauber_paare

    con.execute("DELETE FROM glossar WHERE quelle LIKE ?", (QUELLE + "%",))
    _glossar._GLOSSAR_CACHE.clear()   # geloeschte Alt-Zeilen nicht als 'belegt' zaehlen
    paare, report = finde_zauber_paare(con)
    n = 0
    for term_en, term_de, _beweis in paare:
        # edition_quelle bewusst OFFEN (None): der Abdruck belegt die Begriffsgleichheit,
        # nicht aus welcher Regelfassung der deutsche Name stammt - und geraten wird nichts.
        _upsert(con, term_en, term_de, 1, QUELLE, None, None)
        n += 1
    for zeile in report:
        print(f"  zauber: {zeile}", file=sys.stderr)
    con.commit()
    _glossar._GLOSSAR_CACHE.clear()
    return n


def seed_kernwortschatz_aus_bestand(con: sqlite3.Connection) -> int:
    """SRD-Kernwortschatz (Fertigkeiten, Groessen, Kreaturentypen) QUELLENGETRIEBEN aus dem
    Bestand herleiten und als offizielle Bruecke schreiben (Modul importer/srd_kernwortschatz).
    Schliesst die Luecke, dass foliant_uebersetze_begriff('Acrobatics') und der Charakterbogen-
    Uebersetzer diese Kernbegriffe nicht kannten. Selbst-bereinigend (verwirft die eigenen
    Alt-Zeilen). Braucht die Monster-Bruecke -> nach seed_monster_bruecke_aus_bestand laufen."""
    from importer.srd_kernwortschatz import QUELLE, finde_kernbegriffe
    con.execute("DELETE FROM glossar WHERE quelle = ?", (QUELLE,))
    paare, _verworfen = finde_kernbegriffe(con)
    for term_en, term_de, _kat, _n in paare:
        _upsert(con, term_en, term_de, 1, QUELLE, "2024", None)
    con.commit()
    return len(paare)


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
