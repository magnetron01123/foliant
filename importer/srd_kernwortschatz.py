"""SRD-Kernwortschatz-Bruecke: Fertigkeiten, Groessenkategorien und Kreaturentypen
QUELLENGETRIEBEN aus dem Bestand herleiten (Datenprinzip: regelbasiert, nie geraten).

BEFUND 15.07.2026: Das Glossar kannte `Stealth -> Heimlichkeit`, aber NICHT `Acrobatics`,
`Perception`, `Medium` (Groesse), `Creature Type` und ~30 weitere SRD-KERNBEGRIFFE.
`foliant_uebersetze_begriff("Acrobatics")` lief ins Leere, und der Charakterbogen-Uebersetzer
markierte "Mittelgross*" als unbelegte Wiedergabe, obwohl der deutsche SRD den Begriff fuehrt.

ZWEI FRAGEN, ZWEI QUELLEN - daher dieser Aufbau:

1. WELCHES englische Lemma gehoert zu WELCHEM deutschen?  -> aus den STATBLOECKEN.
   srd-de und die englischen SRD-Fassungen beschreiben DIESELBEN Kreaturen; die bestehende
   Monster-Bruecke (`_finde_monster_paare`) paart sie strukturell 1:1.
   - Fertigkeiten: dieselbe Kreatur listet dieselben Fertigkeiten mit DENSELBEN Boni ->
     der Bonus ist der Anker ("Perception +4" <-> "Wahrnehmung +4"). Nur EINDEUTIGE Boni
     zaehlen; kommt ein Bonus zweimal vor, waere die Zuordnung geraten -> uebersprungen (B4).
   - Groesse/Typ: die Kopfzeile ("Medium Monstrosity" <-> "Mittelgroße Monstrosität").

2. WIE lautet die deutsche GRUNDFORM?  -> aus den REGELTABELLEN des srd-de.
   Deutsch flektiert: im Statblock steht "Kleines/Kleiner/Kleine". Lernte man das Lemma aus
   dem Statblock, landete "Kleines" im Glossar - falsches Deutsch. Die Regeltabellen drucken
   die unflektierte Grundform; der Statblock liefert NUR die Zuordnung.

GEGEN DIE ZWEI FALLEN, an denen naives Paaren scheitert:
- Die Fertigkeiten-Tabellen sind in BEIDEN Sprachen alphabetisch sortiert - aber JE IN IHRER
  EIGENEN Sprache. Ueber den Zeilenindex zu paaren erzeugt 16 von 18 Paaren FALSCH
  ("Arkane Kunde" steht auf Position 2, dort steht englisch "Animal Handling").
- Bei mehrgroessigen Kreaturen KIPPT die Reihenfolge: EN "Medium or Small" <-> DE "Kleiner
  oder mittelgroßer". Solche Kopfzeilen werden fuer die GROESSE verworfen (der Typ bleibt gueltig).

EINBAU-KANAL (wichtig!): Viele dieser Lemmata sind HOMONYME - "Medium armor" heisst
"mittelschwere Ruestung", NICHT "mittelgross"; "Giant" ist auch eine Sprache (Riesisch).
Sie duerfen deshalb NICHT vom kontextfreien Inline-Annotator `glossar.begriffe_im_text()`
benutzt werden -> `glossar._HOMONYM_STOP`. Die EXAKTE Suche (`term_de`, also
`foliant_uebersetze_begriff` und der Charakterbogen, wo das FELD den Kontext liefert) nutzt
sie voll. Ohne diese Trennung wuerde der Seed die Deutsch-Qualitaet SENKEN statt heben.
"""
from __future__ import annotations

import re
import sqlite3
from collections import Counter, defaultdict

QUELLE = "SRD 5.2.1 (Kernwortschatz)"

# --- 1) Grundformen aus den Regeltabellen ------------------------------------

_ZELLE = re.compile(r"\|([^|\n]+)")
_GROESSEN_DE = re.compile(
    r"(Winzig)\s*,\s*(Klein)\s*,\s*(Mittelgroß)\s*,\s*(Groß)\s*,\s*(Riesig)\s+oder\s+(Gigantisch)")
_GROESSEN_EN = re.compile(
    r"(Tiny)\s*,\s*(Small)\s*,\s*(Medium)\s*,\s*(Large)\s*,\s*(Huge)\s*,?\s+or\s+(Gargantuan)",
    re.IGNORECASE)


