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


# --- Durchgang 04.08.2026 (abends): abgeschnittene Uebersichtsantwort -----------------

def test_trefferliste_sagt_was_mit_unuebersetzten_namen_zu_tun_ist():
    """Gemeldeter Befund: Eine Uebersichtsantwort gab 'Mist Wanderer*', 'Spirit Medium*',
    'Touch of Death*' aus - englische Namen mit einem Stern dran.

    Das '*' heisst "keine offizielle Uebersetzung"; es ERSETZT die Uebersetzung nicht.
    S3 Stufe 4 verlangt ausdruecklich eine deutsche Wiedergabe und *nicht* Englisch mitten
    im Satz. Die Regel stand in beiden Prompt-Kanaelen UND im Detail-Hinweis - nur die
    TREFFERLISTE trug sie nie, und genau aus der beantwortet das Modell Uebersichtsfragen.
    Nach der eigenen Lehre vom Vormittag heisst das: die Regel sass im falschen Kanal."""
    from app.tools import ausgabe

    antwort = {}
    treffer = [
        {"eintrag_id": 1, "name_de": None, "name_en": "Mist Walker",
         "anzeige_name": "Mist Walker"},                       # keine Uebersetzung belegt
        {"eintrag_id": 2, "name_de": None, "name_en": "Archfey Patron",
         "anzeige_name": "Erzfee-Schutzherr (Archfey Patron)"},  # ueber Glossar aufgeloest
        {"eintrag_id": 3, "name_de": "Feuerball", "name_en": "Fireball",
         "anzeige_name": "Feuerball (Fireball)"},
    ]
    ausgabe.markiere_unuebersetzte(antwort, treffer)

    hinweis = antwort.get("hinweis_ohne_deutschen_namen", "")
    assert hinweis, "ohne Hinweis reicht das Modell den englischen Namen durch"
    assert "1 Treffer" in hinweis, "nur der unaufgeloeste Name zaehlt, nicht alle drei"
    assert "Mist Walker" in hinweis, "das Beispiel macht die Anweisung konkret"
    assert "ersetzt sie nicht" in hinweis, "der haeufigste Irrtum muss benannt sein"


def test_kein_hinweis_wenn_alles_uebersetzt_ist():
    """Ein Hinweis, der immer steht, wird nicht gelesen."""
    from app.tools import ausgabe

    antwort = {}
    ausgabe.markiere_unuebersetzte(antwort, [
        {"name_de": "Feuerball", "name_en": "Fireball",
         "anzeige_name": "Feuerball (Fireball)"}])
    assert "hinweis_ohne_deutschen_namen" not in antwort


def test_die_echte_suche_liefert_den_hinweis_mit(tmp_path, monkeypatch):
    """Die beiden Tests darueber pruefen die Funktion - das ist zu flach, und ich bin
    genau darauf schon einmal hereingefallen: Ein Mutationslauf am 04.08.2026 entfernte
    den Aufruf aus `suche.py`, und alle Tests blieben gruen.

    DAS hier ist der Regressionstest: Er geht durch `foliant_suche_bestand` und prueft,
    dass der Hinweis in der echten Antwort ankommt - denn nur was dort steht, sieht das
    Modell."""
    import sqlite3

    from app import db as adb
    from app.tools import suche
    from tests.hilfen import SCHEMA

    pfad = tmp_path / "unuebersetzt.sqlite"
    con = sqlite3.connect(pfad)
    con.executescript(SCHEMA.read_text(encoding="utf-8"))
    con.execute("INSERT INTO quellen (kuerzel,titel,sprache,edition,herkunft,lizenz,"
                "prioritaet,inhaltsart) VALUES ('ddb-rthw-en','Ravenloft','en','2024',"
                "'ddb','privat',40,'abenteuer_setting')")
    con.executemany(
        "INSERT INTO eintraege (quelle_id,kategorie,name_de,name_en,sprache,edition,seite,"
        "body_md) VALUES (?,?,?,?,?,?,?,?)",
        [(1, "hintergrund", None, "Mist Wanderer", "en", "2024", None,
          "*Kontext: Backgrounds*\n\nA Mist Wanderer background feature."),
         (1, "hintergrund", None, "Spirit Medium", "en", "2024", None,
          "*Kontext: Backgrounds*\n\nA Spirit Medium background feature.")])
    con.commit()
    con.execute("INSERT INTO eintraege_fts(eintraege_fts) VALUES('rebuild')")
    con.commit()
    con.close()
    monkeypatch.setattr(adb, "standard_pfad", lambda: pfad)

    antwort = suche.foliant_suche_bestand("background", kategorie="hintergrund")

    assert antwort.get("treffer"), "Vorbedingung: die Suche muss etwas finden"
    hinweis = antwort.get("hinweis_ohne_deutschen_namen", "")
    assert hinweis, ("ohne diesen Hinweis reicht das Modell 'Mist Wanderer*' durch - "
                     "genau der gemeldete Befund")
    assert "ersetzt sie nicht" in hinweis


