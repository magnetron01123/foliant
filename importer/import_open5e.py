"""Open5e-Import (MVP-Quelle). EINMALIGER Import von api.open5e.com/v2 -> gleiches `eintraege`-
Schema (BP #7); KEIN Laufzeit-API-Aufruf (Runtime bleibt offline, Q7).
Englisch -> zur Laufzeit mit dt. Begriffen annotiert (S3-Fallback, app.tools._anzeige_name).
seite bleibt NULL (F7: Seite optional). Nur gewuenschte Dokumente ziehen, editionsgetaggt
(srd-2024 / srd-2014); unbekannte Dokument-Keys werden ABGELEHNT statt geraten (Q3).

VERLUSTSICHER (A7): Abruf und Transformation laufen VOLLSTAENDIG, bevor irgendein
Altbestand geloescht wird - HTTP-/JSON-/Paginationfehler und leere Antworten lassen den
vorhandenen Bestand unangetastet; unplausibles Schrumpfen verlangt erlaube_schrumpfen.
Pagination folgt nur https-URLs des konfigurierten Hosts, erkennt Zyklen und ist hart
gedeckelt (A10). Die Funktion COMMITTET NICHT selbst - der Aufrufer fuehrt die
Transaktion (`with con: ...`), inkl. FTS-Rebuild in derselben Transaktion.
Quirks -> app/bekannte_macken.py."""
from __future__ import annotations

import sqlite3
import sys
import time

from importer.import_markdown import SCHRUMPF_SCHWELLE

API_BASE = "https://api.open5e.com/v2/"   # Default; [open5e].api_base gewinnt (A8)
_PAUSE_S = 0.3           # hoefliche Drossel zwischen Requests (freies Community-Projekt)
_PRIORITAET_BASIS = 60   # geringere Praezedenz als deutsche Quellen (Q2; kleiner = Vorrang)
_MAX_SEITEN = 500        # harte Obergrenze je Endpunkt (A10: keine endlose Pagination)


def _api_base() -> str:
    """A8: die in config/foliant.toml angebotene [open5e].api_base wird tatsaechlich
    verwendet; nur https, mit Slash am Ende (Basis der Pagination-Host-Pruefung)."""
    from app import db as _db
    basis = str((_db.lade_konfig().get("open5e", {}) or {}).get("api_base") or API_BASE)
    if not basis.startswith("https://"):
        raise ValueError(f"[open5e].api_base muss https sein, nicht {basis!r} (A10).")
    return basis if basis.endswith("/") else basis + "/"

# Dokument-Key -> Pflicht-Edition (V1/Q3). Unbekannte Keys -> Fehler, nicht raten.
_EDITIONEN = {"srd-2024": "2024", "srd-2014": "2014"}

# (Endpunkt, kategorie); items VOR weapons/armor (deren Details werden hineingemergt).
_ENDPUNKTE = [("rules", "regel"), ("conditions", "regel"), ("spells", "zauber"),
              ("creatures", "monster"), ("items", "gegenstand"), ("weapons", "gegenstand"),
              ("armor", "gegenstand"), ("species", "spezies"), ("classes", "klasse"),
              ("backgrounds", "hintergrund"), ("feats", "talent")]


# ---------- Markdown-Formatter (englische Labels: Quelle ist englisch; Deutsch macht ----------
# ---------- Claude bei der Ausgabe nach S3 - hier zaehlt vollstaendiger Regelinhalt) ----------

def _zeile(paare: list[tuple[str, object]]) -> str:
    return " · ".join(f"**{k}:** {v}" for k, v in paare if v not in (None, "", [], {}))


def _bloecke(liste: list | None, titel: str | None = None) -> str:
    """[{name, desc}, ...] -> '**Name.** desc'-Absaetze (traits/actions/benefits...)."""
    if not liste:
        return ""
    teile = [f"\n#### {titel}\n"] if titel else []
    for b in liste:
        name, desc = (b.get("name") or "").strip(), (b.get("desc") or "").strip()
        if name and desc:
            teile.append(f"**{name}.** {desc}")
        elif name or desc:
            teile.append(name or desc)
    return "\n\n".join(teile)