def _fl_normal(wort: str) -> str:
    """Toleriert den fl-/fi-Ligaturverlust der srd-de-PDF: die Typen-Tabelle druckt real
    'Pfanze' statt 'Pflanze'. Fuer den VERGLEICH wird das l/i nach f entfernt - so passt der
    (korrekte) Statblock-Begriff trotzdem auf die (defekte) Tabellenzelle."""
    return re.sub(r"f[li]", "f", wort.lower())


def _fertigkeits_lemmata(con: sqlite3.Connection) -> set[str]:
    """Erste Spalte der srd-de-Fertigkeiten-Tabelle (Spalten: Fertigkeit|Attribut|Beispiel)."""
    raus: set[str] = set()
    for (body,) in con.execute(
            "SELECT e.body_md FROM eintraege e JOIN quellen q ON q.id = e.quelle_id "
            "WHERE q.kuerzel = 'srd-de' AND e.body_md LIKE '%Beispielanwendungen%'"):
        for zeile in (body or "").splitlines():
            zellen = [z.strip().replace("*", "") for z in _ZELLE.findall(zeile)]
            if len(zellen) >= 2 and zellen[0] and not zellen[0].startswith("-"):
                if zellen[0] not in ("Fertigkeit", "Attribut"):
                    raus.add(zellen[0])
    return raus


def _typ_lemmata(con: sqlite3.Connection) -> set[str]:
    """Kreaturentyp-Tabelle des Regelglossars (3-spaltig, ALLE Zellen sind Typen)."""
    raus: set[str] = set()
    for (body,) in con.execute(
            "SELECT e.body_md FROM eintraege e JOIN quellen q ON q.id = e.quelle_id "
            "WHERE q.kuerzel = 'srd-de' AND e.body_md LIKE '%folgende Kreaturentypen im Spiel%'"):
        for zeile in (body or "").splitlines():
            if not zeile.lstrip().startswith("|") or "---" in zeile:
                continue
            for zelle in _ZELLE.findall(zeile):
                wert = zelle.strip().replace("*", "")
                if wert and wert.isalpha():
                    raus.add(wert)
    return raus


def _groessen_lemmata(con: sqlite3.Connection) -> tuple[list[str], list[str]]:
    """Die Groessen stehen in BEIDEN Sprachen als GEORDNETE Aufzaehlung (winzig -> gigantisch).
    Diese Reihenfolge ist semantisch (Groesse!), nicht alphabetisch -> die Position ist hier
    ein gueltiger Anker. Die Statbloecke bestaetigen sie zusaetzlich."""
    de: list[str] = []
    en: list[str] = []
    for body, sprache in con.execute(
            "SELECT body_md, sprache FROM eintraege "
            "WHERE body_md LIKE '%Gigantisch%' OR body_md LIKE '%Gargantuan%'"):
        if not de and sprache == "de":
            m = _GROESSEN_DE.search(body or "")
            if m:
                de = list(m.groups())
        if not en and sprache == "en":
            m = _GROESSEN_EN.search(body or "")
            if m:
                en = [g.capitalize() for g in m.groups()]
    return en, de


# --- 2) Zuordnung aus den Statbloecken ----------------------------------------

_BONUS = re.compile(r"\s*\*{0,2}([^+\-*|\\]{3,30}?)\*{0,2}\s*\\?([+-]\s*\d+)")


def _segment(zeile: str, label: str) -> str | None:
    """Der Wert HINTER einem Statblock-Label, bis zum naechsten Label. Die Formate:
      srd-de  : '**Fertigkeiten** Geschichte +12, Wahrnehmung +10 **Sinne** Dunkelsicht 36 m …'
      open5e  : '**Saves:** … · **Skills:** History +12, Perception +10 · **Senses:** …'
      ddb-br  : '**Skills** History \\+12, Perception \\+10'
    Ohne den Schnitt am naechsten '**'/'·' liefe der Parser in die Nachbarfelder (Sinne,
    Sprachen) und erfand dort Fertigkeiten."""
    m = re.search(r"\*{0,2}" + label + r"\s*:?\*{0,2}\s*", zeile, re.IGNORECASE)
    if not m:
        return None
    rest = zeile[m.end():]
    schnitte = [i for i in (rest.find("**"), rest.find("·")) if i >= 0]
    return rest[:min(schnitte)] if schnitte else rest


