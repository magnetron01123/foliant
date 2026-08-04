"""Was die Runde gemeldet hat, bleibt behoben (O4/M5).

Jeder 👎-Befund aus einem Rueckmeldungs-Durchgang bekommt hier seinen Regressionstest -
an EINER Stelle, damit sichtbar bleibt, was der Spieltisch tatsaechlich gefunden hat und
was daraus wurde. Der Ablauf verlangt das ausdruecklich: eine Verhaltensaenderung ohne
Test, der ohne sie fehlschlaegt, ist nicht belegt, sondern nur plausibel
(.claude/ablaeufe/rueckmeldungen.md).

Durchgang 04.08.2026 - drei Markierungen, drei Befunde:
  1. S2/S3/S7/S11  Der Eintragsname blieb englisch mit '*', obwohl das Glossar den
                   deutschen Begriff fuehrt.
  2. B4            Ein Monster-Merkmal wurde als Antwort auf eine Spielerfrage ausgegeben.
  3. B2            Bei einem Leerbefund kam eine Vermutung ueber ein fehlendes Buch dazu.
"""
from __future__ import annotations

import sqlite3

import pytest

from app import glossar as g


def _glossar_db(zeilen):
    """Eine Glossar-DB mit genau den uebergebenen (en, de)-Paaren, alle offiziell."""
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute("CREATE TABLE glossar (id INTEGER PRIMARY KEY, term_en TEXT NOT NULL, "
                "term_de TEXT NOT NULL, offiziell INTEGER NOT NULL, quelle TEXT, "
                "edition_quelle TEXT, seite TEXT)")
    con.execute("CREATE UNIQUE INDEX idx ON glossar(term_en, term_de)")
    con.executemany("INSERT INTO glossar (term_en, term_de, offiziell, quelle) "
                    "VALUES (?,?,1,'Spielerhandbuch')", zeilen)
    con.commit()
    g.leere_cache()
    return con


# --- Befund 1: der Eintragsname blieb englisch ----------------------------------------

def test_der_eintragsname_wird_mitannotiert():
    """Bis 04.08.2026 durchsuchte `begriffe_im_text` nur `body_md` - also alles AUSSER
    der Ueberschrift der Antwort.

    Die Folge am Spieltisch: Das Modell bekam 30 amtliche Begriffe aus dem Fliesstext
    mitgeliefert und gab ausgerechnet den Namen, den der Spieler ZUERST liest, englisch
    mit '*' aus. Ein Feld, das die '*'-Fehlmarkierung verhindern soll, deckte die
    sichtbarste Stelle nicht ab."""
    con = _glossar_db([("Archfey", "Erzfee")])
    name, body = "Archfey Patron", "Your pact draws on the power of the Feywild."

    # Das ist die Regression: nur der Body kennt den Begriff NICHT.
    assert not g.begriffe_im_text(con, body)
    # Mit dem Namen davor - so setzt ausgabe.py den Text heute zusammen - schon.
    treffer = {z["term_en"]: z["term_de"] for z in g.begriffe_im_text(con, f"{name}\n{body}")}
    assert treffer == {"Archfey": "Erzfee"}
    con.close()


def test_detailausgabe_liefert_den_namen_in_begriffe_deutsch(monkeypatch):
    """Der Test darueber prueft nur die Glossar-Funktion - das ist zu flach: Ein
    Mutationstest am 04.08.2026 zeigte, dass die Aenderung in `ausgabe._detail`
    rueckgaengig gemacht werden konnte, ohne dass ein Test fehlschlug.

    DAS hier ist der eigentliche Regressionstest: Er laeuft durch den echten Detailpfad
    und prueft, dass der Eintragsname im Feld `begriffe_deutsch` ankommt - denn nur was
    dort steht, gibt das Modell ohne '*' aus."""
    from app.tools import ausgabe

    con = _glossar_db([("Archfey", "Erzfee")])
    eintrag = {"id": 1, "name_de": None, "name_en": "Archfey Patron", "kategorie": "klasse",
               "edition": "2024", "sprache": "en", "quelle_titel": "Player's Handbook",
               "quelle": "ddb-phb-2024-en", "seite": None,
               "body_md": "Your pact draws on the power of the Feywild.", "lizenz": None}
    monkeypatch.setattr(ausgabe, "_anzeige_name", lambda c, e: "Archfey Patron")

    d = ausgabe._detail(eintrag, con)

    assert d.get("begriffe_deutsch", {}).get("Archfey") == "Erzfee", (
        "der Name der Antwort bleibt sonst englisch mit '*' - genau der gemeldete Befund")
    con.close()