def _speed(s: dict | None) -> str:
    if not isinstance(s, dict):
        return ""
    unit = s.get("unit", "feet")
    return ", ".join(f"{art} {wert} {unit}" for art, wert in s.items()
                     if art != "unit" and isinstance(wert, (int, float)) and wert)


def _md_spell(r: dict) -> str:
    komp = [k for k, da in (("V", r.get("verbal")), ("S", r.get("somatic")),
                            ("M", r.get("material"))) if da]
    material = f" ({r['material_specified']})" if r.get("material_specified") else ""
    klassen = ", ".join(k.get("name", "") for k in r.get("classes") or [])
    # A10: strukturierte Wirkfelder der v2-API nicht verwerfen (Fixture-belegt:
    # damage_roll/damage_types, shape_type/shape_size, attack_roll).
    schaden = f"{r.get('damage_roll') or ''} {', '.join(r.get('damage_types') or [])}".strip()
    form = (f"{r.get('shape_size') or ''} {r.get('shape_size_unit') or ''} "
            f"{r.get('shape_type') or ''}".strip()
            if r.get("shape_type") else "")
    # SYN-P1-008: Reaktionszauber (Shield, Counterspell) sind ohne ihren Ausloeser
    # ("which you take when ...") nicht regelkonform einsetzbar - reaction_condition
    # (Fixture-belegt, bei Nicht-Reaktionen null) deshalb wie im offiziellen
    # Zauberblock direkt an die Casting Time anhaengen.
    zeit = r.get("casting_time")
    if r.get("reaction_condition"):
        zeit = f"{zeit}, {r['reaction_condition']}" if zeit else r["reaction_condition"]
    kopf = [
        _zeile([("Level", r.get("level")),
                ("School", (r.get("school") or {}).get("name")), ("Classes", klassen)]),
        _zeile([("Casting Time", zeit), ("Range", r.get("range_text")),
                ("Components", ", ".join(komp) + material if komp else "")]),
        _zeile([("Duration", r.get("duration")),
                ("Concentration", "yes" if r.get("concentration") else ""),
                ("Ritual", "yes" if r.get("ritual") else "")]),
        _zeile([("Damage", schaden), ("Shape", form),
                ("Attack Roll", "yes" if r.get("attack_roll") else "")]),
    ]
    teile = [z for z in kopf if z] + [r.get("desc") or ""]
    if r.get("higher_level"):
        teile.append(f"**At Higher Levels.** {r['higher_level']}")
    return "\n\n".join(t for t in teile if t)


def _nutzungs_limit(ul: dict | None) -> str:
    """usage_limits ({type, param}) -> Statblock-Kuerzel: RECHARGE laedt ab param auf
    dem W6 neu ('Recharge 5–6'), PER_DAY ist ein Tageskontingent ('2/Day'). Unbekannte
    Typen lesbar durchreichen statt still verwerfen (A10). Felder wie uses_per_day/
    recharge_on_roll gibt es in v2 NICHT - die Fixtures belegen nur usage_limits."""
    if not isinstance(ul, dict) or not ul.get("type"):
        return ""
    typ, param = str(ul["type"]), ul.get("param")
    if typ == "RECHARGE":
        return "Recharge 6" if param == 6 else (f"Recharge {param}–6" if param else "Recharge")
    if typ == "PER_DAY":
        return f"{param}/Day" if param is not None else "Per Day"
    return typ.replace("_", " ").title() + (f" {param}" if param is not None else "")


