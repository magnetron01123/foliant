"""Renderer (deterministisch): neutrales Charaktermodell -> gefüllter DE-WotC-Bogen.

Zeichnet Werte per Koordinaten (layout_map) mit Auto-Fit auf eine Kopie der offiziellen
DE-Vorlage; der Vektor-Hintergrund (Logo, Rahmen, Illustrationen, rechtliche Fußzeile)
bleibt unverändert - es wird nur Text/Marken HINZUGEFÜGT (KONZEPT §9/§10). Bei echtem
Überlauf einer bereits im Quellbogen vorhandenen Sektion wandert der Resttext auf eine
Fortsetzungsseite im offiziellen Stil (KONZEPT §9) - nichts wird still abgeschnitten.

Phase 2: rendert das neutrale Modell OHNE Übersetzung (UeText -> .de falls vorhanden,
sonst .en) - der "sieht aus wie Original"-Beweis. Die deutsche Übersetzung kommt in Phase 3.

Nur PyMuPDF (fitz), keine reportlab/pypdf-Abhängigkeit.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import fitz

from app.charakterbogen.modelle import Charakter, UeText

_HIER = Path(__file__).parent
_LAYOUT_PFAD = _HIER / "feldkarten" / "de_wotc_2025.json"
_CODEMAP_PFAD = _HIER / "feldkarten" / "code_map.json"
_TEMPLATE_STD = (_HIER.parents[1] / "vorlagen" / "charakterboegen" / "offiziell"
                 / "Charakterbogen_2024_DE.pdf")

_FONT = "helv"
_MEDIA = (603, 774)
_SPEZIAL_PFAD = {"persoenlichkeit_gesinnung": "identitaet.gesinnung"}

# Typografische Sonderzeichen -> font-sichere Varianten. Helvetica-Base14 rendert z.B. das
# typografische Apostroph U+2019 (') sichtbar falsch als '·' ("Monk·s" statt "Monk's").
_ERSATZ = {"’": "'", "‘": "'", "“": '"', "”": '"', "′": "'",
           "–": "-", "—": "-", "…": "...", " ": " ", "ʼ": "'"}


def _saeubere(text: str) -> str:
    if not text:
        return text
    return "".join(_ERSATZ.get(c, c) for c in text)


def lade_layout(pfad: Path | None = None) -> dict:
    return json.loads((pfad or _LAYOUT_PFAD).read_text(encoding="utf-8"))


def lade_codemap(pfad: Path | None = None) -> dict:
    return json.loads((pfad or _CODEMAP_PFAD).read_text(encoding="utf-8"))


# --- Text-Primitive ----------------------------------------------------------

def _fit_size(text: str, breite: float, size: float, minsize: float) -> float:
    while size > minsize and fitz.get_text_length(text, _FONT, size) > breite:
        size -= 0.5
    return size


def _zeichne_einzeilig(page, rect, text, size, minsize, align, ink) -> None:
    if text is None or text == "":
        return
    text = _saeubere(text)
    r = fitz.Rect(rect)
    sz = _fit_size(text, r.width, size, minsize)
    tw = fitz.get_text_length(text, _FONT, sz)
    if align == "c":
        x = r.x0 + (r.width - tw) / 2
    elif align == "r":
        x = r.x1 - tw
    else:
        x = r.x0
    baseline = r.y0 + (r.height + sz * 0.72) / 2
    page.insert_text((x, baseline), text, fontname=_FONT, fontsize=sz, color=ink)


def _marke(page, punkt, ink) -> None:
    """Gefülltes Kästchen/Häkchen fuer Übungs-/Vorbereitet-Marker (○ -> ●)."""
    page.draw_circle(fitz.Point(punkt[0], punkt[1]), 2.3, color=ink, fill=ink, width=0)


def _umbrich(text: str, breite: float, size: float) -> list[str]:
    text = _saeubere(text)
    zeilen: list[str] = []
    for absatz in text.split("\n"):
        if not absatz:
            zeilen.append("")
            continue
        cur = ""
        for wort in absatz.split(" "):
            test = (cur + " " + wort).strip()
            if not cur or fitz.get_text_length(test, _FONT, size) <= breite:
                cur = test
            else:
                zeilen.append(cur)
                cur = wort
        zeilen.append(cur)
    return zeilen


def _para(page, rect, text, size, minsize, ink) -> str:
    """Zeichnet umbrochenen Text in rect, Auto-Fit von size bis minsize. Gibt den NICHT
    passenden Rest zurück (fuer Fortsetzungsseiten) - '' wenn alles passt."""
    if not text:
        return ""
    r = fitz.Rect(rect)
    for sz in _groessen(size, minsize):
        lh = sz * 1.28
        zeilen = _umbrich(text, r.width, sz)
        if len(zeilen) * lh <= r.height:
            _zeichne_zeilen(page, r, zeilen, sz, lh, ink)
            return ""
    # Bei Mindestgröße: so viel wie passt, Rest zurueckgeben (verlustfrei -> Fortsetzung)
    sz = minsize
    lh = sz * 1.28
    zeilen = _umbrich(text, r.width, sz)
    maxz = max(1, int(r.height / lh))
    _zeichne_zeilen(page, r, zeilen[:maxz], sz, lh, ink)
    rest = [z for z in zeilen[maxz:]]
    return "\n".join(rest).strip()


def _groessen(size, minsize):
    s = size
    while s >= minsize:
        yield s
        s -= 0.5


def _zeichne_zeilen(page, r, zeilen, sz, lh, ink) -> None:
    y = r.y0 + sz
    for z in zeilen:
        if z:
            page.insert_text((r.x0, y), z, fontname=_FONT, fontsize=sz, color=ink)
        y += lh


# --- Werte aus dem Modell ----------------------------------------------------

def _navigiere(root, pfad: str):
    cur = root
    for seg in pfad.split("."):
        if cur is None:
            return None
        cur = cur.get(seg) if isinstance(cur, dict) else getattr(cur, seg, None)
    return cur


def _text(val) -> str:
    if val is None:
        return ""
    if isinstance(val, UeText):
        return (val.de or val.en or "").strip()
    if isinstance(val, bool):
        return ""
    return str(val)


def _ue_liste(liste: list[UeText]) -> str:
    return ", ".join(_text(u) for u in liste if _text(u))


def _merkmal_text(m) -> str:
    kopf = _text(m.name)
    quelle = f" ({m.quelle} {m.seite})" if m.quelle else ""
    body = _text(m.beschreibung)
    oek = ("  [" + "; ".join(_text(x) for x in m.aktionsoekonomie) + "]") if m.aktionsoekonomie else ""
    return f"{kopf}{quelle}. {body}{oek}".strip()


_LB = re.compile(r"([\d]+(?:[.,]\d+)?)\s*lb\.?", re.IGNORECASE)


def _gewicht_kg(text: str | None) -> str | None:
    """'5 lb.' -> '2,3 kg' (deterministisch: 1 lb = 0,4536 kg). Ohne lb-Muster unverändert."""
    if not text:
        return text
    m = _LB.search(text)
    if not m:
        return text
    try:
        kg = float(m.group(1).replace(",", ".")) * 0.4536
    except ValueError:
        return text
    zahl = f"{kg:.1f}".rstrip("0").rstrip(".").replace(".", ",")
    return _LB.sub(f"{zahl} kg", text)


def _merkmale(charakter, herkunft) -> str:
    return "\n\n".join(_merkmal_text(m) for m in charakter.merkmale if m.herkunft == herkunft)


def _geschichte_text(charakter) -> str:
    p = charakter.persoenlichkeit
    teile = [("Persönlichkeitsmerkmale", p.wesenszuege), ("Ideale", p.ideale),
             ("Bindungen", p.bindungen), ("Makel", p.makel),
             ("Hintergrundgeschichte", p.hintergrundgeschichte), ("Verbündete", p.verbuendete),
             ("Notizen", p.notizen)]
    return "\n".join(f"{titel}: {_text(v)}" for titel, v in teile if _text(v))


def _ausruestung_text(charakter) -> str:
    zeilen = []
    for g in charakter.ausruestung.gegenstaende:
        menge = f"{g.menge}× " if g.menge and g.menge not in ("1", "") else ""
        gew = f" ({_gewicht_kg(g.gewicht)})" if g.gewicht else ""
        zeilen.append(f"{menge}{_text(g.name)}{gew}")
    return "\n".join(zeilen)


def _grossbox_texte(charakter) -> dict[str, str]:
    return {
        "klassenmerkmale": _merkmale(charakter, "klasse"),
        "spezies_merkmale": _merkmale(charakter, "spezies"),
        "talente": _merkmale(charakter, "talent"),
        "aussehen": _text(charakter.persoenlichkeit.aussehen),
        "geschichte": _geschichte_text(charakter),
        "sprachen": _ue_liste(charakter.uebungen.sprachen),
        "ausruestung": _ausruestung_text(charakter),
        "einstimmung": _ue_liste(charakter.ausruestung.eingestimmt),
        "waffen_uebung": _ue_liste(charakter.uebungen.waffen),
        "werkzeug_uebung": _ue_liste(charakter.uebungen.werkzeuge),
    }


_BOX_TITEL = {
    "klassenmerkmale": "Klassenmerkmale",
    "spezies_merkmale": "Spezies-Merkmale",
    "talente": "Talente",
    "geschichte": "Geschichte & Persönlichkeit",
    "ausruestung": "Ausrüstung",
    "aussehen": "Aussehen",
    "sprachen": "Sprachen",
    "einstimmung": "Einstimmung",
    "waffen_uebung": "Waffen-Vertrautheit",
    "werkzeug_uebung": "Werkzeug-Vertrautheit",
}


# --- Tabellen ----------------------------------------------------------------

def _waffen_tabelle(page, spec, angriffe, ink) -> None:
    y0 = spec["kopf_y"]
    lh = spec["zeilenhoehe"]
    sp = spec["spalten"]
    rows = angriffe[: spec["zeilen"]]
    if not rows:
        return

    def spalten_size(texte, breite):
        # kleinste Grösse, die ALLE Zeilen der Spalte fasst -> einheitlich, kein Zellen-Wackeln
        s = spec["size"]
        for t in texte:
            if t:
                s = min(s, _fit_size(_saeubere(t), breite, spec["size"], spec["min"]))
        return s

    sn = spalten_size([_text(w.name) for w in rows], sp["name"][1] - sp["name"][0])
    ss = spalten_size([_text(w.schaden) for w in rows], sp["schaden"][1] - sp["schaden"][0])
    for i, w in enumerate(rows):
        y = y0 + i * lh
        # size==min erzwingt die einheitliche Spaltengrösse (kein Per-Zelle-Autofit)
        _zeichne_einzeilig(page, [sp["name"][0], y - 10, sp["name"][1], y + 2], _text(w.name), sn, sn, "l", ink)
        _zeichne_einzeilig(page, [sp["atk"][0], y - 10, sp["atk"][1], y + 2], _text(w.angriffsbonus), spec["size"], spec["size"], "c", ink)
        _zeichne_einzeilig(page, [sp["schaden"][0], y - 10, sp["schaden"][1], y + 2], _text(w.schaden), ss, ss, "l", ink)
        _zeichne_einzeilig(page, [sp["notizen"][0], y - 10, sp["notizen"][1], y + 2], _text(w.notiz), spec["size"], spec["min"], "l", ink)


def _zauber_tabelle(page, spec, zauber, codemap, ink) -> list:
    y0 = spec["kopf_y"]
    lh = spec["zeilenhoehe"]
    sp = spec["spalten"]
    krm = spec["krm"]
    zt = codemap["zeitaufwand"]
    passt = zauber[: spec["zeilen"]]
    for i, z in enumerate(passt):
        y = y0 + i * lh
        grad = "0" if z.grad == 0 else (str(z.grad) if z.grad is not None else "")
        _zeichne_einzeilig(page, [sp["grad"][0], y - 10, sp["grad"][1], y + 2], grad, spec["size"], spec["min"], sp["grad"][2], ink)
        _zeichne_einzeilig(page, [sp["name"][0], y - 10, sp["name"][1], y + 2], _text(z.name), spec["size"], spec["min"], sp["name"][2], ink)
        zeit = zt.get(z.zeitaufwand or "", z.zeitaufwand or "")
        _zeichne_einzeilig(page, [sp["zeit"][0], y - 10, sp["zeit"][1], y + 2], zeit, spec["size"], spec["min"], sp["zeit"][2], ink)
        _zeichne_einzeilig(page, [sp["reichweite"][0], y - 10, sp["reichweite"][1], y + 2], _text(z.reichweite), spec["size"], spec["min"], sp["reichweite"][2], ink)
        _zeichne_einzeilig(page, [sp["notizen"][0], y - 10, sp["notizen"][1], y + 2], _text(z.notiz), spec["size"], spec["min"], sp["notizen"][2], ink)
        # K/R/M-Marken aus Wirkungsdauer/Komponenten (deterministisch, nichts raten)
        dauer = _text(z.wirkungsdauer).lower()
        komp = (z.komponenten or "").upper()
        if "konzentration" in dauer or "concentration" in dauer:
            _marke(page, (krm["k"], y - 3), ink)
        if "M" in komp:
            _marke(page, (krm["m"], y - 3), ink)
    return zauber[spec["zeilen"]:]


def _muenzen(page, spec, muenzen, ink) -> None:
    for code, rect in spec["felder"].items():
        wert = muenzen.get(code)
        if wert not in (None, ""):
            _zeichne_einzeilig(page, rect, str(wert), spec["size"], spec["min"], "c", ink)


# --- Grossbox mit Spalten + Fortsetzung -------------------------------------

def _grossbox(page, spec, text, ink) -> str:
    if spec.get("spalten") == 2:
        r = spec["rect"]
        teiler = spec["teiler"]
        links = [r[0], r[1], teiler - 5, r[3]]
        rechts = [teiler + 5, r[1], r[2], r[3]]
        rest = _para(page, links, text, spec["size"], spec["min"], ink)
        if rest:
            rest = _para(page, rechts, rest, spec["size"], spec["min"], ink)
        return rest
    return _para(page, spec["rect"], text, spec["size"], spec["min"], ink)


def _fortsetzungen_rendern(doc, items, ink) -> None:
    """Alle überlaufenden Abschnitte in EINEN gemeinsamen, 2-spaltigen 'Anhang' im Bogen-Stil
    fliessen lassen (statt je Abschnitt eine fast leere Seite). Zwischenüberschriften markieren
    die Abschnitte. KONZEPT §9: überträgt vorhandenen Inhalt, fügt keinen hinzu."""
    items = [(t, x) for t, x in items if x]
    if not items:
        return
    rest = "\n\n".join(f"‹{titel}›\n{text}" for titel, text in items)
    nr = 0
    while rest:
        nr += 1
        page = doc.new_page(width=_MEDIA[0], height=_MEDIA[1])
        _anhang_rahmen(page, ink, nr)
        rest = _para(page, [30, 58, 296, 748], rest, 8.5, 6, ink)          # linke Spalte
        if rest:
            rest = _para(page, [311, 58, 577, 748], rest, 8.5, 6, ink)     # rechte Spalte


def _anhang_rahmen(page, ink, nr) -> None:
    """Doppelrahmen + zentrierter Kapitälchen-Header + Spaltentrenner, damit die Anhangseite
    zum restlichen Bogen passt (Design-Kritik: Fortsetzung wirkte wie schmuckloser Text-Dump)."""
    page.draw_rect(fitz.Rect(9, 9, 594, 765), color=(0.55, 0.5, 0.42), width=1.4)
    page.draw_rect(fitz.Rect(14, 14, 589, 760), color=(0.72, 0.68, 0.6), width=0.6)
    titel = "ANHANG" if nr == 1 else f"ANHANG ({nr})"
    tw = fitz.get_text_length(titel, _FONT, 13)
    page.insert_text(((603 - tw) / 2, 38), titel, fontname=_FONT, fontsize=13, color=ink)
    page.draw_line(fitz.Point(30, 46), fitz.Point(573, 46), color=(0.55, 0.5, 0.42), width=0.9)
    page.draw_line(fitz.Point(303, 58), fitz.Point(303, 748), color=(0.82, 0.79, 0.72), width=0.4)


# --- Öffentliche API ---------------------------------------------------------

def rendere(charakter: Charakter, template_pfad: Path | None = None,
            layout: dict | None = None, codemap: dict | None = None,
            kalibrierung: bool = False) -> bytes:
    """Rendert `charakter` auf die DE-Vorlage und gibt das fertige PDF als Bytes zurück."""
    layout = layout or lade_layout()
    codemap = codemap or lade_codemap()
    doc = fitz.open(str(template_pfad or _TEMPLATE_STD))
    try:
        ink = tuple(layout["ink"])
        seiten = [doc[i] for i in range(doc.page_count)]

        if kalibrierung:
            _kalibriere(seiten, layout)
            return doc.tobytes()

        # 1) Einzelfelder
        for key, spec in layout["felder"].items():
            pfad = _SPEZIAL_PFAD.get(key, key)
            _zeichne_einzeilig(seiten[spec["s"]], spec["rect"], _text(_navigiere(charakter, pfad)),
                               spec["size"], spec["min"], spec.get("align", "l"), ink)

        # 2) Attribute
        for k, spec in layout["attribute"].items():
            a = charakter.attribute.get(k)
            if not a:
                continue
            p = seiten[spec["s"]]
            _zeichne_einzeilig(p, spec["mod"], _text(a.mod), 15, 9, "c", ink)
            if a.wert is not None:
                _zeichne_einzeilig(p, spec["wert"], str(a.wert), 10, 7, "c", ink)
            _zeichne_einzeilig(p, spec["save"], _text(a.rettungswurf), 8, 6, "c", ink)
            if a.rettung_geuebt:
                _marke(p, spec["save_prof"], ink)

        # 3) Fertigkeiten
        fmap = {f.schluessel: f for f in charakter.fertigkeiten}
        for k, spec in layout["fertigkeiten"].items():
            f = fmap.get(k)
            if not f:
                continue
            p = seiten[spec["s"]]
            _zeichne_einzeilig(p, spec["wert"], _text(f.mod), 8, 6, "c", ink)
            if f.geuebt:
                _marke(p, spec["prof"], ink)

        # 4) Grossboxen (mit Überlauf-Sammlung)
        texte = _grossbox_texte(charakter)
        fortsetzungen: list[tuple[str, str]] = []
        for key, spec in layout["grossbox"].items():
            text = texte.get(key, "")
            if not text:
                continue
            rest = _grossbox(seiten[spec["s"]], spec, text, ink)
            if rest:
                fortsetzungen.append((_BOX_TITEL.get(key, key), rest))

        # 5) Tabellen + Münzen
        _waffen_tabelle(seiten[0], layout["waffen_tabelle"], charakter.angriffe, ink)
        zauber_rest = _zauber_tabelle(seiten[1], layout["zauber_tabelle"],
                                      charakter.zauberwirken.zauber, codemap, ink)
        _muenzen(seiten[1], layout["muenzen"], charakter.ausruestung.muenzen, ink)

        # 6) Fortsetzungsseiten (KONZEPT §9) - alles in EINEN gemeinsamen Anhang fliessen lassen
        if zauber_rest:
            namen = "\n".join(f"Grad {z.grad}: {_text(z.name)}" for z in zauber_rest)
            fortsetzungen.append(("Weitere Zauber", namen))
        _fortsetzungen_rendern(doc, fortsetzungen, ink)

        return doc.tobytes()
    finally:
        doc.close()


def _kalibriere(seiten, layout) -> None:
    """Zeichnet alle Ziel-Rechtecke als rote Umrisse + Schlüssel (Feinjustage, KONZEPT §7.2)."""
    rot = (0.85, 0.1, 0.1)
    def kasten(p, rect, name):
        p.draw_rect(fitz.Rect(rect), color=rot, width=0.4)
        p.insert_text((rect[0] + 1, rect[1] + 5), name, fontname=_FONT, fontsize=3.2, color=rot)
    for key, spec in layout["felder"].items():
        kasten(seiten[spec["s"]], spec["rect"], key.split(".")[-1])
    for k, spec in layout["attribute"].items():
        for teil in ("mod", "wert", "save"):
            kasten(seiten[spec["s"]], spec[teil], f"{k}.{teil}")
    for k, spec in layout["fertigkeiten"].items():
        kasten(seiten[spec["s"]], spec["wert"], k[:5])
    for key, spec in layout["grossbox"].items():
        kasten(seiten[spec["s"]], spec["rect"], key)
