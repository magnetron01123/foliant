"""Die Prioritaetsbaender (importer/quellen.py) - die Antwort auf die Frage nach der
QUELLEN-WERTIGKEIT (BACKLOG.md par. 4, entschieden 31.07.2026).

Warum das ueberhaupt Tests braucht: `prioritaet` entscheidet bei einer fachlichen
Dublette, WELCHER Text die Auskunft liefert (app/db._dedupe_und_sortiere). Vorher wurde
die Zahl an vier Stellen unabhaengig vergeben - Config-Vorlage, DDB-Import, Open5e-Import,
Admin-Rueckfall -, ohne dass irgendwo stand, warum eine Zahl so ausfaellt. Zwei Stellen
konnten auseinanderlaufen, ohne dass etwas anschlug.

Die Baender sind eine KONVENTION, kein Zwang: `admin check` warnt bei Abweichung, bricht
aber nicht ab. Innerhalb eines Bandes ist Feinsortierung ausdruecklich erlaubt.
"""
import pytest

from importer import quellen as q


@pytest.mark.parametrize("name,merkmale,erwartet", [
    ("deutsches Kernregelwerk 2024 (Kaufbuch)",
     dict(sprache="de", edition="2024", herkunft="pdf", lizenz="privat"),
     q.BAND_DE_KERNREGELWERK),
    ("deutsches SRD (frei lizenziert)",
     dict(sprache="de", edition="2024", herkunft="pdf", lizenz="CC-BY-4.0"),
     q.BAND_DE_SRD),
    ("deutsches Altbuch 2014",
     dict(sprache="de", edition="2014", herkunft="pdf", lizenz="privat"),
     q.BAND_DE_ALTBUCH),
    ("englisches Kaufbuch (DDB)",
     dict(sprache="en", edition="2024", herkunft="ddb", lizenz="privat"),
     q.BAND_EN_KAUFBUCH),
    ("englische freie API-Quelle",
     dict(sprache="en", edition="2024", herkunft="open5e", lizenz="CC-BY-4.0"),
     q.BAND_EN_FREI),
])
def test_band_je_quellenklasse(name, merkmale, erwartet):
    assert q.band_fuer(**merkmale) == erwartet, name


@pytest.mark.parametrize("art", ["errata", "regelauslegung"])
@pytest.mark.parametrize("sprache,edition,herkunft", [
    ("en", "2024", "pdf"), ("de", "2024", "pdf"), ("en", "2014", "ddb")])
def test_revision_liegt_immer_im_eigenen_band(art, sprache, edition, herkunft):
    """Errata und Auslegung haengen an DEM, was sie sind - nicht an Sprache oder
    Bezugsweg. Ein deutsches Erratum bliebe eine Korrektur und duerfte den deutschen
    Grundtext trotzdem nicht ueberholen."""
    assert q.band_fuer(sprache=sprache, edition=edition, herkunft=herkunft,
                       inhaltsart=art) == q.BAND_REVISION


def test_revision_rankt_hinter_jedem_regelwerk():
    """Die eigentliche Zusage des Revisions-Bandes: bei gleichem Namen gewinnt immer der
    Grundtext. Ohne sie koennte eine Korrektur als kanonischer Text ausgegeben werden -
    also ein Satzfragment ('the damage is 8d6, not 6d6') statt der Regel."""
    regelwerke = (q.BAND_DE_KERNREGELWERK, q.BAND_DE_SRD, q.BAND_DE_ALTBUCH,
                  q.BAND_EN_KAUFBUCH, q.BAND_EN_FREI)
    assert all(b + q.BAND_BREITE <= q.BAND_REVISION for b in regelwerke)


def test_baender_ueberschneiden_sich_nicht():
    """Zwei Klassen im selben Zehnerbereich waeren keine Rangfolge mehr, sondern ein
    Zufall - und der Dedupe-Sieger haenge am alphabetischen Stichentscheid."""
    baender = sorted((q.BAND_DE_KERNREGELWERK, q.BAND_DE_SRD, q.BAND_DE_ALTBUCH,
                      q.BAND_EN_KAUFBUCH, q.BAND_EN_FREI, q.BAND_REVISION))
    assert all(b + q.BAND_BREITE <= naechstes
               for b, naechstes in zip(baender, baender[1:]))
    assert baender[-1] + q.BAND_BREITE <= q.STANDARD_PRIORITAET


def test_band_passt_prueft_den_ganzen_bereich():
    """Ein Band ist zehn breit - genau dafuer, dass ein Import innerhalb seiner Klasse
    feinsortieren darf (Open5e legt je Dokument einen Laufindex drauf)."""
    assert q.band_passt(q.BAND_EN_FREI, q.BAND_EN_FREI)
    assert q.band_passt(q.BAND_EN_FREI + 9, q.BAND_EN_FREI)
    assert not q.band_passt(q.BAND_EN_FREI + 10, q.BAND_EN_FREI)
    assert not q.band_passt(q.BAND_EN_FREI - 1, q.BAND_EN_FREI)


def test_importer_beziehen_ihre_zahlen_aus_den_baendern():
    """Der Punkt der ganzen Uebung: EINE Definition. Vergaebe ein Importer wieder seine
    eigene Zahl, liefe er beim naechsten Bandwechsel still daneben."""
    from importer import import_ddb, import_open5e
    assert import_ddb._DDB_PRIORITAET == q.BAND_EN_KAUFBUCH
    assert import_open5e._PRIORITAET_BASIS == q.BAND_EN_FREI


def test_config_haelt_ihre_eigenen_baender_ein():
    """Die echte config/foliant.toml gegen die Baender - dieselbe Pruefung, die
    `admin check` zur Laufzeit auf dem Bestand faehrt, nur schon hier.

    Sonst faellt eine vertauschte Zahl erst auf dem Pi auf, und zwar als falscher
    Dublettensieger in einer Antwort - der unauffaelligste aller Fehler."""
    from app import db as _db
    for block in _db.lade_konfig().get("quelle", []):
        band = q.band_fuer(sprache=block.get("sprache", "de"),
                           edition=block["edition"],
                           herkunft=block.get("herkunft", "pdf"),
                           inhaltsart=block.get("inhaltsart", "regelwerk"),
                           lizenz=block.get("lizenz"))
        assert q.band_passt(block.get("prioritaet", q.STANDARD_PRIORITAET), band), (
            f"{block['kuerzel']}: prioritaet={block.get('prioritaet')}, "
            f"erwartet {band}-{band + q.BAND_BREITE - 1}")