def _aktions_name(a: dict) -> str:
    """SYN-P1-008: Nutzungsgrenzen gehoeren in den Aktionsnamen (offizieller
    Statblock-Stil, englisch wie die Quelle) - ohne sie wirkt z. B. der Vampir-Charm
    unbegrenzt statt 'Recharge 5–6' und der Biss gestaltunabhaengig. Kosten
    legendaerer Aktionen erst ab 2 nennen: 1 ist der stillschweigende Normalfall,
    und die Fixtures tragen legendary_action_cost 1 auch an NORMALEN Aktionen
    (Aboleth-Tentacle, API-Modellierung) - '(Costs 1 Action)' waere dort irrefuehrend."""
    kosten = a.get("legendary_action_cost")
    zusaetze = [z for z in (
        _nutzungs_limit(a.get("usage_limits")),
        (a.get("limited_to_form") or "").strip(),
        f"Costs {kosten} Actions" if isinstance(kosten, (int, float)) and kosten > 1 else "",
    ) if z]
    name = (a.get("name") or "").strip()
    return f"{name} ({'; '.join(zusaetze)})" if name and zusaetze else name


def _md_creature(r: dict) -> str:
    scores, mods = r.get("ability_scores") or {}, r.get("modifiers") or {}
    attr = ", ".join(
        f"{name[:3].upper()} {wert} ({mods.get(name, (wert - 10) // 2):+d})"
        for name, wert in scores.items())
    saves = ", ".join(f"{k[:3].title()} {v:+d}" for k, v in (r.get("saving_throws") or {}).items())
    skills = ", ".join(f"{k.replace('_', ' ').title()} {v:+d}"
                       for k, v in (r.get("skill_bonuses") or {}).items())
    ac_detail = f" ({r['armor_detail']})" if r.get("armor_detail") else ""
    hp_dice = f" ({r['hit_dice']})" if r.get("hit_dice") else ""
    cr = r.get("challenge_rating")
    xp = f" ({r['experience_points']} XP)" if r.get("experience_points") else ""
    # A10: Sinne/Sichtweiten und Resistenzen/Immunitaeten der v2-API nicht verwerfen
    # (Fixture-belegt: *_range-Felder + resistances_and_immunities.*_display).
    sinne = ", ".join(f"{name} {r[feld]} ft."
                      for feld, name in (("darkvision_range", "Darkvision"),
                                         ("blindsight_range", "Blindsight"),
                                         ("tremorsense_range", "Tremorsense"),
                                         ("truesight_range", "Truesight"))
                      if r.get(feld))
    ri = r.get("resistances_and_immunities") or {}
    # SYN-P1-008: initiative_bonus ist im 2024-Statblock Kopfbestandteil - Kreaturen
    # wuerfeln damit (nicht zwingend mit dem blossen DEX-Mod, vgl. Vampir +14).
    init = r.get("initiative_bonus")
    kopf = [
        _zeile([("Type", f"{(r.get('size') or {}).get('name', '')} "
                         f"{(r.get('type') or {}).get('name', '')}".strip()),
                ("Alignment", r.get("alignment")),
                ("CR", f"{cr}{xp}" if cr is not None else None)]),
        _zeile([("AC", f"{r.get('armor_class')}{ac_detail}" if r.get("armor_class") else None),
                ("Initiative", f"{int(init):+d}" if init is not None else None),
                ("HP", f"{r.get('hit_points')}{hp_dice}" if r.get("hit_points") else None),
                ("Speed", _speed(r.get("speed")))]),
        f"**Abilities:** {attr}" if attr else "",
        _zeile([("Saves", saves), ("Skills", skills),
                ("Senses", sinne),
                ("Passive Perception", r.get("passive_perception")),
                ("Languages", (r.get("languages") or {}).get("as_string"))]),
        _zeile([("Damage Resistances", ri.get("damage_resistances_display")),
                ("Damage Immunities", ri.get("damage_immunities_display")),
                ("Damage Vulnerabilities", ri.get("damage_vulnerabilities_display")),
                ("Condition Immunities", ri.get("condition_immunities_display"))]),
    ]
    aktionen: dict[str, list] = {}
    for a in r.get("actions") or []:
        # SYN-P1-008: Kopie mit angereichertem Namen (Recharge/Form/Kosten) -
        # _bloecke bleibt generisch fuer alle anderen Endpunkte.
        aktionen.setdefault(a.get("action_type") or "ACTION", []).append(
            {**a, "name": _aktions_name(a)})
    titel = {"ACTION": "Actions", "BONUS_ACTION": "Bonus Actions", "REACTION": "Reactions",
             "LEGENDARY_ACTION": "Legendary Actions", "LAIR_ACTION": "Lair Actions"}
    teile = [z for z in kopf if z] + [r.get("desc") or "",
                                      _bloecke(r.get("traits"), "Traits")]
    for typ, liste in aktionen.items():
        teile.append(_bloecke(liste, titel.get(typ, typ.title())))
    return "\n\n".join(t for t in teile if t)