def test_teilbegriffe_werden_nur_mit_beleg_uebernommen():
    """`offiziell=1` ist hier richtig und anderswo gefaehrlich - ein falsches Paar wandert
    durch den ganzen Bestand und nimmt die '*'-Kennzeichnung an Stellen weg, wo sie
    hingehoert. Die Schranke: Die belegende Zusammensetzung muss offiziell dastehen UND
    den deutschen Begriff woertlich enthalten."""
    from importer import import_glossar as ig

    con = _glossar_db([("Warlock of the Archfey", "Hexenmeister der Erzfee")])
    assert ig.seed_teilbegriffe(con) == 1
    paare = {r["term_en"]: r["term_de"] for r in con.execute(
        "SELECT term_en, term_de FROM glossar WHERE quelle = ?", (ig.TEIL_QUELLE,))}
    assert paare == {"Archfey": "Erzfee"}     # 'Great Old One' fehlt der Beleg -> keine Zeile
    con.close()


def test_ohne_belegende_form_entsteht_keine_zeile():
    """Faellt der Beleg weg (etwa weil ein Re-Import die Quelle aendert), soll die Antwort
    auf das ehrliche '*' zurueckfallen. Lieber eine fehlende Bruecke als eine erfundene
    (Regel 1)."""
    from importer import import_glossar as ig

    con = _glossar_db([("Something Else", "Etwas Anderes")])
    assert ig.seed_teilbegriffe(con) == 0
    con.close()


def test_abweichende_uebersetzung_deckt_die_ableitung_nicht():
    """Nennt die laengere Form den Begriff anders, ist die Ableitung nicht mehr gedeckt -
    dann darf sie NICHT entstehen, auch wenn das englische Lemma passt."""
    from importer import import_glossar as ig

    con = _glossar_db([("Warlock of the Archfey", "Hexenmeister der Feenfürstin")])
    assert ig.seed_teilbegriffe(con) == 0
    con.close()


@pytest.mark.parametrize("nicht_drin, grund", [
    ("Celestial", "Glossar kennt nur 'Celestisches Wesen' - die Patron-Form waere geraten"),
    ("Undead", "aus einem Band ohne deutsche Fassung - hier ist '*' richtig"),
    ("Great Old One", "nur im Genitiv belegt ('des Großen Alten') - Nominativ waere "
                      "eine grammatische Ableitung"),
])
def test_ungedeckte_teilbegriffe_bleiben_draussen(nicht_drin, grund):
    """Was nicht woertlich belegt ist, kommt nicht rein - auch wenn es 'offensichtlich'
    stimmt.

    'Great Old One' stand zunaechst mit drin und wurde vom ersten echten Seeding-Lauf
    (04.08.2026, Pi) abgewiesen: Der Beleg 'Hexenmeister des Großen Alten' ist ein
    Genitiv, die Nominativform steht nirgends im Bestand. Die Schranke hatte recht und der
    Eintrag ging raus - Flexion ist Sache der Flexions-Bruecke auf BELEGTEN Lemmata, nicht
    einer kuratierten Liste, die neue erfindet."""
    from importer import import_glossar as ig

    assert not any(en == nicht_drin for en, _de, _beleg in ig.TEILBEGRIFFE), grund


# --- Befund 2: Monster-Merkmal als Antwort auf eine Spielerfrage -----------------------