def test_auch_die_facettensuche_liefert_den_hinweis(tmp_path, monkeypatch):
    """Die Suche hat ZWEI Ausgabewege - Freitext und reine Facetten -, und ein Hinweis,
    der nur an einem haengt, fehlt genau dann, wenn jemand ohne Suchbegriff stoebert
    ('zeig mir alles mit HG 5'). Beim ersten Mutationslauf traf die Mutation den einen
    Pfad und der Test den anderen: gruen, obwohl kaputt."""
    import sqlite3

    from app import db as adb
    from app.tools import suche
    from tests.hilfen import SCHEMA

    pfad = tmp_path / "facetten-unuebersetzt.sqlite"
    con = sqlite3.connect(pfad)
    con.executescript(SCHEMA.read_text(encoding="utf-8"))
    con.execute("INSERT INTO quellen (kuerzel,titel,sprache,edition,herkunft,lizenz,"
                "prioritaet,inhaltsart) VALUES ('ddb-rthw-en','Ravenloft','en','2024',"
                "'ddb','privat',40,'abenteuer_setting')")
    con.execute(
        "INSERT INTO eintraege (quelle_id,kategorie,name_de,name_en,sprache,edition,seite,"
        "body_md) VALUES (1,'monster',NULL,'Mist Horror','en','2024',NULL,?)",
        ("*Kontext: Bestiary*\n\n_Medium Aberration, Neutral Evil_\n\n"
         "**Herausforderungsgrad** 5 (1.800 EP)\n\nA creature of the mists.",))
    con.commit()
    con.execute("INSERT INTO eintraege_fts(eintraege_fts) VALUES('rebuild')")
    con.commit()
    con.close()
    monkeypatch.setattr(adb, "standard_pfad", lambda: pfad)

    antwort = suche.foliant_suche_bestand(kategorie="monster", hg="5")

    assert antwort.get("treffer"), "Vorbedingung: der Facettenfilter muss greifen"
    assert antwort.get("hinweis_ohne_deutschen_namen"), (
        "der Struktur-Pfad trug den Hinweis nicht - dieselbe Luecke, andere Tuer")


def test_antwortbudget_traegt_mehr_als_drei_discord_nachrichten():
    """Die Antwort riss mitten im Satz ab, und die Warnung darueber kommt NACH der
    bezahlten Antwort - der Nutzer zahlt fuer etwas, das er nicht bekommt.

    Der Wert ist bewusst nur ein Schritt: 3000 Tokens trugen deutsch schon rund vier
    Discord-Nachrichten. Das eigentliche Gegenmittel ist die Gliederungsregel im
    Discord-Zusatz - dieser Wert faengt die knappen Faelle."""
    import inspect

    from app import llm

    vorgabe = inspect.signature(llm.fahre_schleife).parameters["max_tokens"].default
    assert vorgabe >= 4000, "knappe Ueberschreitungen reissen sonst weiter mitten im Satz"
    assert vorgabe <= 8000, ("mehr Budget heisst laengere Antworten - ab etwa drei "
                             "Discord-Nachrichten liest sie am Tisch niemand mehr")


def test_discord_zusatz_verlangt_gliedern_statt_ausschuetten():
    """Der Discord-Zusatz traegt bewusst NUR Form - und wie lang eine Antwort sein darf,
    ist Form. Die Regel muss zugleich klarstellen, dass EIN Eintrag weiterhin vollstaendig
    kommt: 'kompakt heisst knapp formuliert, nicht gekuerzt' bleibt unangetastet."""
    import pathlib

    text = pathlib.Path("config/discord_zusatz.md").read_text(encoding="utf-8")
    assert "Kategorien" in text and "Anzahl" in text
    assert "vollständig" in text, "sonst liest sich die Regel als Erlaubnis zu kuerzen"


def test_beide_kanaele_verbieten_das_mutmassen():
    """S/B-Regeln muessen in BEIDEN Prompt-Kanaelen stehen - die Projektanweisung richtet
    jede Person selbst ein, wer das nicht tut, bekaeme sonst keine."""
    import pathlib

    from config import stil

    anweisung = pathlib.Path("config/projektanweisung.md").read_text(encoding="utf-8")
    for text in (stil.INSTRUCTIONS, anweisung):
        assert "mutmaß" in text.lower() or "mutmass" in text.lower()


# --- Pi-Eval 06.08.2026 (Fall F2): Unterklasse ohne deutschen Namen ------------------