def _md_weapon_details(r: dict) -> str:
    props, mastery = [], []
    for p in r.get("properties") or []:
        prop = p.get("property") or {}
        (mastery if prop.get("type") == "Mastery" else props).append(prop)
    teile = [_zeile([("Damage", f"{r.get('damage_dice', '')} "
                                f"{(r.get('damage_type') or {}).get('name', '')}".strip()),
                     ("Range", f"{r.get('range')}/{r.get('long_range')} ft."
                      if r.get("range") else None),
                     ("Type", "simple weapon" if r.get("is_simple") else "martial weapon")])]
    if props:
        teile.append("**Properties:** " + ", ".join(p.get("name", "") for p in props))
    for m in mastery:  # Waffenmeisterschaft (Weapon Mastery) - 2024-Kernfeature
        teile.append(f"**Mastery — {m.get('name')}.** {m.get('desc', '')}")
    return "\n\n".join(t for t in teile if t)


def _md_armor_details(r: dict) -> str:
    return _zeile([("AC", r.get("ac_display")), ("Category", r.get("category")),
                   ("Stealth", "disadvantage" if r.get("grants_stealth_disadvantage") else ""),
                   ("Strength required", r.get("strength_score_required"))])


def _md_item(r: dict) -> str:
    kosten = f"{r['cost']} gp" if r.get("cost") else None
    gewicht = f"{r['weight']} {r.get('weight_unit', 'lb')}" if r.get("weight") else None
    kopf = _zeile([("Category", (r.get("category") or {}).get("name")),
                   ("Cost", kosten), ("Weight", gewicht)])
    return "\n\n".join(t for t in [kopf, r.get("desc") or ""] if t)


def _md_klasse(r: dict) -> str:
    hp = r.get("hit_points") or {}
    kopf = _zeile([("Hit Die", hp.get("hit_dice_name") or r.get("hit_dice")),
                   ("Saving Throws", ", ".join(s.get("name", "")
                                               for s in r.get("saving_throws") or [])),
                   ("Caster Type", (r.get("caster_type") or "").title()
                    if r.get("caster_type") not in (None, "NONE") else "")])
    features = r.get("features") or []
    if features and not any(f.get("desc") for f in features):
        feat_md = "**Features:** " + ", ".join(f.get("name", "") for f in features)
    else:
        feat_md = _bloecke(features, "Features")
    teile = [kopf, r.get("desc") or "", feat_md]
    if r.get("subclass_of"):
        sub = r["subclass_of"]
        name = sub.get("name") if isinstance(sub, dict) else str(sub)
        teile.insert(0, f"*Subclass of: {name}*")
    return "\n\n".join(t for t in teile if t)


def _md_generisch(r: dict, listen_feld: str | None = None) -> str:
    teile = [r.get("desc") or ""]
    if listen_feld:
        teile.append(_bloecke(r.get(listen_feld)))
    return "\n\n".join(t for t in teile if t)


def _body_md(endpunkt: str, r: dict) -> str:
    if endpunkt == "spells":
        return _md_spell(r)
    if endpunkt == "creatures":
        return _md_creature(r)
    if endpunkt == "items":
        return _md_item(r)
    if endpunkt == "weapons":
        return _md_weapon_details(r)
    if endpunkt == "armor":
        return _md_armor_details(r)
    if endpunkt == "classes":
        return _md_klasse(r)
    if endpunkt == "species":
        return _md_generisch(r, "traits")
    if endpunkt in ("backgrounds", "feats"):
        return _md_generisch(r, "benefits")
    return _md_generisch(r)  # rules, conditions


