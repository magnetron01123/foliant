"""DDB-PDF-Extractor (deterministisch) -> neutrales Charaktermodell.

D&D-Beyond-Exporte (PDFsharp) tragen ihre Werte in verwaisten /Widget-Annotationen
OHNE Catalog-/AcroForm (KONZEPT §4.1). `page.widgets()` von PyMuPDF liest sie dennoch
(am Golden-Sample verifiziert: 874 Widgets, 169 befuellt). Fallback auf /Contents, falls
ein Wert nicht in /V liegt.

Verlustfrei (Auftrag §13.1 Nr. 6/7): jedes befuellte Widget landet verbatim in
`charakter.roh_felder`; die semantische Zuordnung ist zusaetzlich. `FeaturesTraits1..6`
und `Actions1..2` werden VOR dem Parsen verlustfrei verbunden (§7.5) - D&D Beyond bricht
den Text an Wortgrenzen um und verschluckt dabei das Trennzeichen, deshalb Smart-Join
(ein Leerzeichen nur, wenn zwei Nicht-Whitespace-Zeichen aneinanderstossen).

Kein Netzwerk, kein OCR, kein Koordinaten-Raten. Nur PyMuPDF (bereits im Bestand,
transitiv ueber pymupdf4llm) - Renderer-Abhaengigkeiten (reportlab/pypdf) kommen erst
in Phase 2.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import fitz  # PyMuPDF

from app.charakterbogen.modelle import (
    Aktion,
    Ausruestung,
    Charakter,
    Fertigkeit,
    Gegenstand,
    Merkmal,
    RohFeld,
    UeText,
    Waffe,
    Zauber,
)

_FELDKARTE_PFAD = Path(__file__).parent / "feldkarten" / "ddb_pdfsharp_6_1.json"


class DDBFormatFehler(ValueError):
    """Das PDF gehoert nicht zur unterstuetzten DDB-Exportfamilie (§7.2). Nicht raten."""


def lade_feldkarte(pfad: Path | None = None) -> dict:
    with open(pfad or _FELDKARTE_PFAD, encoding="utf-8") as f:
        return json.load(f)


# --- Widgets lesen -----------------------------------------------------------

def _oeffne(quelle: str | bytes | Path) -> fitz.Document:
    if isinstance(quelle, (bytes, bytearray)):
        return fitz.open(stream=bytes(quelle), filetype="pdf")
    return fitz.open(str(quelle))


def lese_widgets(doc: fitz.Document) -> tuple[list[RohFeld], list[str]]:
    """Gibt (befuellte Roh-Felder, ALLE Widget-Namen) zurueck.

    Roh-Felder = befuellte, benannte Text-Widgets (verbatim). Alle Namen (auch leere)
    dienen dem Fingerprint (§7.2 Nr. 5), der character-UNABHAENGIG sein muss - deshalb
    nur Namen, nie Werte hashen.
    """
    roh: list[RohFeld] = []
    alle_namen: list[str] = []
    for pno, page in enumerate(doc):
        for w in page.widgets() or []:
            name = w.field_name
            if name:
                alle_namen.append(name)
            wert = w.field_value
            if wert in (None, ""):
                # Fallback /Contents (KONZEPT §4.1: Wert in /V ODER /Contents)
                try:
                    typ, val = doc.xref_get_key(w.xref, "Contents")
                    if typ == "string":
                        wert = val
                except Exception:
                    pass
            if wert in (None, ""):
                continue
            # "Off" bedeutet NUR bei Ankreuz-Widgets "nicht gesetzt". Bei einem Text-Feld
            # ist "Off" ein echter Wert und darf NICHT verworfen werden (sonst Verlust).
            if wert == "Off" and _ist_ankreuzwidget(w):
                continue
            if name:
                roh.append(RohFeld(seite=pno, name=name, wert=wert))
    return roh, alle_namen


def _ist_ankreuzwidget(w) -> bool:
    """Checkbox/Radiobutton/Button - bei diesen ist 'Off' der Leer-/Aus-Zustand."""
    return (w.field_type_string or "").lower() in ("checkbox", "radiobutton", "button")


def berechne_fingerprint(alle_namen: list[str]) -> str:
    """Stabiler Fingerabdruck der Exportfamilie aus der sortierten Widget-Namensmenge.

    Rechts getrimmt (DDB-Leerzeichen-Suffixe), dedupliziert, sortiert. Werte fliessen
    NICHT ein (andere Charaktere derselben Familie haben andere Werte, §7.2)."""
    menge = sorted({n.rstrip() for n in alle_namen})
    roh = "\n".join(menge).encode("utf-8")
    return hashlib.sha256(roh).hexdigest()[:16]


def pruefe_exportfamilie(doc: fitz.Document, roh: list[RohFeld], feldkarte: dict) -> None:
    """Wirft DDBFormatFehler, wenn Seitenzahl/Pflichtfelder nicht passen (§7.2). Nie raten."""
    fp = feldkarte["fingerprint"]
    if doc.page_count != fp["seiten"]:
        raise DDBFormatFehler(
            f"Erwartet {fp['seiten']} Seiten, gefunden {doc.page_count}."
        )
    vorhanden = {r.name.rstrip() for r in roh}
    fehlend = [p for p in fp["pflichtfelder"] if p not in vorhanden]
    if fehlend:
        raise DDBFormatFehler(f"Pflichtfelder fehlen: {fehlend}")


# --- Hilfen ------------------------------------------------------------------

def _index_roh(roh: list[RohFeld]) -> dict[str, str]:
    """Nachschlage-Index: rechts getrimmter Feldname -> Wert (erste Belegung gewinnt).

    Rechts-Trimmen faengt DDB-Suffixe ('DEXmod ', 'Wpn3 AtkBonus  ') ab; interne
    Doppelspaces ('CLASS  LEVEL') bleiben erhalten. Kollisionen werden vermerkt,
    aber roh_felder bleibt die verlustfreie Wahrheit."""
    idx: dict[str, str] = {}
    for r in roh:
        k = r.name.rstrip()
        if k not in idx:
            idx[k] = r.wert
    return idx


def _setze_pfad(wurzel, pfad: str, wert) -> None:
    """Setzt einen Punkt-Pfad im Modell (Objekt-Attribute + verschachtelte dicts)."""
    segmente = pfad.split(".")
    ziel = wurzel
    for seg in segmente[:-1]:
        ziel = ziel[seg] if isinstance(ziel, dict) else getattr(ziel, seg)
    letzt = segmente[-1]
    if isinstance(ziel, dict):
        ziel[letzt] = wert
    else:
        setattr(ziel, letzt, wert)


def _wandle(art: str, wert: str, warnungen: list[str], feld: str):
    """Rohwert -> Modellwert je nach `art` (KONZEPT §5/§8: Zahlen roh, Text als UeText)."""
    if art in ("name", "roh"):
        return wert
    if art == "zahl":
        try:
            return int(wert.strip())
        except (ValueError, AttributeError):
            warnungen.append(f"{feld}: '{wert}' ist keine Ganzzahl - roh uebernommen")
            return wert
    if art in ("text", "term"):
        return UeText(en=wert, art=art)
    return wert


def _ist_kopf_duplikat(name: str, praefixe: list[str]) -> bool:
    """CharacterName2/3/4, 'CLASS  LEVEL2' ... = pro Seite wiederholte Kopfzeile."""
    for p in praefixe:
        if name.startswith(p):
            rest = name[len(p):]
            if rest and rest.isdigit():
                return True
    return False


def _verbinde_fragmente(fragmente: list[str]) -> str:
    """Smart-Join: verbindet Box-Fragmente verlustfrei; ein Leerzeichen NUR, wenn zwei
    Nicht-Whitespace-Zeichen aneinanderstossen (D&D Beyond bricht an Wortgrenzen um und
    verschluckt das Leerzeichen). Fragmentinhalt wird nie veraendert -> jedes Fragment
    bleibt ein zusammenhaengender Teilstring (verlustfrei, §7.5)."""
    out = ""
    for f in fragmente:
        if not f:
            continue
        if out and not out[-1].isspace() and not f[0].isspace():
            out += " "
        out += f
    return out


def _teile_abschnitte(text: str) -> list[tuple[str, str]]:
    """Zerlegt '=== TITEL === koerper === TITEL2 === ...' in [(titel, koerper), ...].

    Fuehrt Vor-Text (vor dem ersten Marker) als ('', ...) mit, falls vorhanden."""
    stuecke = re.split(r"===\s*([^=]+?)\s*===", text)
    ergebnis: list[tuple[str, str]] = []
    vor = stuecke[0].strip()
    if vor:
        ergebnis.append(("", vor))
    for i in range(1, len(stuecke), 2):
        titel = stuecke[i].strip()
        koerper = stuecke[i + 1] if i + 1 < len(stuecke) else ""
        ergebnis.append((titel, koerper))
    return ergebnis


# --- Teil-Parser -------------------------------------------------------------

def _parse_identitaet(char: Charakter, idx: dict, feldkarte: dict) -> None:
    for feldname, spec in feldkarte["skalar"].items():
        if feldname not in idx:
            continue
        art = spec["art"]
        if art == "klasse_stufe":
            char.identitaet.klasse_stufe_roh = idx[feldname]
            _spalte_klasse_stufe(char, idx[feldname])
        else:
            _setze_pfad(char, spec["pfad"], _wandle(art, idx[feldname], char.warnungen, feldname))


def _spalte_klasse_stufe(char: Charakter, roh: str) -> None:
    """'Monk 5' -> Klasse (term) + Stufe (Zahl). NUR bei eindeutig einklassigem
    'Klassenname Stufe': der Name darf keine Ziffer und keinen '/'-Trenner enthalten.
    Mehrklassig ('Fighter 1 / Wizard 4') ist NICHT eindeutig zerlegbar -> Rohwert
    bleibt in klasse_stufe_roh, klasse/stufe bleiben None (nichts raten, §7.4/§16)."""
    m = re.fullmatch(r"\s*([^\d/]+?)\s+(\d+)\s*", roh)
    if m:
        char.identitaet.klasse = UeText(en=m.group(1).strip(), art="term")
        char.identitaet.stufe = int(m.group(2))
    else:
        char.warnungen.append(
            f"CLASS  LEVEL: '{roh}' nicht eindeutig einklassig zerlegbar - roh belassen, nichts geraten")


def _parse_attribute(char: Charakter, idx: dict, feldkarte: dict) -> None:
    from app.charakterbogen.modelle import Attribut
    for schluessel, felder in feldkarte["attribute"].items():
        a = Attribut()
        if felder["score"] in idx:
            try:
                a.wert = int(idx[felder["score"]].strip())
            except ValueError:
                char.warnungen.append(f"{felder['score']}: keine Zahl")
        a.mod = idx.get(felder["mod"])
        a.rettungswurf = idx.get(felder["save"])
        a.rettung_geuebt = felder["save_prof"] in idx
        char.attribute[schluessel] = a


def _parse_fertigkeiten(char: Charakter, idx: dict, feldkarte: dict) -> None:
    for f in feldkarte["fertigkeiten"]:
        if f["wert"] not in idx and f["mod"] not in idx and f["prof"] not in idx:
            continue
        char.fertigkeiten.append(Fertigkeit(
            schluessel=f["schluessel"],
            name=UeText(en=f["schluessel"].replace("_", " ").title(), art="term"),
            mod=idx.get(f["wert"]),
            attribut=idx.get(f["mod"]),
            geuebt=f["prof"] in idx,
        ))


def _parse_waffen(char: Charakter, idx: dict, feldkarte: dict) -> None:
    for w in feldkarte["waffen"]:
        if w["name"] not in idx:
            continue
        char.angriffe.append(Waffe(
            name=UeText(en=idx[w["name"]], art="term"),
            angriffsbonus=idx.get(w["angriffsbonus"]),
            schaden=UeText(en=idx[w["schaden"]], art="text") if w["schaden"] in idx else None,
        ))


def _parse_uebungen(char: Charakter, idx: dict, feldkarte: dict) -> None:
    """ProficienciesLang nach Kategorie aufteilen (§7.4). Der Kategorie-Text wird als GANZES
    gehalten und NICHT an Kommas zerlegt: D&D Beyond fuehrt zusammengesetzte Begriffe invertiert
    mit Komma ('Crossbow, Hand' = Hand Crossbow), ein Komma-Split wuerde die raten/zerreissen.
    Die Zerlegung in Einzelbegriffe + Terminologie-Aufloesung ist Sache der Uebersetzung (Phase 3,
    mit Foliant)."""
    feld = feldkarte["rich_felder"]["proficiencies"][0]
    if feld not in idx:
        return
    ziel = {"WEAPONS": char.uebungen.waffen, "TOOLS": char.uebungen.werkzeuge,
            "LANGUAGES": char.uebungen.sprachen, "ARMOR": char.uebungen.ruestung}
    for titel, koerper in _teile_abschnitte(idx[feld]):
        liste = ziel.get(titel.upper())
        if liste is None:
            continue
        text = " ".join(koerper.split()).strip()  # Zeilenumbrueche -> ein Fluss, Rand trimmen
        if text:
            # art="liste": Kategorie als Ganzes uebersetzen; §5-Anzeige "de (en)" OHNE per-Item-*,
            # weil bei zusammengesetzten Begriffen ("Crossbow, Hand"=Handarmbrust) keine 1:1-
            # Item-Zuordnung moeglich ist (ein einzelner Stern waere irrefuehrend).
            liste.append(UeText(en=text, art="liste"))


def _parse_aktionen(char: Charakter, idx: dict, feldkarte: dict) -> None:
    fragmente = [idx[f] for f in feldkarte["rich_felder"]["actions"] if f in idx]
    if not fragmente:
        return
    verbunden = _verbinde_fragmente(fragmente)
    for titel, koerper in _teile_abschnitte(verbunden):
        koerper = koerper.strip()
        if koerper:
            char.aktionen.append(Aktion(abschnitt=titel or None,
                                        beschreibung=UeText(en=koerper, art="text")))


# Ein Feature-Kopf ist '* Name • QUELLE [Seite]'. Die '•'-Quelle ist PFLICHT fuer die
# Erkennung: sie unterscheidet echte Koepfe von Beschreibungszeilen, die zufaellig mit '*'
# beginnen ('*Note: ...'). Seite optional. Ohne '•' gilt eine '*'-Zeile als Beschreibung.
_FEATURE_KOPF = re.compile(r"^\*\s*(?P<name>.+?)\s*•\s*(?P<quelle>\S+)(?:\s+(?P<seite>\d+))?\s*$")


def _parse_merkmale(char: Charakter, idx: dict, feldkarte: dict) -> None:
    """FeaturesTraits1..6 verbinden (§7.5), dann nach Abschnitten/Feature-Markern zerlegen."""
    fragmente = [idx[f] for f in feldkarte["rich_felder"]["features"] if f in idx]
    if not fragmente:
        return
    verbunden = _verbinde_fragmente(fragmente)
    for titel, koerper in _teile_abschnitte(verbunden):
        herkunft = _herkunft_aus_titel(titel)
        aktuell: Merkmal | None = None
        for zeile in koerper.splitlines():
            gestrippt = zeile.strip()
            kopf = _FEATURE_KOPF.match(gestrippt)
            if kopf:
                aktuell = Merkmal(
                    name=UeText(en=kopf.group("name").strip(), art="term"),
                    quelle=kopf.group("quelle"),
                    seite=kopf.group("seite"),
                    herkunft=herkunft,
                    beschreibung=UeText(en="", art="text"),
                )
                char.merkmale.append(aktuell)
            elif aktuell is not None and gestrippt.startswith("|"):
                aktuell.aktionsoekonomie.append(UeText(en=gestrippt.lstrip("| ").rstrip(), art="text"))
            elif aktuell is not None and gestrippt:
                aktuell.beschreibung.en = (aktuell.beschreibung.en + "\n" + zeile).strip("\n") \
                    if aktuell.beschreibung.en else zeile


def _herkunft_aus_titel(titel: str) -> str | None:
    t = titel.upper()
    if "SPECIES" in t or "TRAITS" in t:
        return "spezies"
    if "FEATURES" in t:
        return "klasse"
    if "FEAT" in t:
        return "talent"
    return None


_GRAD_HEADER = re.compile(r"(\d+)\s*(?:st|nd|rd|th)?\s*LEVEL", re.IGNORECASE)


def _parse_zauber(char: Charakter, idx: dict, feldkarte: dict) -> None:
    spec = feldkarte["indiziert"]["zauber"]
    felder = spec["felder"]
    aktueller_grad: int | None = None
    aktueller_kopf: str | None = None
    for i in range(spec["start"], spec["max"]):
        def hol(key: str) -> str | None:
            return idx.get(felder[key].replace("{i}", str(i)))
        kopf = hol("kopf")
        if kopf:
            aktueller_kopf = kopf
            aktueller_grad = _grad_aus_kopf(kopf)
        name = hol("name")
        if name is None:
            # Kein Name an dieser Stelle: keine weiteren Zauber, wenn auch kein Kopf folgt.
            if kopf is None and not any(hol(k) for k in felder):
                # Luecke - konservativ weiterlaufen bis max (DDB indiziert zwar dicht,
                # aber wir verlassen uns nicht darauf).
                continue
            continue
        char.zauberwirken.zauber.append(Zauber(
            grad=aktueller_grad,
            name=UeText(en=name, art="term"),
            quelle=UeText(en=hol("quelle"), art="text") if hol("quelle") else None,
            vorbereitet=(hol("vorbereitet") == "O"),
            rettung_treffer=hol("rettung_treffer"),
            zeitaufwand=hol("zeitaufwand"),
            reichweite=UeText(en=hol("reichweite"), art="text") if hol("reichweite") else None,
            komponenten=hol("komponenten"),
            wirkungsdauer=UeText(en=hol("wirkungsdauer"), art="text") if hol("wirkungsdauer") else None,
            seite=hol("seite"),
            notiz=UeText(en=hol("notiz"), art="text") if hol("notiz") else None,
            kopf_roh=aktueller_kopf,
        ))


def _grad_aus_kopf(kopf: str) -> int | None:
    if re.search(r"CANTRIP", kopf, re.IGNORECASE):
        return 0
    m = _GRAD_HEADER.search(kopf)
    if m:
        g = int(m.group(1))
        return g if 0 <= g <= 9 else None
    return None


def _parse_ausruestung(char: Charakter, idx: dict, feldkarte: dict) -> None:
    spec = feldkarte["indiziert"]["ausruestung"]
    for i in range(spec["start"], spec["max"]):
        name = idx.get(spec["name"].replace("{i}", str(i)))
        if name is None:
            continue
        char.ausruestung.gegenstaende.append(Gegenstand(
            name=UeText(en=name, art="term"),
            menge=idx.get(spec["menge"].replace("{i}", str(i))),
            gewicht=idx.get(spec["gewicht"].replace("{i}", str(i))),
        ))


def _parse_story(char: Charakter, idx: dict, feldkarte: dict) -> None:
    for feldname, pfad in feldkarte["story"].items():
        if feldname in idx:
            _setze_pfad(char, pfad, UeText(en=idx[feldname], art="text"))


# --- Orchestrierung ----------------------------------------------------------

# Felder, die bewusst KEIN eigenes Modell-Ziel haben, aber verbatim in roh_felder
# stehen (nicht als 'unerwartet' in raw markieren).
_BEKANNT_OHNE_ZIEL = {"spellSlotHeader"}


def extrahiere(quelle: str | bytes | Path, feldkarte: dict | None = None) -> Charakter:
    """Liest ein DDB-Export-PDF vollstaendig in das neutrale Modell (EN).

    Wirft DDBFormatFehler, wenn das PDF nicht zur unterstuetzten Familie gehoert.
    """
    feldkarte = feldkarte or lade_feldkarte()
    doc = _oeffne(quelle)
    try:
        roh, alle_namen = lese_widgets(doc)
        pruefe_exportfamilie(doc, roh, feldkarte)

        char = Charakter()
        char.roh_felder = roh
        char.quell_fingerprint = berechne_fingerprint(alle_namen)

        idx = _index_roh(roh)
        _parse_identitaet(char, idx, feldkarte)
        _parse_attribute(char, idx, feldkarte)
        _parse_fertigkeiten(char, idx, feldkarte)
        _parse_waffen(char, idx, feldkarte)
        _parse_uebungen(char, idx, feldkarte)
        _parse_aktionen(char, idx, feldkarte)
        _parse_merkmale(char, idx, feldkarte)
        _leite_unterklasse_ab(char)
        _parse_zauber(char, idx, feldkarte)
        _parse_ausruestung(char, idx, feldkarte)
        _parse_story(char, idx, feldkarte)

        _erfasse_unerwartete(char, idx, feldkarte)
        return char
    finally:
        doc.close()


def _leite_unterklasse_ab(char: Charakter) -> None:
    """Unterklasse NUR aus eindeutigem Inhalt (§7.4, nichts raten): genau ein Merkmal, dessen
    Name auf 'Subclass' endet und das genau eine Aktionsoekonomie-Zeile traegt (den
    Unterklassennamen, z.B. 'Monk Subclass' -> '| Warrior of Shadow'). Sonst None."""
    kandidaten = [m for m in char.merkmale
                  if m.name and m.name.en.strip().endswith("Subclass") and len(m.aktionsoekonomie) == 1]
    if len(kandidaten) == 1:
        char.identitaet.unterklasse = UeText(en=kandidaten[0].aktionsoekonomie[0].en, art="term")


def _erfasse_unerwartete(char: Charakter, idx: dict, feldkarte: dict) -> None:
    """Jedes belegte Feld ohne bekanntes Ziel -> raw (nie verwerfen, KONZEPT §4.1)."""
    bekannt: set[str] = set()
    bekannt |= set(feldkarte["skalar"].keys())
    for felder in feldkarte["attribute"].values():
        bekannt |= set(felder.values())
    for f in feldkarte["fertigkeiten"]:
        bekannt |= {f["wert"], f["prof"], f["mod"]}
    for gruppe in feldkarte["rich_felder"].values():
        bekannt |= set(gruppe)
    for w in feldkarte["waffen"]:
        bekannt |= {w["name"], w["angriffsbonus"], w["schaden"]}
    bekannt |= set(feldkarte["story"].keys())

    praefixe = feldkarte["kopf_duplikate_praefixe"]
    indiz_praefixe = ("spell", "Eq Name", "Eq Qty", "Eq Weight")

    for name, wert in idx.items():
        if name in bekannt:
            continue
        if _ist_kopf_duplikat(name, praefixe):
            continue
        if any(name.startswith(p) for p in indiz_praefixe):
            continue  # indizierte Zauber-/Ausruestungsfelder werden dediziert verarbeitet
        char.raw[name] = wert