def _skills_mit_bonus(zeile: str | None) -> dict[str, int]:
    """'Perception +4, Stealth \\+6' -> {'Perception': 4, 'Stealth': 6}
    (der Backslash ist ein Markdown-Escape aus der PDF-Konvertierung)."""
    if not zeile:
        return {}
    raus: dict[str, int] = {}
    for teil in re.split(r"[,;]", zeile):
        m = _BONUS.match(teil)
        if m:
            name = " ".join(m.group(1).replace("\\", " ").split())
            if name:
                raus[name] = int(m.group(2).replace(" ", ""))
    return raus


def _fertigkeiten_des_monsters(body: str, label: str) -> dict[str, int]:
    for zeile in (body or "").splitlines():
        if re.search(label, zeile, re.IGNORECASE):
            seg = _segment(zeile, label)
            if seg:
                treffer = _skills_mit_bonus(seg)
                if treffer:
                    return treffer
    return {}


def _groesse_und_typ(body: str) -> tuple[str | None, str | None]:
    """'Mittelgroße Monstrosität, neutral böse' -> ('Mittelgroße', 'Monstrosität');
    open5e: '**Type:** Large Aberration · …' -> ('Large', 'Aberration').
    Mehrgroessige Kreaturen ('Medium or Small' <-> 'Kleiner oder mittelgroßer') liefern KEINE
    Groesse - dort kippt die Reihenfolge zwischen den Sprachen (der Typ bleibt gueltig)."""
    for zeile in (body or "").splitlines()[:12]:
        z = zeile.strip()
        if not z or z.startswith(("*Kontext", "#", ">")):
            continue
        seg = _segment(z, "Type") or _segment(z, "Typ")
        kern = seg if seg is not None else z.replace("*", " ").replace("_", " ")
        kern = re.split(r"[,(·]", kern)[0].strip()
        woerter = re.findall(r"[A-Za-zÄÖÜäöüß]{3,}", kern)
        if len(woerter) < 2:
            continue                       # z. B. '**AC:** 17 …' -> keine Kopfzeile
        mehrgroessig = bool(re.search(r"\b(?:or|oder)\b", kern, re.IGNORECASE))
        return (None if mehrgroessig else woerter[0]), woerter[-1]
    return None, None


def _lemma_fuer(token: str, lemmata: set[str]) -> str | None:
    """Bindet ein flektiertes Statblock-Token an seine Grundform aus der Regeltabelle:
    'Mittelgroße' -> 'Mittelgroß', 'Pflanze' -> 'Pfanze' (Ligaturdefekt der Tabelle).
    Laengste passende Grundform gewinnt."""
    t = _fl_normal(token)
    treffer = [l for l in lemmata if t.startswith(_fl_normal(l)) or _fl_normal(l).startswith(t)]
    return max(treffer, key=len) if treffer else None


def _stimmen(con: sqlite3.Connection, fert: set[str], groessen_de: set[str],
             typen_de: set[str]) -> dict[str, Counter]:
    from importer.import_glossar import _finde_monster_paare

    koerper: dict[str, str] = {}
    for r in con.execute("SELECT name_de, name_en, sprache, body_md FROM eintraege "
                         "WHERE kategorie = 'monster'"):
        name = r["name_de"] if r["sprache"] == "de" else r["name_en"]
        if name and name not in koerper:
            koerper[name] = r["body_md"] or ""

    stimmen: dict[str, Counter] = defaultdict(Counter)
    for term_en, term_de, _key in _finde_monster_paare(con):
        en_body, de_body = koerper.get(term_en, ""), koerper.get(term_de, "")
        if not en_body or not de_body:
            continue

        en_s = _fertigkeiten_des_monsters(en_body, "Skills")
        de_s = _fertigkeiten_des_monsters(de_body, "Fertigkeiten")
        en_z, de_z = Counter(en_s.values()), Counter(de_s.values())
        for e_name, bonus in en_s.items():
            if en_z[bonus] != 1 or de_z.get(bonus, 0) != 1:
                continue                      # Bonus nicht eindeutig -> nicht raten
            d_name = next(n for n, b in de_s.items() if b == bonus)
            if d_name in fert:                # nur Grundformen der Regeltabelle
                stimmen[f"fertigkeit|{e_name}"][d_name] += 1

        e_gr, e_typ = _groesse_und_typ(en_body)
        d_gr, d_typ = _groesse_und_typ(de_body)
        if e_gr and d_gr and (lemma := _lemma_fuer(d_gr, groessen_de)):
            stimmen[f"groesse|{e_gr}"][lemma] += 1
        if e_typ and d_typ and (lemma := _lemma_fuer(d_typ, typen_de)):
            stimmen[f"kreaturentyp|{e_typ}"][lemma] += 1
    return stimmen