def _facetten(endpunkt: str, r: dict) -> dict | None:
    """Strukturierte Filter-Facetten NUR aus den bereits geparsten Open5e-Feldern
    (KEIN Prosa-Parsing -> B1-risikoarm): Zauber grad/schule/klassen, Monster HG/typ.
    Seitenwagen zur eintraege-Zeile (zauber_meta/monster_meta), ersetzt body_md nie.
    Fehlt ein Feld, bleibt es None (ein Filter mis-filtert dann bloss, statt zu raten).
    HG als String (Open5e liefert Dezimal '0.25'/'0.5'/'1.0' bzw. Zahl - vereinheitlicht)."""
    if endpunkt == "spells":
        klassen = ", ".join(k.get("name", "") for k in r.get("classes") or []).strip(", ")
        grad = r.get("level")
        return {"tabelle": "zauber_meta",
                "werte": (grad if isinstance(grad, int) else None,
                          (r.get("school") or {}).get("name") or None,
                          klassen or None)}
    if endpunkt == "creatures":
        cr = r.get("challenge_rating")
        return {"tabelle": "monster_meta",
                "werte": (str(cr) if cr is not None else None,
                          (r.get("type") or {}).get("name") or None)}
    return None


def _schreibe_facetten(con: sqlite3.Connection, quelle_id: int, chunks: dict) -> tuple[int, int]:
    """Befuellt zauber_meta/monster_meta additiv aus den in den chunks abgelegten
    Facetten (c['meta'] aus _facetten). Verknuepfung ueber (kategorie, name_en) ->
    eintrag_id - innerhalb EINER Quelle eindeutig, weil chunks nach (kat, name) dedupt.
    Alte *_meta-Zeilen wurden bereits vom DELETE der eintraege per FK ON DELETE CASCADE
    entfernt (setzt PRAGMA foreign_keys=ON voraus - _db.connect() aktiviert es).
    Gibt (Zauber-Facetten, Monster-Facetten) zurueck."""
    id_je = {(kat, ne): eid for eid, kat, ne in con.execute(
        "SELECT id, kategorie, name_en FROM eintraege WHERE quelle_id = ?", (quelle_id,))}
    z_meta, m_meta = [], []
    for c in chunks.values():
        meta, eid = c.get("meta"), id_je.get((c["kategorie"], c["name"]))
        if not meta or eid is None:
            continue
        (z_meta if meta["tabelle"] == "zauber_meta" else m_meta).append((eid, *meta["werte"]))
    if z_meta:
        con.executemany("INSERT INTO zauber_meta (eintrag_id, grad, schule, klassen) "
                        "VALUES (?, ?, ?, ?)", z_meta)
    if m_meta:
        con.executemany("INSERT INTO monster_meta (eintrag_id, hg, typ) VALUES (?, ?, ?)",
                        m_meta)
    return len(z_meta), len(m_meta)


# --------------------------------- API-Zugriff & Import ---------------------------------

def _dok_key(r: dict) -> str:
    """Macke: `document` ist meist Objekt, bei rules ein blanker String."""
    d = r.get("document")
    return d.get("key", "") if isinstance(d, dict) else (d or "")