def test_monster_steckbrief_traegt_den_geltungs_hinweis():
    """Auf 'Kann man 2 Gelegenheitsangriffe machen?' kam ein 'Ja', belegt mit der Hydra.
    Der Treffer war geerdet - falsch war, ein Monster-Merkmal als allgemeine Regel
    auszugeben. Fuer Spielercharaktere lautet die Antwort 'nein', und die eigene
    Folgeantwort widerrief es zwei Minuten spaeter (B4).

    Der Hinweis laeuft ueber Kanal 1 (Tool-Ausgabe), laut SPEC den zuverlaessigsten -
    eine Prompt-Regel mehr haette hier nichts gebracht, weil B4 bereits in beiden
    Prompt-Kanaelen steht."""
    from app.tools import ausgabe

    hinweis = ausgabe.HINWEIS_MONSTER_MERKMAL
    assert "Spielercharaktere" in hinweis and "B4" in hinweis
    # Der Hinweis muss die HANDLUNG nennen, nicht nur die Lage beschreiben.
    assert "ausdruecklich dazu" in hinweis


@pytest.mark.parametrize("kategorie, erwartet", [("monster", True), ("regel", False),
                                                 ("zauber", False)])
def test_geltungs_hinweis_nur_bei_monstern(kategorie, erwartet, monkeypatch):
    """Ein Hinweis, der ueberall steht, wird nirgends gelesen - deshalb haengt er an
    `kategorie == 'monster'` und an sonst nichts."""
    from app.tools import ausgabe

    eintrag = {"id": 1, "name_de": "Hydra", "name_en": "Hydra", "kategorie": kategorie,
               "edition": "2024", "sprache": "de", "quelle_titel": "SRD 5.2.1",
               "quelle": "srd-de", "seite": "334", "body_md": "Text", "lizenz": None}
    monkeypatch.setattr(ausgabe, "_anzeige_name", lambda con, e: "Hydra")
    monkeypatch.setattr(ausgabe, "_zitat", lambda e: "Quelle: SRD")
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    d = ausgabe._detail(eintrag, con)
    assert ("hinweis_monster_merkmal" in d) is erwartet
    con.close()


# --- Befund 3: Spekulation ueber fehlende Buecher --------------------------------------

def test_kein_mutmassen_ueber_fehlende_buecher():
    """Der Bot spekulierte bei einem Leerbefund ueber ein fehlendes Buch - und war damit
    REGELKONFORM: Der Prompt gab diese Formulierung woertlich vor ('eventuell fehlt ein
    Buch'). Der Befund lag in der Regel, nicht im Modell.

    Seit `/bestand` gibt es die belegte Auskunft darueber, welche Buecher da sind. Eine
    Vermutung, wo eine Abfrage moeglich ist, ist genau die Sorte Fuellstoff, die B2
    verbietet."""
    from config import stil

    import pathlib

    from app.tools import ausgabe

    anweisung = pathlib.Path("config/projektanweisung.md").read_text(encoding="utf-8")
    for text in (stil.INSTRUCTIONS, anweisung):
        assert "eventuell fehlt ein Buch" not in text.lower()
        assert "/bestand" in text
    # Kanal 1 zuletzt und am wichtigsten: Der Leerbefund-Hinweis BOT die Vermutung
    # ausdruecklich an ("Eventuell fehlt schlicht ein Buch"). Solange er das tut, ist
    # jede Prompt-Regel dagegen nur die zweitlauteste Stimme im Kontext.
    assert "eventuell fehlt" not in ausgabe.HINWEIS_LEER.lower()
    assert "/bestand" in ausgabe.HINWEIS_LEER


def test_beide_kanaele_verbieten_das_mutmassen():
    """S/B-Regeln muessen in BEIDEN Prompt-Kanaelen stehen - die Projektanweisung richtet
    jede Person selbst ein, wer das nicht tut, bekaeme sonst keine."""
    import pathlib

    from config import stil

    anweisung = pathlib.Path("config/projektanweisung.md").read_text(encoding="utf-8")
    for text in (stil.INSTRUCTIONS, anweisung):
        assert "mutmaß" in text.lower() or "mutmass" in text.lower()