# --- 3) Ausschlussverfahren fuer Fertigkeiten ohne eindeutigen Statblock-Beleg -----
#
# Fuenf Fertigkeiten kommen in den Statbloecken nie mit EINDEUTIGEM Bonus vor (Animal Handling,
# Intimidation, Investigation, Performance, Sleight of Hand). Sie lassen sich trotzdem ERZWINGEN,
# ohne zu raten: ueber Mengen, die es in BEIDEN Sprachen gibt. Bleibt in einer Menge auf jeder
# Seite genau EINE unbekannte Fertigkeit uebrig, ist die Zuordnung zwingend.
# Zwei Mengen-Quellen:
#   (a) ATTRIBUTSGRUPPEN - deutsch aus der Fertigkeiten-Tabelle (Spalte "Attribut"), englisch aus
#       den Regeltexten selbst ("make a Dexterity (Stealth) check" -> Stealth = Dexterity).
#   (b) KLASSEN-FERTIGKEITSLISTEN - engl. "Skill Proficiencies | Choose 2: …" gegen die deutsche
#       Liste. Gepaart werden die Listen NICHT ueber den Klassennamen, sondern ueber ihre bereits
#       BEKANNTEN Mitglieder (Signatur) - das braucht keine Klassen-Bruecke und kann nicht
#       versehentlich zwei verschiedene Klassen verheiraten.

_ATTR_MUSTER = re.compile(
    r"\b(Strength|Dexterity|Constitution|Intelligence|Wisdom|Charisma)\s*\(([A-Za-z ]{3,20}?)\)",
    re.IGNORECASE)
_SKILL_LISTE_EN = re.compile(r"Skill Proficiencies\s*\|\s*(?:\**Choose \d+:?\**)?\s*([^|\n]+)",
                             re.IGNORECASE)
_SKILL_LISTE_DE = re.compile(
    r"Fertigkeiten[^|\n]{0,40}\|\s*(?:\**Wähle \d+:?\**)?\s*([^|\n]+)", re.IGNORECASE)


def _norm_skill(s: str) -> str:
    return " ".join(s.split()).casefold()


def _en_attribut_roh(con: sqlite3.Connection) -> dict[str, tuple[str, str, int]]:
    """casefold-Name -> (Anzeigeform, Attribut, Gesamttreffer), gelernt aus 'Dexterity (Stealth)
    check' im engl. Regeltext ueber ALLE '(…)'-Vorkommen (noch ungefiltert)."""
    zaehler: dict[str, Counter] = defaultdict(Counter)
    anzeige: dict[str, str] = {}
    for (body,) in con.execute("SELECT body_md FROM eintraege WHERE sprache = 'en'"):
        for attribut, skill in _ATTR_MUSTER.findall(body or ""):
            k = _norm_skill(skill)
            zaehler[k][attribut.title()] += 1
            anzeige.setdefault(k, " ".join(skill.split()))
    return {k: (anzeige[k], c.most_common(1)[0][0], sum(c.values()))
            for k, c in zaehler.items() if c}


def _ist_skillname(anzeige: str) -> bool:
    """Formfilter fuer die Fallback-Aufnahme: jedes Wort gross geschrieben, kein 'or'/'oder'
    (Kombis wie 'Arcana or Religion'), keine reinen Kleinschreib-Rauschtoken ('hill', 'fire')."""
    if re.search(r"\b(?:or|oder)\b", anzeige, re.IGNORECASE):
        return False
    woerter = anzeige.split()
    return bool(woerter) and all(w[0].isupper() for w in woerter if w.isalpha())


def _en_fertigkeiten(con: sqlite3.Connection) -> dict[str, str]:
    """Die englischen Fertigkeiten mit ihrem Attribut. Ein Name gilt, wenn er als
    'Attribut (Name)'-Probe vorkommt UND entweder (a) in einer Klassen-Fertigkeitsliste steht
    ODER (b) eine echte Skill-Form hat und >= 5x als Probe vorkommt. (a) deckt 17 der 18; (b)
    holt allein 'Performance' dazu (2024-Barde waehlt 'beliebige' Fertigkeiten -> steht in keiner
    festen Liste). Rausch ('Fire', 'Very Rare', 'Arcana or Religion') scheitert an beiden Wegen.
    Rueckgabe: {Anzeigeform: Attribut}."""
    in_listen = {_norm_skill(n) for liste in _rohe_listennamen(con, _SKILL_LISTE_EN, "en")
                 for n in liste}
    raus: dict[str, str] = {}
    for k, (anz, ab, treffer) in _en_attribut_roh(con).items():
        if k in in_listen or (treffer >= 5 and _ist_skillname(anz)):
            raus[anz] = ab
    return raus