def test_englische_unterklasse_nennt_ihre_stufen_merkmale(tmp_path, monkeypatch):
    """Gemeldeter Befund: Auf "Was kann der Undead Patron?" antwortete der Bot, der
    Bestand fuehre nur den Flavor-Text - die fuenf Stufen-Merkmale stehen aber als
    eigene Eintraege daneben.

    Ursache war nicht das Modell, sondern die Ausgabe: `_verwandte_klassenabschnitte`
    stieg bei fehlendem `name_de` sofort aus und suchte ausserdem nur unter
    'Klassen > <Name>'. Englische DDB-Unterklassen erfuellen beides nicht - ihre
    Merkmale wurden also nie genannt, und B15 (Fragmente zu EINER Antwort zusammen-
    setzen) kann nur zusammensetzen, was die Ausgabe ueberhaupt ausweist."""
    import sqlite3

    from app import db as adb
    from app.tools import nachschlagen as ns
    from tests.hilfen import SCHEMA

    pfad = tmp_path / "unterklasse-en.sqlite"
    con = sqlite3.connect(pfad)
    con.executescript(SCHEMA.read_text(encoding="utf-8"))
    con.execute("INSERT INTO quellen (kuerzel,titel,sprache,edition,herkunft,lizenz,"
                "prioritaet,inhaltsart) VALUES ('ddb-rthw-en','Ravenloft','en','2024',"
                "'ddb','privat',40,'abenteuer_setting')")
    con.executemany(
        "INSERT INTO eintraege (quelle_id,kategorie,name_de,name_en,sprache,edition,seite,"
        "body_md) VALUES (?,?,?,?,?,?,?,?)",
        [(1, "klasse", None, "Undead Patron (Warlock)", "en", "2024", None,
          "*Kontext: Subclasses*\n\nYou have made a pact with a creature of undeath."),
         (1, "klasse", None, "Level 3: Form of Dread", "en", "2024", None,
          "*Kontext: Subclasses > Undead Patron (Warlock)*\n\nAs a Bonus Action ..."),
         (1, "klasse", None, "Level 6: Grave Touched", "en", "2024", None,
          "*Kontext: Subclasses > Undead Patron (Warlock)*\n\nYour patron's powers ...")])
    con.commit()
    con.execute("INSERT INTO eintraege_fts(eintraege_fts) VALUES('rebuild')")
    con.commit()
    con.close()
    monkeypatch.setattr(adb, "standard_pfad", lambda: pfad)

    antwort = ns.foliant_hol_eintrag("klasse", name="Undead Patron")

    assert antwort.get("gefunden"), "Vorbedingung: die Unterklasse muss gefunden werden"
    verwandte = antwort.get("verwandte_abschnitte") or []
    assert "Level 3: Form of Dread" in verwandte and "Level 6: Grave Touched" in verwandte, (
        f"Stufen-Merkmale nicht ausgewiesen ({verwandte}) - genau der gemeldete Befund")
    assert "Undead Patron (Warlock)" not in verwandte, "der Eintrag selbst gehoert nicht dazu"
    assert "B15" in antwort.get("hinweis_abschnitte", ""), \
        "ohne die Zusammensetz-Ansage bietet das Modell die Merkmale nur an"


# --- Codeblock-Breite (Messung an echten Antworten, 08.08.2026) ------------------------

def _regel_db(tmp_path, eintraege):
    """Eine Bestands-DB mit genau den uebergebenen (name_de, name_en, body)-Regeln."""
    import sqlite3

    from tests.hilfen import SCHEMA

    pfad = tmp_path / "regeln.sqlite"
    con = sqlite3.connect(pfad)
    con.executescript(SCHEMA.read_text(encoding="utf-8"))
    con.execute("INSERT INTO quellen (kuerzel,titel,sprache,edition,herkunft,lizenz,"
                "prioritaet,inhaltsart) VALUES ('srd-de','SRD','de','2024','srd',"
                "'cc-by-4.0',20,'regelwerk')")
    con.executemany(
        "INSERT INTO eintraege (quelle_id,kategorie,name_de,name_en,sprache,edition,"
        "seite,body_md) VALUES (1,'regel',?,?,'de','2024',NULL,?)", eintraege)
    con.commit()
    con.execute("INSERT INTO eintraege_fts(eintraege_fts) VALUES('rebuild')")
    con.commit()
    con.close()
    return pfad