def _hole_alle(client, endpunkt: str, dokument: str, basis: str) -> list[dict]:
    url = f"{basis}{endpunkt}/"
    params = {"document__key__in": dokument, "limit": 100}
    ergebnisse: list[dict] = []
    gesehen = {url}
    for _ in range(_MAX_SEITEN):
        antwort = client.get(url, params=params)
        params = None  # Folge-URLs (next) tragen ihre Parameter selbst
        if antwort.status_code == 404:
            print(f"  {endpunkt}: Endpunkt existiert nicht (mehr) - uebersprungen",
                  file=sys.stderr)
            return []
        antwort.raise_for_status()
        daten = antwort.json()
        # defensiv doppelt filtern, falls der Server-Filter sich aendert (bekannte_macken)
        ergebnisse += [r for r in daten.get("results", []) if _dok_key(r) == dokument]
        url = daten.get("next")
        if not url:
            return ergebnisse
        # A10: nur erwartete https-URLs des konfigurierten Hosts verfolgen; Zyklen erkennen.
        if not str(url).startswith(basis):
            raise ValueError(f"{endpunkt}: Pagination verweigert - next-URL {url!r} liegt "
                             f"nicht unter dem konfigurierten Open5e-Host ({basis}).")
        if url in gesehen:
            raise ValueError(f"{endpunkt}: Pagination-Zyklus erkannt ({url}) - Abbruch "
                             f"statt Endlosschleife.")
        gesehen.add(url)
        time.sleep(_PAUSE_S)
    raise ValueError(f"{endpunkt}: Pagination ueberschreitet {_MAX_SEITEN} Seiten - "
                     f"Abbruch (unplausibel grosse Antwort).")


# A10: korrekte Lizenz je Dokument statt pauschal 'CC-BY-4.0 / OGL'.
_LIZENZEN = {"srd-2024": "CC-BY-4.0", "srd-2014": "OGL-1.0a"}


def _quelle_upsert(con: sqlite3.Connection, kuerzel: str, titel: str, edition: str,
                   prioritaet: int, lizenz: str) -> int:
    """A8: beim Upsert ALLE veraenderbaren Felder konsistent aktualisieren - sonst
    behaelt eine bestehende Quelle stillschweigend alte Lizenz/Prioritaet/Herkunft."""
    con.execute(
        "INSERT INTO quellen (kuerzel, titel, sprache, edition, herkunft, lizenz, prioritaet) "
        "VALUES (?, ?, 'en', ?, 'open5e', ?, ?) "
        "ON CONFLICT(kuerzel) DO UPDATE SET titel=excluded.titel, "
        "sprache=excluded.sprache, edition=excluded.edition, "
        "herkunft=excluded.herkunft, lizenz=excluded.lizenz, "
        "prioritaet=excluded.prioritaet",
        (kuerzel, titel, edition, lizenz, prioritaet))
    return con.execute("SELECT id FROM quellen WHERE kuerzel = ?", (kuerzel,)).fetchone()[0]