def _de_attribut(con: sqlite3.Connection) -> dict[str, str]:
    """DE-Fertigkeit -> Attribut, aus Spalte 2 der srd-de-Fertigkeiten-Tabelle."""
    raus: dict[str, str] = {}
    for (body,) in con.execute(
            "SELECT e.body_md FROM eintraege e JOIN quellen q ON q.id = e.quelle_id "
            "WHERE q.kuerzel = 'srd-de' AND e.body_md LIKE '%Beispielanwendungen%'"):
        for zeile in (body or "").splitlines():
            zellen = [z.strip().replace("*", "") for z in _ZELLE.findall(zeile)]
            if len(zellen) >= 2 and zellen[0] and zellen[1] and "---" not in zeile:
                if zellen[0] != "Fertigkeit":
                    raus[zellen[0]] = zellen[1]
    return raus


def _rohe_listennamen(con: sqlite3.Connection, muster: re.Pattern, sprache: str) -> list[list[str]]:
    """Rohe Namenslisten aus den Klassen-Fertigkeitszeilen (ungefiltert)."""
    raus: list[list[str]] = []
    for (body,) in con.execute("SELECT body_md FROM eintraege WHERE sprache = ?", (sprache,)):
        for treffer in muster.findall(body or ""):
            if re.search(r"\b(any|beliebig|alle)\b", treffer, re.IGNORECASE):
                continue                       # "any skill" ist keine belegte Aufzaehlung
            namen = [" ".join(t.replace("*", "").split())
                     for t in re.split(r"[,;]|\bund\b|\band\b|\bor\b|\boder\b", treffer)]
            raus.append([n for n in namen if 3 <= len(n) <= 22 and n[0:1].isupper()])
    return raus


def _listen(con: sqlite3.Connection, muster: re.Pattern, sprache: str,
            gueltig: set[str]) -> list[frozenset[str]]:
    """Fertigkeits-Auswahllisten der Klassen (als Mengen, auf `gueltig` beschraenkt).
    Vergleich casefold-unempfindlich; Rueckgabe traegt die `gueltig`-Anzeigeform."""
    kanon = {_norm_skill(g): g for g in gueltig}
    raus: list[frozenset[str]] = []
    for liste in _rohe_listennamen(con, muster, sprache):
        menge = {kanon[_norm_skill(n)] for n in liste if _norm_skill(n) in kanon}
        if len(menge) >= 3:
            raus.append(frozenset(menge))
    return raus


def _erzwinge_durch_ausschluss(con: sqlite3.Connection, bekannt: dict[str, str],
                               fert_de: set[str], fert_en: set[str]) -> list[tuple[str, str, str]]:
    """Liefert (term_en, term_de, begruendung) fuer alles, was durch Ausschluss ZWINGEND folgt."""
    neu: list[tuple[str, str, str]] = []

    # (a) Attributsgruppen
    en_attr = _en_fertigkeiten(con)            # {Anzeige: Attribut}, kreuzvalidiert
    de_attr = _de_attribut(con)
    fert_en = set(en_attr)
    attr_bruecke: dict[str, str] = {}
    from app import glossar as _g
    de_attribute = set(de_attr.values())          # die dt. Attributsnamen aus der Tabelle
    for a_en in ("Strength", "Dexterity", "Constitution", "Intelligence", "Wisdom", "Charisma"):
        a_de, _off = _g.term_de(con, a_en)
        # a_de == a_en ist KEIN Ausschluss: "Charisma" ist in beiden Sprachen gleich. Die Bindung
        # gilt, sobald a_de ein echter Attributsname aus der dt. Fertigkeiten-Tabelle ist.
        if a_de in de_attribute:
            attr_bruecke[a_en] = a_de

    gruppen: list[tuple[frozenset[str], frozenset[str], str]] = []
    for a_en, a_de in attr_bruecke.items():
        g_en = frozenset(s for s in fert_en if en_attr.get(s) == a_en)
        g_de = frozenset(s for s in fert_de if de_attr.get(s) == a_de)
        if g_en and g_de:
            gruppen.append((g_en, g_de, f"Attributsgruppe {a_en}/{a_de}"))

    # (b) "Kommt in einer Klassen-Fertigkeitsliste vor" ist selbst eine belegte Menge. Genau EINE
    # Fertigkeit steht in KEINER festen Liste - der 2024-Barde waehlt "beliebige"/"any". Das gilt
    # in BEIDEN Sprachen identisch: englisch faellt nur 'Performance' heraus, deutsch nur
    # 'Auftreten'. Diese 17er-Menge trennt im Ausschluss die letzten Charisma-Zwillinge
    # (Intimidation/Einschuechtern vs. Performance/Auftreten), die eine Attributsgruppe allein
    # nicht aufloest.
    en_in_liste = frozenset().union(*_listen(con, _SKILL_LISTE_EN, "en", fert_en)) or frozenset()
    de_in_liste = frozenset().union(*_listen(con, _SKILL_LISTE_DE, "de", fert_de)) or frozenset()
    if en_in_liste and de_in_liste:
        gruppen.append((en_in_liste, de_in_liste, "in einer Klassenliste"))

    # Fixpunkt: jede Gruppe, in der auf BEIDEN Seiten genau eine Unbekannte bleibt, ist zwingend.
    stand = dict(bekannt)
    geaendert = True
    while geaendert:
        geaendert = False
        for g_en, g_de, warum in gruppen:
            offen_en = [s for s in g_en if s not in stand]
            offen_de = [s for s in g_de if s not in set(stand.values())]
            if len(offen_en) == 1 and len(offen_de) == 1:
                stand[offen_en[0]] = offen_de[0]
                neu.append((offen_en[0], offen_de[0], warum))
                geaendert = True
    return neu


