"""Neutrales, rendererunabhaengiges Charaktermodell (Auftrag §7.3, KONZEPT §8).

Zwischenstufe zwischen DDB-Extraktion (EN) und DE-Rendering. Zwei Prinzipien:

1. Jeder UEBERSETZBARE String ist ein Paar ``UeText{en, de}``, damit fuer die
   Klammer-Konvention "Deutsch (English)" (§5) das Original erhalten bleibt.
   In Phase 1 (Extraktion) ist nur ``en`` gesetzt; ``de`` bleibt None bis zur
   Uebersetzung (Phase 3).
2. Zahlen, Modifikatoren, Wuerfelnotation, Ressourcen und Checkbox-Zustaende bleiben
   rohe Strings/Ints/Bools - sie laufen NIE durch das Sprachmodell (Auftrag §7.3, §8.3).

Feldnamen sind bewusst deutsch (Repo-Konvention, Deutsch-first). Die englischen
"canonical keys" aus KONZEPT §7.1 (identity.name, abilities.str.score ...) beschreiben
die Mapping-STRUKTUR, nicht die Bezeichner-Sprache; die DDB-Feldkarte bildet exakt auf
die hier definierten deutschen Pfade ab.

`roh_felder` traegt JEDES befuellte DDB-Widget verbatim (Seite/Name/Wert). Es ist das
Verlustfreiheits-Protokoll: der Golden-Test prueft, dass jeder Quellwert dort steht -
unabhaengig davon, wie gut die semantische Zuordnung schon ist.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field


# --- Bausteine ---------------------------------------------------------------

@dataclass
class UeText:
    """Uebersetzbarer Text: englisches Original + (spaeter) deutsche Fassung.

    `art` steuert die spaetere Behandlung (Phase 3), wird aber schon in Phase 1
    gesetzt, damit die Absicht dokumentiert ist:
      - "text"  freier Fliesstext            -> sinngenau uebersetzen (§8.3)
      - "term"  fester D&D-Spielbegriff      -> Foliant-Terminologie (§8.1), Klammerform
      - "name"  Eigen-/Charaktername         -> NICHT uebersetzen, keine Klammer
    """
    en: str
    de: str | None = None
    art: str = "text"


@dataclass
class RohFeld:
    """Ein befuelltes DDB-Widget, verbatim erfasst (Verlustfreiheits-Protokoll)."""
    seite: int
    name: str
    wert: str


# --- Identitaet & Werte ------------------------------------------------------

@dataclass
class Attribut:
    """Ein Attribut: Wert, Modifikator (roh, mit Vorzeichen), Rettungswurf, Uebung."""
    wert: int | None = None
    mod: str | None = None
    rettungswurf: str | None = None
    rettung_geuebt: bool = False


@dataclass
class Identitaet:
    name: str | None = None                       # Charaktername (Eigenname, keine Klammer)
    klasse: UeText | None = None                  # aus "CLASS  LEVEL" abgespalten (term)
    stufe: int | None = None                      # aus "CLASS  LEVEL" abgespalten (Zahl)
    klasse_stufe_roh: str | None = None           # Originalwert "Monk 5" (Beleg, nichts raten)
    unterklasse: UeText | None = None             # nur aus eindeutigem Inhalt; sonst None
    spezies: UeText | None = None                 # "RACE" (term)
    hintergrund: UeText | None = None             # "BACKGROUND" (term)
    ep: str | None = None                         # "EXPERIENCE POINTS" (roh, z.B. "(Milestone)")
    gesinnung: UeText | None = None
    groesse: UeText | None = None                 # "SIZE" (term)
    spielername: str | None = None                # "PLAYER NAME" - im MVP ohne Zielfeld (§7.4)


@dataclass
class Fertigkeit:
    schluessel: str                               # kanonischer Schluessel, z.B. "acrobatics"
    name: UeText                                  # Anzeige-/Uebersetzungsname (term)
    mod: str | None = None                        # Bonus (roh, z.B. "+7")
    attribut: str | None = None                   # zugrundeliegendes Attribut, z.B. "DEX"
    geuebt: bool = False


@dataclass
class Kampf:
    rk: int | None = None                         # AC
    tp_max: int | None = None                     # MaxHP
    tp_aktuell: int | None = None                 # CurrentHP (im Sample leer)
    tp_temp: str | None = None                    # TempHP (roh, z.B. "--")
    trefferwuerfel: str | None = None             # "Total", z.B. "5d8"
    initiative: str | None = None                 # "Init", z.B. "+4"
    bewegungsrate: UeText | None = None           # "Speed", z.B. "40 ft. (Walking)" (Einheiten -> Renderer)
    sinne: UeText | None = None                   # "AdditionalSenses", z.B. "Darkvision 60 ft."
    passiv_wahrnehmung: str | None = None         # "Passive1"
    passiv_einsicht: str | None = None            # "Passive2"
    passiv_untersuchung: str | None = None        # "Passive3"
    todesrettung_erfolge: int | None = None
    todesrettung_misserfolge: int | None = None
    uebungsbonus: str | None = None               # "ProfBonus", z.B. "+3"
    inspiration: bool = False                      # Heldische Inspiration


@dataclass
class Uebungen:
    """Vertrautheit/Uebung mit Ruestung, Waffen, Werkzeugen, Sprachen (aus ProficienciesLang)."""
    ruestung: list[UeText] = field(default_factory=list)
    waffen: list[UeText] = field(default_factory=list)
    werkzeuge: list[UeText] = field(default_factory=list)
    sprachen: list[UeText] = field(default_factory=list)


@dataclass
class Waffe:
    """Waffe / Schadenszaubertrick (Wpn Name{n} / Wpn{n} AtkBonus / Wpn{n} Damage)."""
    name: UeText | None = None
    angriffsbonus: str | None = None
    schaden: UeText | None = None                 # z.B. "1d8+4 Bludgeoning" (Wuerfel roh, Art -> term)
    notiz: UeText | None = None


@dataclass
class Aktion:
    """Ein Eintrag aus Actions1/2, best-effort nach Abschnitt zerlegt."""
    abschnitt: str | None = None                  # z.B. "ACTIONS", "BONUS ACTIONS"
    name: UeText | None = None
    beschreibung: UeText | None = None


@dataclass
class Merkmal:
    """Klassen-/Spezies-/Talentmerkmal aus FeaturesTraits1..6 (verbunden, dann geparst)."""
    name: UeText | None = None
    quelle: str | None = None                     # z.B. "PHB-2024", "RtHW" (roh)
    seite: str | None = None                      # z.B. "101" (roh)
    beschreibung: UeText | None = None            # freier Text (uebersetzen)
    aktionsoekonomie: list[UeText] = field(default_factory=list)  # "| ..."-Zeilen (uebersetzbar)
    herkunft: str | None = None                   # "klasse" | "spezies" | "talent"


@dataclass
class Zauber:
    grad: int | None = None                       # aus spellHeader (0 = Zaubertrick)
    name: UeText | None = None                    # spellName (term -> foliant_hol_zauber)
    quelle: UeText | None = None                  # spellSource, z.B. "Living Shadow"
    vorbereitet: bool = False                     # spellPrepared == "O"
    rettung_treffer: str | None = None            # spellSaveHit, z.B. "--" (roh)
    zeitaufwand: str | None = None                # spellCastingTime, z.B. "1A" (code_map spaeter)
    reichweite: UeText | None = None              # spellRange (Einheiten -> Renderer)
    komponenten: str | None = None                # spellComponents, z.B. "V,S" (roh)
    wirkungsdauer: UeText | None = None           # spellDuration
    seite: str | None = None                      # spellPage (roh)
    notiz: UeText | None = None                   # spellNotes
    kopf_roh: str | None = None                   # spellHeader-Rohwert, z.B. "=== 2nd LEVEL ==="


@dataclass
class Zauberwirken:
    attribut: UeText | None = None                # Zauberattribut (falls im Bogen belegt)
    rettungs_sg: str | None = None                # Zauber-SG
    angriffsbonus: str | None = None              # Zauberangriffsbonus
    plaetze: dict = field(default_factory=dict)   # {"1": {"gesamt":..,"verbraucht":..}, ...}
    zauber: list[Zauber] = field(default_factory=list)


@dataclass
class Gegenstand:
    name: UeText | None = None
    menge: str | None = None                      # "Eq Qty{n}" (roh)
    gewicht: str | None = None                    # "Eq Weight{n}" (roh, z.B. "5 lb.")


@dataclass
class Ausruestung:
    gegenstaende: list[Gegenstand] = field(default_factory=list)
    eingestimmt: list[UeText] = field(default_factory=list)   # eingestimmte magische Gegenstaende
    muenzen: dict = field(default_factory=dict)               # {"cp":..,"sp":..,"ep":..,"gp":..,"pp":..}
    getragenes_gewicht: str | None = None                     # "Weight Carried"
    belastet_ab: str | None = None                            # "Encumbered"
    schieben_ziehen_heben: str | None = None                  # "PushDragLift"


@dataclass
class Persoenlichkeit:
    wesenszuege: UeText | None = None             # PERSONALITY TRAITS
    ideale: UeText | None = None                  # IDEALS
    bindungen: UeText | None = None               # BONDS
    makel: UeText | None = None                   # FLAWS
    aussehen: UeText | None = None                # CHARACTER APPEARANCE
    hintergrundgeschichte: UeText | None = None   # CHARACTER BACKSTORY
    verbuendete: UeText | None = None             # ALLIES & ORGANIZATIONS
    notizen: UeText | None = None                 # ADDITIONAL NOTES


# --- Wurzel ------------------------------------------------------------------

@dataclass
class Charakter:
    identitaet: Identitaet = field(default_factory=Identitaet)
    attribute: dict[str, Attribut] = field(default_factory=dict)   # "str".."cha"
    fertigkeiten: list[Fertigkeit] = field(default_factory=list)
    kampf: Kampf = field(default_factory=Kampf)
    uebungen: Uebungen = field(default_factory=Uebungen)
    angriffe: list[Waffe] = field(default_factory=list)
    aktionen: list[Aktion] = field(default_factory=list)
    merkmale: list[Merkmal] = field(default_factory=list)
    zauberwirken: Zauberwirken = field(default_factory=Zauberwirken)
    ausruestung: Ausruestung = field(default_factory=Ausruestung)
    persoenlichkeit: Persoenlichkeit = field(default_factory=Persoenlichkeit)

    # Verlustfreiheit + Diagnose
    roh_felder: list[RohFeld] = field(default_factory=list)   # ALLE befuellten Widgets verbatim
    raw: dict = field(default_factory=dict)                   # unbekannte/unerwartete Felder
    warnungen: list[str] = field(default_factory=list)        # z.B. Feldkollisionen, Ungereimtheiten
    quell_fingerprint: str | None = None                     # Feldkarten-Version der Exportfamilie

    def als_dict(self) -> dict:
        """Vollstaendige, JSON-serialisierbare Repraesentation (nested)."""
        return dataclasses.asdict(self)