def import_open5e(con: sqlite3.Connection, dokumente: list[str] | None = None,
                  erlaube_schrumpfen: bool = False) -> int:
    """Holt alle verfuegbaren Inhaltstypen je Dokument, mappt auf `eintraege`
    (name_en, body_md, edition aus Dokument-Key, sprache='en', seite=NULL,
    Quelle 'open5e-<dokument>' mit prioritaet >= 60). A7: erst VOLLSTAENDIG abrufen und
    transformieren, dann pruefen, dann ersetzen - committet NICHT selbst (Aufrufer:
    `with con: ...`). Gibt die Gesamtzahl zurueck."""
    import httpx  # Import hier: nur der Importer braucht Netz (Q7: Laufzeit offline)

    dokumente = dokumente or ["srd-2024"]
    unbekannt = [d for d in dokumente if d not in _EDITIONEN]
    if unbekannt:
        raise ValueError(f"Dokument(e) ohne bekannte Regelversion: {unbekannt} - Edition "
                         f"wird NICHT geraten (Q3). Mapping in _EDITIONEN ergaenzen.")

    # PHASE 1 (A7): alles abrufen + transformieren, BEVOR irgendetwas geloescht wird.
    # Netz-/JSON-/Paginationfehler werfen hier - der Bestand ist noch unberuehrt.
    basis = _api_base()
    vorbereitet: list[tuple[str, str, str, dict]] = []
    with httpx.Client(timeout=30.0, headers={"User-Agent": "Foliant (privat, einmaliger Import)"}) as client:
        titel_je_dok = {}
        antwort = client.get(f"{basis}documents/", params={"limit": 100})
        antwort.raise_for_status()
        for d in antwort.json().get("results", []):
            titel_je_dok[d.get("key")] = d.get("name", d.get("key"))

        for dokument in dokumente:
            edition = _EDITIONEN[dokument]
            titel = f"{titel_je_dok.get(dokument, dokument)} (Open5e)"
            chunks: dict[tuple[str, str], dict] = {}  # (kategorie, name) -> chunk
            for endpunkt, kategorie in _ENDPUNKTE:
                rohe = _hole_alle(client, endpunkt, dokument, basis)
                for r in rohe:
                    name = (r.get("name") or "").strip()
                    body = _body_md(endpunkt, r)
                    if not name or not body:
                        continue
                    key = (kategorie, name.lower())
                    if key in chunks and endpunkt in ("weapons", "armor"):
                        # Waffen-/Ruestungsmechanik in den vorhandenen items-Eintrag mergen
                        chunks[key]["body"] += f"\n\n{body}"
                    elif key not in chunks:
                        chunks[key] = {"name": name, "kategorie": kategorie, "body": body,
                                       "meta": _facetten(endpunkt, r)}
                print(f"  {dokument}/{endpunkt}: {len(rohe)} Datensaetze")
            if not chunks:
                raise ValueError(f"{dokument}: kein einziger Datensatz von der API - "
                                 f"der alte Bestand bleibt unangetastet (A7).")
            vorbereitet.append((dokument, edition, titel, chunks))

    # PHASE 2 (A7): pruefen + ersetzen, innerhalb der Transaktion des Aufrufers.
    gesamt = 0
    for i, (dokument, edition, titel, chunks) in enumerate(vorbereitet):
        kuerzel = f"open5e-{dokument}"
        alt_zeile = con.execute(
            "SELECT count(e.id) FROM quellen q LEFT JOIN eintraege e ON e.quelle_id = q.id "
            "WHERE q.kuerzel = ?", (kuerzel,)).fetchone()
        alt = alt_zeile[0] if alt_zeile else 0
        if not erlaube_schrumpfen and alt and len(chunks) < alt * SCHRUMPF_SCHWELLE:
            raise ValueError(
                f"{dokument}: Schrumpf-Schutz (A7) - nur {len(chunks)} neue gegenueber "
                f"{alt} bestehenden Eintraegen (< {int(SCHRUMPF_SCHWELLE * 100)} %). "
                f"Wenn beabsichtigt: erlaube_schrumpfen=True bzw. --force.")
        quelle_id = _quelle_upsert(con, kuerzel, titel, edition, _PRIORITAET_BASIS + i,
                                   _LIZENZEN.get(dokument, "siehe Open5e-Dokument"))
        con.execute("DELETE FROM eintraege WHERE quelle_id = ?", (quelle_id,))  # idempotent
        con.executemany(
            "INSERT INTO eintraege (quelle_id, kategorie, name_de, name_en, sprache, "
            "edition, seite, body_md) VALUES (?, ?, NULL, ?, 'en', ?, NULL, ?)",
            [(quelle_id, c["kategorie"], c["name"], edition, c["body"])
             for c in chunks.values()])
        z_n, m_n = _schreibe_facetten(con, quelle_id, chunks)
        print(f"{dokument}: {len(chunks)} Eintraege vorbereitet (Edition {edition}), "
              f"{z_n} Zauber- + {m_n} Monster-Facetten")
        gesamt += len(chunks)
    # FTS-Rebuild in DERSELBEN Transaktion (Leitplanke + A7).
    con.execute("INSERT INTO eintraege_fts(eintraege_fts) VALUES('rebuild')")
    return gesamt


if __name__ == "__main__":
    from app import db as _db
    pfad = _db.standard_pfad()
    if not pfad.exists():
        sys.exit(f"DB fehlt: {pfad} -> erst `python db/init_db.py` ausfuehren.")
    con = _db.connect(str(pfad))
    try:
        dokumente = (_db.lade_konfig().get("open5e", {}) or {}).get("dokumente") or ["srd-2024"]
        with con:  # A7: eine Transaktion fuer Ersetzen + FTS-Rebuild
            n = import_open5e(con, dokumente)
        print(f"Fertig: {n} Eintraege, FTS neu aufgebaut.")
    finally:
        con.close()