def finde_kernbegriffe(con: sqlite3.Connection, min_belege: int = 2,
                       ) -> tuple[list[tuple[str, str, str, int]], list[str]]:
    """(paare, verworfen). paare = (term_en, term_de, kategorie, belege).
    Ein Paar gilt nur bei >= `min_belege` Statblock-Belegen UND ohne ernsthafte Zweitform."""
    fert = _fertigkeits_lemmata(con)
    typen_de = _typ_lemmata(con)
    gr_en, gr_de = _groessen_lemmata(con)

    stimmen = _stimmen(con, fert, set(gr_de), typen_de)

    paare: list[tuple[str, str, str, int]] = []
    verworfen: list[str] = []
    for schluessel, zaehler in sorted(stimmen.items()):
        kategorie, term_en = schluessel.split("|", 1)
        (bester, n), *rest = zaehler.most_common()
        if n < min_belege:
            verworfen.append(f"{term_en} [{kategorie}]: nur {n} Beleg(e)")
            continue
        if rest and rest[0][1] * 4 >= n:                  # ernsthafter Widerspruch -> nicht raten
            verworfen.append(f"{term_en} [{kategorie}]: Konflikt {dict(zaehler)}")
            continue
        paare.append((term_en, bester, kategorie, n))

    # Groessen zusaetzlich ueber die geordnete Regel-Aufzaehlung (deckt auch Groessen ohne
    # Beleg-Monster, z. B. Gargantuan). Statblock-Belege haben Vorrang und muessen passen.
    if len(gr_en) == 6 and len(gr_de) == 6:
        aus_statblock = {p[0]: p[1] for p in paare if p[2] == "groesse"}
        for e, d in zip(gr_en, gr_de):
            if e not in aus_statblock:
                paare.append((e, d, "groesse", 0))
            elif aus_statblock[e] != d:
                verworfen.append(f"{e} [groesse]: Regelliste sagt '{d}', Statbloecke "
                                 f"'{aus_statblock[e]}' -> WIDERSPRUCH, nicht eingetragen")
                paare = [p for p in paare if not (p[2] == "groesse" and p[0] == e)]

    # Fertigkeiten OHNE eindeutigen Statblock-Beleg per Ausschluss erzwingen (Attributsgruppen
    # + Klassenlisten). Grundlage sind die bereits statblock-belegten Fertigkeitspaare.
    fert_de_lemma = fert
    fert_en_lemma = {p[0] for p in paare if p[2] == "fertigkeit"}
    bekannt = {p[0]: p[1] for p in paare if p[2] == "fertigkeit"}
    for term_en, term_de, warum in _erzwinge_durch_ausschluss(
            con, bekannt, fert_de_lemma, fert_en_lemma):
        paare.append((term_en, term_de, "fertigkeit", 0))
        verworfen.append(f"+ {term_en} -> {term_de} [fertigkeit]: erzwungen ({warum})")
    return paare, verworfen
