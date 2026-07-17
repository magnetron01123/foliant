"""Renderer (deterministisch): neutrales Charaktermodell -> gefüllter DE-WotC-Bogen.

Zeichnet Werte per Koordinaten (layout_map) mit Auto-Fit auf eine Kopie der offiziellen
DE-Vorlage; der Vektor-Hintergrund (Logo, Rahmen, Illustrationen, rechtliche Fußzeile)
bleibt unverändert - es wird nur Text/Marken HINZUGEFÜGT (KONZEPT §9/§10). Bei echtem
Überlauf einer bereits im Quellbogen vorhandenen Sektion wird die LEERE Vorlagenseite
kopiert, direkt hinter der Ursprungsseite eingefügt und der Rest fließt dort in DIESELBE
Box weiter (KONZEPT §9) - nichts wird still abgeschnitten.

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
_SPEZIAL_PFAD = {"persoenlichkeit_gesinnung": "identitaet.gesinnung"}

# Typografische Sonderzeichen -> font-sichere Varianten. Helvetica-Base14 rendert z.B. das
# typografische Apostroph U+2019 (') sichtbar falsch als '·' ("Monk·s" statt "Monk's").
_ERSATZ = {"’": "'", "‘": "'", "“": '"', "”": '"', "′": "'",
           "–": "-", "—": "-", "…": "...", " ": " ", "ʼ": "'"}


# Deutsche Anführungszeichen U+201E/U+201A (und Guillemets) fehlten: Helvetica rendert sie
# als '·' ("·Wille des Schattens·", Befund 16.07.2026). DDBs Bullet U+2022 wird zum
# font-sicheren Mittelpunkt; hängt er vor der Aktionsökonomie-Klammer, räumt _STREU_PUNKT auf.
_ERSATZ.update({"„": '"', "‚": "'", "»": '"', "«": '"', "•": "·"})

_WUERFEL_EN = re.compile(r"\b(\d*)d(\d+)\b")               # 5d8 -> 5W8, d20 -> W20
_STREU_PUNKT = re.compile(r"\s*·\s*(?=[\])])")         # "(+2 / +1) ·]" -> "(+2 / +1)]"


def _saeubere(text: str) -> str:
    if not text:
        return text
    text = "".join(_ERSATZ.get(c, c) for c in text)
    # Deutsche Würfelnotation ZENTRAL (Befund: '5d8' im Trefferwürfel-Feld blieb als einzige
    # Angabe englisch, weil rohe Strings nie durchs Sprachmodell laufen). Deterministisch,
    # verändert keine Zahlen.
    text = _WUERFEL_EN.sub(lambda m: f"{m.group(1)}W{m.group(2)}", text)
    return _STREU_PUNKT.sub("", text)


def lade_layout(pfad: Path | None = None) -> dict:
    return json.loads((pfad or _LAYOUT_PFAD).read_text(encoding="utf-8"))


def lade_codemap(pfad: Path | None = None) -> dict:
    return json.loads((pfad or _CODEMAP_PFAD).read_text(encoding="utf-8"))


# --- Text-Primitive ----------------------------------------------------------

# Fett-Auszeichnung: \x01…\x02 markiert fette Läufe (Merkmalsköpfe, Sub-Features). Die Marker
# entstehen beim Textbau (_merkmal_text u.a.) und werden beim Zeichnen konsumiert - sie
# erreichen nie das Sprachmodell und nie die PDF-Ausgabe.
_FA, _FE = "\x01", "\x02"
_FONT_FETT = "hebo"
_MARKER = re.compile(r"[\x01\x02]")


def _ohne_marker(text: str) -> str:
    return _MARKER.sub("", text or "")


def _worte(absatz: str) -> list[tuple[str, bool]]:
    """'\\x01Kopf.\\x02 Rest' -> [('Kopf.', True), ('Rest', False), …] (wortweise)."""
    raus: list[tuple[str, bool]] = []
    fett = False
    for teil in re.split(r"([\x01\x02])", absatz):
        if teil == _FA:
            fett = True
        elif teil == _FE:
            fett = False
        else:
            raus.extend((w, fett) for w in teil.split())
    return raus


_FONT_OBJ = {_FONT: fitz.Font(_FONT), _FONT_FETT: fitz.Font(_FONT_FETT)}


def _textlaenge(text: str, font: str, size: float) -> float:
    """Echte Render-Breite. `fitz.get_text_length` misst Nicht-ASCII (äöüß) zu schmal -
    `fitz.Font().text_length` stimmt mit dem insert_text-Rendering überein (belegt
    16.07.2026: Span real 115,5 pt vs. get_text_length 112,2 pt -> Fett-Läufe überlappten
    den Folgetext, deutscher Text konnte Boxen minimal überfüllen)."""
    return _FONT_OBJ[font].text_length(text, fontsize=size)


def _fit_size(text: str, breite: float, size: float, minsize: float) -> float:
    while size > minsize and _textlaenge(text, _FONT, size) > breite:
        size -= 0.5
    return size


_KLAMMER_ENDE = re.compile(r"\s*\([^()]*\)\s*$")


def _zeichne_einzeilig(page, rect, text, size, minsize, align, ink) -> None:
    """Einzeiliges Feld mit definierten Überlauf-Stufen: (1) Auto-Fit bis minsize,
    (2) §5-Klammer '(English)' opfern, (3) horizontal auf die Boxbreite stauchen -
    NIE über die Boxgrenze zeichnen (Befund 16.07.2026: die Unterklasse lag auf dem
    Stufe-Oval, Zauber-Reichweiten ragten in die K/R/M-Spalte)."""
    if text is None or text == "":
        return
    text = _ohne_marker(_saeubere(text))
    r = fitz.Rect(rect)
    sz = _fit_size(text, r.width, size, minsize)
    tw = _textlaenge(text, _FONT, sz)
    if tw > r.width:
        kurz = _KLAMMER_ENDE.sub("", text)
        if kurz and kurz != text:
            text = kurz
            sz = _fit_size(text, r.width, size, minsize)
            tw = _textlaenge(text, _FONT, sz)
    baseline = r.y0 + (r.height + sz * 0.72) / 2
    if tw > r.width:
        punkt = fitz.Point(r.x0, baseline)
        page.insert_text(punkt, text, fontname=_FONT, fontsize=sz, color=ink,
                         morph=(punkt, fitz.Matrix(r.width / tw, 0, 0, 1, 0, 0)))
        return
    if align == "c":
        x = r.x0 + (r.width - tw) / 2
    elif align == "r":
        x = r.x1 - tw
    else:
        x = r.x0
    page.insert_text((x, baseline), text, fontname=_FONT, fontsize=sz, color=ink)


def _marke(page, punkt, ink) -> None:
    """X-Kreuz in einem ◇-Ankreuzfeld des Bogens (Übung, K/R/M, Rüstungsvertrautheit)."""
    x, y = punkt[0], punkt[1]
    h = 2.2
    page.draw_line(fitz.Point(x - h, y - h), fitz.Point(x + h, y + h), color=ink, width=1.0)
    page.draw_line(fitz.Point(x - h, y + h), fitz.Point(x + h, y - h), color=ink, width=1.0)


def _umbrich_absatz(absatz: str, breite: float, size: float) -> list[list[tuple[str, bool]]]:
    """Bricht EINEN Absatz auf Wortgrenzen um; Zeilen sind Läufe aus (Wort, fett).
    Fette Wörter werden mit ihrer echten (breiteren) Fontbreite gemessen.
    Leerer Absatz -> eine Leerzeile."""
    worte = _worte(absatz)
    if not worte:
        return [[]]
    space = _textlaenge(" ", _FONT, size)
    zeilen: list[list[tuple[str, bool]]] = []
    cur: list[tuple[str, bool]] = []
    cur_b = 0.0
    for wort, fett in worte:
        wb = _textlaenge(wort, _FONT_FETT if fett else _FONT, size)
        neu = wb if not cur else cur_b + space + wb
        if cur and neu > breite:
            zeilen.append(cur)
            cur, cur_b = [(wort, fett)], wb
        else:
            cur.append((wort, fett))
            cur_b = neu
    zeilen.append(cur)
    return zeilen


def _umbrich(text: str, breite: float, size: float) -> list[str]:
    """Zeilen als reine Strings (Diagnose/Tests)."""
    zeilen: list[str] = []
    for absatz in _saeubere(text).split("\n"):
        zeilen.extend(" ".join(w for w, _ in z) for z in _umbrich_absatz(absatz, breite, size))
    return zeilen


FORTS_MARKE = "(Fortsetzung nächste Seite)"
_SATZENDE = re.compile(r"(?<=[.!?])\s+")
_QUELLE_IM_KOPF = re.compile(r"\s*\([^()]*\d{2,4}[^()]*\)\s*\.?\s*$")   # "… (PHB-2024 102)."


def _fortsetzungskopf(erster_satz: str) -> str:
    """'Angriffe abwehren* (Deflect Attacks) (PHB-2024 102).' -> fetter Kopf 'Angriffe abwehren*
    (Deflect Attacks) (Fortsetzung):' - damit die Fortsetzungsseite sagt, WELCHES Merkmal sie
    fortsetzt. Die Quellenangabe entfällt (sie stand schon auf dem Bogen); ein schon
    vorhandenes '(Fortsetzung):' wird nicht verdoppelt (kettenfähig)."""
    kopf = _ohne_marker(erster_satz).strip()
    vorh = kopf.find("(Fortsetzung):")
    if vorh != -1:
        kopf = kopf[:vorh].rstrip()
    kopf = _QUELLE_IM_KOPF.sub("", kopf).rstrip(" .")
    return f"{_FA}{kopf} (Fortsetzung):{_FE}" if kopf else f"{_FA}(Fortsetzung):{_FE}"


def _blockstart(absaetze: list[str], idx: int) -> int:
    """Erste Zeile des Blocks (= Merkmal, durch Leerzeilen begrenzt), in dem `idx` liegt."""
    start = idx - 1
    while start > 0 and absaetze[start - 1].strip():
        start -= 1
    return start


def _ist_ueberschrift(zeile: str) -> bool:
    """Merkmals-ÜBERSCHRIFT = die GANZE Zeile ist ein Fett-Lauf ('\\x01Name (Quelle)\\x02').
    Sub-Feature-Köpfe sind nur am ZeilenANFANG fett ('\\x01Wappne dich.\\x02 Einmal pro …') -
    ein reiner startswith-Check hielte sie für Merkmalsgrenzen (Befund 17.07.2026: die
    Fortsetzung begann bei 'Wappne dich.' wieder kopflos)."""
    s = zeile.strip()
    return s.startswith(_FA) and s.endswith(_FE)


def _merkmalskopf_vor(absaetze: list[str], idx: int) -> str | None:
    """Fortsetzungskopf aus der letzten ÜBERSCHRIFTSZEILE vor `absaetze[idx]` - None, wenn
    davor keine steht (markerloser Text oder Spaltenfluss). Seit die Merkmale intern
    Absatz-Leerzeilen tragen (Sub-Feature-Struktur, 17.07.2026), taugt die Leerzeilen-
    Blockgrenze nicht mehr als Merkmalsgrenze: ein Umbruch ZWISCHEN zwei Sub-Features
    eines Merkmals bekam gar keinen Kopf ('Fasse dich.' begann verwaist), ein Umbruch IN
    einem Sub-Feature den falschen (Sub-Feature- statt Merkmalsname)."""
    for i in range(idx - 1, -1, -1):
        if _ist_ueberschrift(absaetze[i]):
            return _fortsetzungskopf(_erster_satz(absaetze[i]))
    return None


def _erster_satz(zeile: str) -> str:
    """Erster Satz OHNE Fett-Marker: der Punkt des Merkmalskopfs steht direkt vor \\x02,
    mit Markern erkennt _SATZENDE ihn nicht und der 'Kopf' fräse den ganzen Regelsatz mit."""
    return _SATZENDE.split(_ohne_marker(zeile))[0]


def _layout(text: str, breite: float, hoehe: float, sz: float,
            endmarke: str | None = None, kopf0: str | None = None) -> tuple[list, str, str | None]:
    """Layoutet `text` (mit Fett-Markern) in eine Spalte: (zeilen, rest, kopf).
    rest = '' wenn alles passt. `kopf` ist der Fortsetzungskopf, WENN der Rest mitten in
    einem Merkmal beginnt - der AUFRUFER stellt ihn nur bei echtem Boxwechsel voran
    (Spaltenfluss innerhalb desselben Kastens braucht keinen; Befund 16.07.2026: die
    Fortsetzungsseite begann verwaist mit 'Wenn du den Schaden auf 0 reduzierst …').

    Der Überlauf ist ABSATZTREU: es wandern nur GANZE Absätze (= Zeilen des Merkmals) in die
    Fortsetzung. Passt schon der ERSTE Absatz nicht, wird SATZTREU getrennt - nie mitten im
    Satz. `endmarke` wird als letzte Zeile gesetzt, wenn etwas übrig bleibt."""
    absaetze = text.split("\n")
    lh = sz * 1.28
    bloecke = [_umbrich_absatz(a, breite, sz) for a in absaetze]
    zeilen = [z for blk in bloecke for z in blk]
    if len(zeilen) * lh <= hoehe:
        return zeilen, "", None

    platz = max(1, int(hoehe / lh))
    nutz = max(1, platz - 1) if endmarke else platz
    gezeichnet: list = []
    naechster = 0
    for blk in bloecke:
        if len(gezeichnet) + len(blk) > nutz:
            break
        gezeichnet.extend(blk)
        naechster += 1

    # Keep-with-next: eine ÜBERSCHRIFT (ganzzeiliger Fett-Lauf) darf nicht als letzter
    # Absatz vor dem Umbruch stehen (Befund 17.07.2026: 'Betäubender Schlag' stand allein
    # am Boxende, der gesamte Body erst auf der Fortsetzungsseite) - sie wandert mit.
    while (naechster > 0 and naechster < len(absaetze)
           and _ist_ueberschrift(absaetze[naechster - 1])):
        blk = bloecke[naechster - 1]
        gezeichnet = gezeichnet[: len(gezeichnet) - len(blk)]
        naechster -= 1

    kopf: str | None = None
    if gezeichnet:
        rest_abs = absaetze[naechster:]
        # Ist der Rest (erste NICHT-LEERE Zeile - er kann mit der Absatz-Leerzeile starten)
        # KEIN neuer Merkmalskopf (ganzzeiliger Fett-Lauf), setzt er ein laufendes Merkmal
        # fort und braucht dessen Kopf: aus der letzten Überschrift davor; ohne Überschrift
        # davor traegt `kopf0` den Kopf aus der Vorspalte weiter (Spaltenfluss). Markerlose
        # Texte (z.B. Ausrüstung) fallen auf die alte Leerzeilen-Blockgrenze zurück - dort
        # IST der Block die sinnvolle Einheit.
        erste_zeile = next((a for a in rest_abs if a.strip()), "")
        if erste_zeile and not _ist_ueberschrift(erste_zeile):
            kopf = _merkmalskopf_vor(absaetze, naechster) or kopf0
            if kopf is None and rest_abs[0].strip() and absaetze[naechster - 1].strip():
                start = _blockstart(absaetze, naechster)
                kopf = _fortsetzungskopf(_erster_satz(absaetze[start]))
        rest = "\n".join(rest_abs)
    else:
        saetze = _SATZENDE.split(absaetze[0])
        genommen: list[str] = []
        for satz in saetze:
            if len(_umbrich_absatz(" ".join(genommen + [satz]), breite, sz)) > nutz:
                break
            genommen.append(satz)
        if genommen:
            gezeichnet = _umbrich_absatz(" ".join(genommen), breite, sz)
            schwanz = " ".join(saetze[len(genommen):]).strip()
        else:
            blk = bloecke[0]
            gezeichnet = blk[:nutz]
            schwanz = " ".join(w for z in blk[nutz:] for w, _ in z).strip()
        if schwanz:
            kopf = kopf0 if kopf0 else _fortsetzungskopf(_erster_satz(absaetze[0]))
        rest = "\n".join([schwanz] + absaetze[1:])

    while gezeichnet and not gezeichnet[-1]:
        gezeichnet.pop()
    rest = rest.strip()
    if rest and endmarke:
        gezeichnet.append([(endmarke, False)])
    return gezeichnet, rest, (kopf if rest else None)


def _mit_kopf(rest: str, kopf: str | None) -> str:
    """Fortsetzungskopf an die erste Rest-Zeile setzen (beim Verlassen der Box)."""
    if not rest or not kopf:
        return rest
    erste, _, folge = rest.partition("\n")
    return f"{kopf} {erste}" + (f"\n{folge}" if folge else "")


def _para(page, rect, text, size, minsize, ink, endmarke: str | None = None) -> str:
    """Zeichnet umbrochenen Text (mit Fett-Auszeichnung) in rect, Auto-Fit von size bis
    minsize. Gibt den NICHT passenden Rest zurück ('' wenn alles passt); beginnt der Rest
    mitten in einem Merkmal, trägt er den fetten Fortsetzungskopf."""
    if not text:
        return ""
    r = fitz.Rect(rect)
    text = _saeubere(text)
    sz = size
    for sz in _groessen(size, minsize):
        zeilen, rest, kopf = _layout(text, r.width, r.height, sz, endmarke)
        if not rest:
            _zeichne_zeilen(page, r, zeilen, sz, sz * 1.28, ink)
            return ""
    zeilen, rest, kopf = _layout(text, r.width, r.height, sz, endmarke)
    _zeichne_zeilen(page, r, zeilen, sz, sz * 1.28, ink)
    return _mit_kopf(rest, kopf)


def _groessen(size, minsize):
    s = size
    while s >= minsize:
        yield s
        s -= 0.5


def _zeichne_zeilen(page, r, zeilen, sz, lh, ink) -> None:
    """Zeichnet Zeilen aus (Wort, fett)-Läufen. Konsekutive Wörter GLEICHEN Fonts werden als
    EIN insert_text gesetzt: die PDF-Textebene behält echte Leerzeichen (Suche/Copy-Paste),
    wortweises Setzen verklebte sie ('erhältstfolgende')."""
    y = r.y0 + sz
    for zeile in zeilen:
        x = r.x0
        i = 0
        while i < len(zeile):
            j = i
            while j < len(zeile) and zeile[j][1] == zeile[i][1]:
                j += 1
            lauf = " ".join(w for w, _ in zeile[i:j])
            font = _FONT_FETT if zeile[i][1] else _FONT
            page.insert_text((x, y), lauf, fontname=font, fontsize=sz, color=ink)
            x += _textlaenge(lauf + " ", font, sz)
            i = j
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


# Sub-Features im Beschreibungstext ('Schlagserie. Du kannst …') fett wie bei D&D Beyond.
# Konservative Heuristik: kurzer Erstsatz (<=44 Zeichen), beginnt groß, kein gewöhnlicher
# Satzanfang - im Zweifel NICHT fett (ein fehlendes Fett ist harmlos, ein falsches stört).
_SUBKOPF = re.compile(r"^([^.:\n]{2,44}[.:])\s+(?=\S)")
_SUBKOPF_STOPP = ("Du ", "Die ", "Der ", "Das ", "Dein", "Ein ", "Eine ", "Einen ", "Einmal ",
                  "Wenn ", "Bei ", "Als ", "Am ", "An ", "Auf ", "Aus ", "Bis ", "Für ", "Im ",
                  "In ", "Mit ", "Nach ", "Solange ", "Um ", "Unmittelbar ", "Während ", "Zu ",
                  "You", "The ", "If ", "When", "Once ", "While ", "As ", "At ", "On ", "To ",
                  "A ", "An ", "Your")


def _markiere_subkoepfe(body: str) -> str:
    zeilen = []
    for zeile in body.split("\n"):
        m = _SUBKOPF.match(zeile)
        if m and zeile[:1].isupper() and not zeile.startswith(_SUBKOPF_STOPP):
            zeilen.append(f"{_FA}{m.group(1)}{_FE} {zeile[m.end():]}")
        else:
            zeilen.append(zeile)
    return "\n".join(zeilen)


def _merkmal_text(m) -> str:
    """Merkmal in der Struktur des DDB-Originals: der Name ist eine ÜBERSCHRIFT auf eigener
    Zeile (fett), darunter die Benefits - Beschreibungsabsätze (Sub-Features fett) und
    zuletzt die Aktionsökonomie-Zeilen ('| Increase two scores (+2 / +1)').

    Vorher klebte alles in EINER Zeile hintereinander ('Nebelwanderer-Attributswerterhöhung*
    (…) (RtHW 27). [Erhöhe zwei Werte (+2 / +1)]') - die Überschrift war nicht mehr als
    solche erkennbar und die Benefits verschmolzen mit ihr (David-Befund 17.07.2026,
    besonders sichtbar bei Merkmalen aus Überschrift + genau EINEM Benefit)."""
    quelle = f" ({m.quelle} {m.seite})" if m.quelle else ""
    zeilen = [f"{_FA}{_text(m.name)}{quelle}{_FE}"]
    body = _markiere_subkoepfe(_text(m.beschreibung))
    if body:
        zeilen.append(body)
    zeilen.extend(f"· {oek}" for oek in
                  (_oekonomie_zeile(_text(x)) for x in m.aktionsoekonomie) if oek)
    return "\n".join(zeilen).strip()


_ENDE_BULLET = re.compile(r"[\s•·]+$")


def _oekonomie_zeile(text: str) -> str:
    """'Increase two scores (+2 / +1) •' -> '… (+2 / +1)'. Das Bullet am Zeilenende ist ein
    DDB-Trennzeichen ohne Fortsetzung (die Box endet dort) - als eigene Zeile gerendert
    stünde es sonst sichtbar und sinnlos am Schluss."""
    return _ENDE_BULLET.sub("", text or "")


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
    return "\n".join(f"{_FA}{titel}:{_FE} {_text(v)}" for titel, v in teile if _text(v))


def _ausruestung_text(charakter) -> str:
    zeilen = []
    for g in charakter.ausruestung.gegenstaende:
        menge = f"{g.menge}× " if g.menge and g.menge not in ("1", "") else ""
        gew = f" ({_gewicht_kg(g.gewicht)})" if g.gewicht else ""
        zeilen.append(f"{menge}{_text(g.name)}{gew}")
    # Traglast-Grenzwerte (DDB: Weight Carried/Encumbered/Push-Drag-Lift) deterministisch in kg
    # anfügen - sie gingen bisher komplett verloren (Befund 16.07.2026).
    a = charakter.ausruestung
    grenzen = [("Getragen", a.getragenes_gewicht), ("Belastet ab", a.belastet_ab),
               ("Schieben/Ziehen/Heben", a.schieben_ziehen_heben)]
    werte = [f"{t}: {_gewicht_kg(w)}" for t, w in grenzen
             if w and w.strip() and w.strip() not in ("--", "—")]
    if werte:
        if zeilen:
            zeilen.append("")
        zeilen.append(f"{_FA}Traglast:{_FE} " + " · ".join(werte))
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


# --- Tabellen ----------------------------------------------------------------

def _waffen_tabelle(page, spec, angriffe, ink) -> None:
    y0 = spec["kopf_y"]
    lh = spec["zeilenhoehe"]
    sp = spec["spalten"]
    rows = angriffe[: spec["zeilen"]]
    if not rows:
        return

    def passt(texte, breite):
        s = spec["size"]
        for t in texte:
            if t:
                s = min(s, _fit_size(_saeubere(t), breite, spec["size"], spec["min"]))
        return s

    # EINE einheitliche Grösse für die GANZE Tabelle (kleinste, die jede Zelle jeder Spalte
    # fasst) -> Name/Bonus/Schaden gleich gross, gleiche Grundlinie.
    tsize = min(
        passt([_text(w.name) for w in rows], sp["name"][1] - sp["name"][0]),
        passt([_text(w.angriffsbonus) for w in rows], sp["atk"][1] - sp["atk"][0]),
        passt([_text(w.schaden) for w in rows], sp["schaden"][1] - sp["schaden"][0]),
        passt([_text(w.notiz) for w in rows], sp["notizen"][1] - sp["notizen"][0]),
    )
    for i, w in enumerate(rows):
        y = y0 + i * lh
        _zeichne_einzeilig(page, [sp["name"][0], y - 10, sp["name"][1], y + 2], _text(w.name), tsize, tsize, "l", ink)
        _zeichne_einzeilig(page, [sp["atk"][0], y - 10, sp["atk"][1], y + 2], _text(w.angriffsbonus), tsize, tsize, "c", ink)
        _zeichne_einzeilig(page, [sp["schaden"][0], y - 10, sp["schaden"][1], y + 2], _text(w.schaden), tsize, tsize, "l", ink)
        _zeichne_einzeilig(page, [sp["notizen"][0], y - 10, sp["notizen"][1], y + 2], _text(w.notiz), tsize, tsize, "l", ink)


_RITUAL = re.compile(r"(?i)\britual\b|\(R\)")


def _ist_ritual(z) -> bool:
    """Ritual-Marke NUR bei explizitem Beleg im Quelltext (Name/Notiz) - nie geraten."""
    return bool(_RITUAL.search(f"{_text(z.name)} {_text(z.notiz)}"))


# DDB-Zauber-Notizen eindeutschen: engl. Komponentenkürzel S(omatic) -> G(estisch),
# 'D:'(uration) -> 'WD:' (Wirkungsdauer). Regelbasiert, kein LLM (Befund 16.07.2026).
_NOTIZ_ERSATZ = [(re.compile(r"\bV/S/M\b"), "V/G/M"), (re.compile(r"\bV/S\b"), "V/G"),
                 (re.compile(r"\bS/M\b"), "G/M"), (re.compile(r"^D:\s*"), "WD: ")]


def _normalisiere_notiz(text: str) -> str:
    for muster, ersatz in _NOTIZ_ERSATZ:
        text = muster.sub(ersatz, text)
    return text


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
        _zeichne_einzeilig(page, [sp["notizen"][0], y - 10, sp["notizen"][1], y + 2], _normalisiere_notiz(_text(z.notiz)), spec["size"], spec["min"], sp["notizen"][2], ink)
        # K/R/M-Marken aus Wirkungsdauer/Komponenten/Ritual-Beleg (deterministisch, nichts
        # raten), exakt auf den ◇-Rauten der Zeile (eigene Rasterung: y0 + i*pitch).
        my = krm["y0"] + i * krm["pitch"]
        dauer = _text(z.wirkungsdauer).lower()
        komp = (z.komponenten or "").upper()
        if "konzentration" in dauer or "concentration" in dauer:
            _marke(page, (krm["k"], my), ink)
        if _ist_ritual(z):
            _marke(page, (krm["r"], my), ink)
        if "M" in komp:
            _marke(page, (krm["m"], my), ink)
    return zauber[spec["zeilen"]:]


def _muenzen(page, spec, muenzen, ink) -> None:
    for code, rect in spec["felder"].items():
        wert = muenzen.get(code)
        if wert not in (None, ""):
            _zeichne_einzeilig(page, rect, str(wert), spec["size"], spec["min"], "c", ink)


def _ruestungs_schluessel(en_text: str) -> set[str]:
    """'Light Armor, Medium Armor, Shields' -> {'leicht','mittelschwer','schilde'}.
    Nur wörtliche DDB-Kategorien (nichts raten); 'All Armor' = alle drei Rüstungsklassen."""
    t = en_text.lower()
    keys = set()
    if "all armor" in t:
        keys |= {"leicht", "mittelschwer", "schwer"}
    if "light armor" in t:
        keys.add("leicht")
    if "medium armor" in t:
        keys.add("mittelschwer")
    if "heavy armor" in t:
        keys.add("schwer")
    if "shield" in t:
        keys.add("schilde")
    return keys


def _ruestungs_marken(page, spec, ruestung, ink) -> None:
    """Kreuzt die Rüstungsvertrautheits-Rauten an (Leicht/Mittelschwer/Schwer/Schilde).
    Abgleich läuft über das englische ORIGINAL (deterministisch), nie über die Übersetzung."""
    en = " ".join(u.en or "" for u in ruestung)
    for key in _ruestungs_schluessel(en):
        _marke(page, spec[key], ink)


# --- Grossbox mit Spalten + Fortsetzung -------------------------------------

_PAD_R = 2.5   # rechter Innenabstand: Glyphen sollen die Rahmen-/Trennlinien nicht berühren


def _grossbox(page, spec, text, ink) -> str:
    """Zeichnet eine Grossbox; Rückgabe = Überlauf-Rest (mit Fortsetzungskopf, wenn er mitten
    in einem Merkmal beginnt). 2-spaltige Kästen fitten EINE gemeinsame Schriftgröße über
    beide Spalten (Befund 16.07.2026: Schriftgrad-Sprung zwischen den Spalten). Der
    Spaltenfluss links->rechts bekommt KEINEN Kopf (gleiche Box), nur der Boxwechsel."""
    text = _saeubere(text)
    if spec.get("spalten") == 2:
        r = spec["rect"]
        teiler = spec["teiler"]
        links = fitz.Rect(r[0], r[1], teiler - 5 - _PAD_R, r[3])
        rechts = fitz.Rect(teiler + 5, r[1], r[2] - _PAD_R, r[3])
        sz = spec["size"]
        for sz in _groessen(spec["size"], spec["min"]):
            z1, r1, k1 = _layout(text, links.width, links.height, sz)
            z2, r2, k2 = ((), "", None)
            if r1:
                # k1 wird NICHT gezeichnet (Spaltenfluss braucht keinen Kopf), aber als
                # kopf0 durchgereicht: bricht auch die rechte Spalte noch im selben Merkmal,
                # nennt die Fortsetzungsseite trotzdem den ECHTEN Merkmalsnamen.
                z2, r2, k2 = _layout(r1, rechts.width, rechts.height, sz,
                                     endmarke=FORTS_MARKE, kopf0=k1)
            if not r1 or not r2:
                break
        _zeichne_zeilen(page, links, z1, sz, sz * 1.28, ink)
        if r1:
            _zeichne_zeilen(page, rechts, z2, sz, sz * 1.28, ink)
        # Die Marke gehoert NUR an die letzte Spalte vor der Fortsetzung (die linke laeuft ja
        # nur in die rechte ueber - dort waere der Hinweis falsch).
        return _mit_kopf(r2, k2)
    rect = [spec["rect"][0], spec["rect"][1], spec["rect"][2] - _PAD_R, spec["rect"][3]]
    return _para(page, rect, text, spec["size"], spec["min"], ink, endmarke=FORTS_MARKE)


# Kopf-Feld, das jede Vorlagen-Kopie trägt, damit eine lose Fortsetzungsseite ihrem Charakter
# zuzuordnen bleibt (Befund 16.07.2026: der Kopf der Kopie war komplett leer). NUR der Name -
# Klasse/Stufe sind auf der Kopie nicht relevant und wurden dort fälschlich mitgefüllt (Befund
# 17.07.2026); die Seitenreihenfolge übernehmen jetzt die Seitenzahlen (_seitenzahlen).
_KOPIE_KOPF = ("identitaet.name",)


def _fortsetzungsseiten(doc, vorlage_pfad, reste, zauber_rest, layout, codemap, ink,
                        charakter) -> bool:
    """Überlauf wandert auf KOPIEN der LEEREN Vorlagenseite, die direkt hinter der
    Ursprungsseite eingefügt werden: jeder Rest fließt dort in DIESELBE Box weiter (die
    gedruckten Boxtitel der Vorlage beschriften ihn) - in DERSELBEN Schriftgröße wie auf
    der Ursprungsseite (Überlauf entsteht nur bei minsize -> die Kopie rendert fest mit
    minsize, statt größer zu fitten; Befund: Schriftgrad-Sprung zwischen den Seiten).
    Zauber-Überlauf setzt die Zaubertabelle der Seite-2-Kopie fort - mit allen Spalten und
    K/R/M-Marken. KONZEPT §9: überträgt vorhandenen Inhalt, fügt keinen hinzu."""
    zauber_seite = layout["zauber_tabelle"]["s"]
    quellseiten = set(reste) | ({zauber_seite} if zauber_rest else set())
    if not quellseiten:
        return False
    vorlage = fitz.open(str(vorlage_pfad))
    try:
        # Hintere Quellseite zuerst: Einfügen dahinter verschiebt vordere Indizes nicht.
        for s in sorted(quellseiten, reverse=True):
            pos = s + 1
            offen = reste.get(s, [])
            zrest = zauber_rest if s == zauber_seite else []
            while offen or zrest:
                doc.insert_pdf(vorlage, from_page=s, to_page=s, start_at=pos)
                seite = doc[pos]
                for key in _KOPIE_KOPF:
                    fspec = layout["felder"].get(key)
                    if fspec and fspec["s"] == s:
                        _zeichne_einzeilig(seite, fspec["rect"],
                                           _text(_navigiere(charakter, key)), fspec["size"],
                                           fspec["min"], fspec.get("align", "l"), ink)
                noch = []
                for spec, text in offen:
                    fest = {**spec, "size": spec["min"]}   # Kopie ERBT die Größe der Ursprungsbox
                    rest = _grossbox(seite, fest, text, ink)
                    if rest:
                        noch.append((spec, rest))
                offen = noch
                if zrest:
                    zrest = _zauber_tabelle(seite, layout["zauber_tabelle"], zrest, codemap, ink)
                pos += 1
    finally:
        vorlage.close()
    return True


_FUSSNOTE = "* = eigene deutsche Wiedergabe (kein offizieller deutscher Begriff belegt)"


def _seitenzahlen(doc, ink) -> None:
    """Nummeriert alle Seiten ('Seite N von M') rechts unten - nur wenn das Dokument über die
    Original-Vorlage hinaus gewachsen ist (Fortsetzungsseiten eingefügt), damit lose Blätter
    beim Ausdrucken wieder in der richtigen Reihenfolge liegen. Der unveränderte 2-Seiten-
    Bogen ohne Überlauf bleibt am Fuß frei - nichts Zusätzliches ohne Anlass (KONZEPT §9)."""
    gesamt = doc.page_count
    for i, seite in enumerate(doc):
        text = f"Seite {i + 1} von {gesamt}"
        breite = _textlaenge(text, _FONT, 5.5)
        seite.insert_text((seite.rect.width - 16 - breite, 771.5), text,
                          fontname=_FONT, fontsize=5.5, color=ink)


def _stern_fussnote(doc, ink) -> None:
    """§5: '*' markiert eine deutsche Wiedergabe ohne offiziellen Begriff. Auf jeder Seite,
    auf der die Marke vorkommt ('de* (en)'-Muster), erklärt eine Fußzeile das Zeichen."""
    for page in doc:
        if "* (" in page.get_text():
            page.insert_text((16, 771.5), _FUSSNOTE, fontname=_FONT, fontsize=5.5, color=ink)


# --- Öffentliche API ---------------------------------------------------------

def rendere(charakter: Charakter, template_pfad: Path | None = None,
            layout: dict | None = None, codemap: dict | None = None,
            kalibrierung: bool = False) -> bytes:
    """Rendert `charakter` auf die DE-Vorlage und gibt das fertige PDF als Bytes zurück."""
    layout = layout or lade_layout()
    codemap = codemap or lade_codemap()
    vorlage_pfad = template_pfad or _TEMPLATE_STD
    doc = fitz.open(str(vorlage_pfad))
    try:
        ink = tuple(layout["ink"])
        seiten = [doc[i] for i in range(doc.page_count)]

        if kalibrierung:
            _kalibriere(seiten, layout)
            return doc.tobytes()

        # 1) Einzelfelder. Sinne (z.B. Dunkelsicht) haben auf dem DE-Bogen kein eigenes Feld
        #    -> zweite Zeile in der Bewegungsrate-Box (DDB zeigt Speed und Senses benachbart);
        #    die Bewegungsrate rückt dann in die obere Hälfte (Befund 16.07.2026).
        sinne = _text(charakter.kampf.sinne)
        for key, spec in layout["felder"].items():
            if key == "kampf.bewegungsrate" and sinne:
                r = spec["rect"]
                mitte = (r[1] + r[3]) / 2
                _zeichne_einzeilig(seiten[spec["s"]], [r[0], r[1], r[2], mitte],
                                   _text(charakter.kampf.bewegungsrate),
                                   spec["size"], spec["min"], "c", ink)
                _zeichne_einzeilig(seiten[spec["s"]], [r[0], mitte, r[2], r[3]],
                                   sinne, 7, 5.5, "c", ink)
                continue
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

        # 4) Grossboxen (Überlauf-Sammlung je Quellseite)
        texte = _grossbox_texte(charakter)
        reste: dict[int, list[tuple[dict, str]]] = {}
        for key, spec in layout["grossbox"].items():
            text = texte.get(key, "")
            if not text:
                continue
            rest = _grossbox(seiten[spec["s"]], spec, text, ink)
            if rest:
                reste.setdefault(spec["s"], []).append((spec, rest))

        # 5) Tabellen + Münzen + Rüstungsvertrautheit
        _waffen_tabelle(seiten[0], layout["waffen_tabelle"], charakter.angriffe, ink)
        zauber_rest = _zauber_tabelle(seiten[1], layout["zauber_tabelle"],
                                      charakter.zauberwirken.zauber, codemap, ink)
        _muenzen(seiten[1], layout["muenzen"], charakter.ausruestung.muenzen, ink)
        rm = layout["ruestung_marken"]
        _ruestungs_marken(seiten[rm["s"]], rm, charakter.uebungen.ruestung, ink)

        # 6) Fortsetzungsseiten (KONZEPT §9): Kopien der leeren Vorlagenseite direkt hinter
        #    der Ursprungsseite; Reste fliessen in dieselben Boxen/Tabellen weiter
        gewachsen = _fortsetzungsseiten(doc, vorlage_pfad, reste, zauber_rest, layout, codemap,
                                        ink, charakter)
        if gewachsen:
            _seitenzahlen(doc, ink)

        # 7) §5-Fussnote: '*' am Seitenfuss erklären, wo es zum Einsatz kam
        _stern_fussnote(doc, ink)

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