def test_regel_nennt_die_im_text_zitierten_geschwister(tmp_path, monkeypatch):
    """Gemeldeter Befund (10.08.2026, zwei 👎 auf beide Haelften derselben Antwort):
    Auf "grapple" kam der Glossar-Eintrag "Gepackt halten" - der Zustand und wie er endet.
    WIE man packt, steht im "Waffenlosen Angriff", und der Bestandstext sagt das selbst:
    *Siehe auch* „Waffenloser Angriff". Der Eintrag liegt im Bestand. Die Antwort hat ihn
    trotzdem nur ANGEBOTEN ("Sag Bescheid, wenn du ... brauchst") - genau das, was B15
    verbietet.

    Kein Prompt-Fall: B15 stand in beiden Prompt-Kanaelen UND als Grounding-Hinweis.
    `_verwandte_klassenabschnitte` filterte nur auf kategorie='klasse', also sah die
    Ausgabe den Verweis nie. Dieselbe Lehre wie am 06.08.2026 - B15 kann nur
    zusammensetzen, was die Ausgabe ueberhaupt nennt."""
    from app import db as adb
    from app.tools import nachschlagen as ns

    pfad = _regel_db(tmp_path, [
        ("Gepackt halten", "Grappling",
         "Siehe auch_ „Gepackt“ und „Waffenloser Angriff“.\n\nEine Kreatur kann eine "
         "andere packen und festhalten."),
        ("Waffenloser Angriff", "Unarmed Strike",
         "Statt Schaden kannst du das Ziel packen."),
        ("Gepackt", "Grappled", "Zustand: die Bewegungsrate ist 0."),
    ])
    monkeypatch.setattr(adb, "standard_pfad", lambda: pfad)

    antwort = ns.foliant_hol_eintrag("regel", name="Gepackt halten")

    assert antwort.get("gefunden"), "Vorbedingung: die Regel muss gefunden werden"
    verwandte = antwort.get("verwandte_abschnitte") or []
    assert "Waffenloser Angriff" in verwandte, (
        f"der ausloesende Teil der Regel fehlt ({verwandte}) - genau der gemeldete Befund")
    assert "Gepackt" in verwandte
    assert "Gepackt halten" not in verwandte, "der Eintrag selbst gehoert nicht dazu"
    assert "B15" in antwort.get("hinweis_abschnitte", ""), \
        "ohne die Zusammensetz-Ansage bietet das Modell den Teil nur an"


def test_verweise_auf_kapitel_werden_nicht_als_abschnitt_ausgegeben(tmp_path, monkeypatch):
    """Die Gegenprobe, und sie zaehlt: Von 167 Verweisen im Bestand zeigen die meisten auf
    KAPITEL ("Playing the Game"), nicht auf Eintraege - und die deutschen 2014-Scans
    tragen an dieser Stelle OCR-Truemmer aus dem Index. Wuerden die mit ausgewiesen,
    schickte der Hinweis das Modell auf abrufbare Abschnitte, die es nicht gibt: ein
    Leerlauf, den der Spieler als Fehler sieht."""
    from app import db as adb
    from app.tools import nachschlagen as ns

    pfad = _regel_db(tmp_path, [
        ("Aktion", "Action", "Siehe auch_ „Die Spielregeln“ („Aktionen“).\n\nText."),
    ])
    monkeypatch.setattr(adb, "standard_pfad", lambda: pfad)

    antwort = ns.foliant_hol_eintrag("regel", name="Aktion")

    assert antwort.get("gefunden")
    assert not antwort.get("verwandte_abschnitte"), \
        "Kapitelnamen sind keine abrufbaren Eintraege"
    assert not antwort.get("hinweis_abschnitte")


def test_discord_zusatz_nennt_dasselbe_breitenbudget_wie_der_grader():
    """Prompt und Messung müssen DIESELBE Zahl tragen. Driften sie auseinander, wird der
    Bot an einer Regel gemessen, die ihm nie gesagt wurde — die teuerste Sorte
    Fehlalarm, weil sie wie ein Modellfehler aussieht.

    Anlass: Codeblöcke in echten Discord-Antworten waren 39–93 Zeichen breit (Median 51).
    Ein Codeblock bricht in Discord nicht um; am Handy — und am Tisch ist das Handy das
    Gerät — muss man breitere Tabellen seitwärts schieben."""
    import pathlib

    from evals.verhaltens_eval import CODEBLOCK_MAX_BREITE

    zusatz = pathlib.Path("config/discord_zusatz.md").read_text(encoding="utf-8")
    assert str(CODEBLOCK_MAX_BREITE) in zusatz, (
        f"Der Zusatz nennt das Budget {CODEBLOCK_MAX_BREITE} nicht - "
        f"gemessen wird dann etwas, das der Bot nie erfahren hat")
    assert "Codeblock-Zeilen" in zusatz


def test_discord_zusatz_verbietet_die_tabelle_bei_fliesstext_zellen():
    """Neun Waffeneigenschaften mit Beschreibung sind in KEINER Breite eine gute
    Tabelle. Der Zusatz erlaubte fette Feldzeilen längst - das Modell wählte die Tabelle,
    weil danach gefragt wurde. Jetzt steht die Grenze ausdrücklich da."""
    import pathlib

    zusatz = pathlib.Path("config/discord_zusatz.md").read_text(encoding="utf-8")
    assert "drei Spalten" in zusatz and "Feldzeile" in zusatz
