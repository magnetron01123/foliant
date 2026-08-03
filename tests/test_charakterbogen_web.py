"""Web-Tests (Starlette TestClient): schmaler Upload-MVP, Sicherheit, Fehlermeldungen.

Nur synthetische Fixtures + FakeProvider (keine echte API, keine privaten Binärdateien).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import fitz
import pytest
from starlette.testclient import TestClient

from app.charakterbogen import web
from app.charakterbogen.uebersetzer import FakeProvider
from app.charakterbogen.web import (
    KEIN_DDB, KENNWORT_FALSCH, NICHT_PDF, NICHT_SICHER, ZU_VIELE_VERSUCHE,
    _pruefe_sicher, erstelle_app,
)
from tests.test_charakterbogen_ddb import BEISPIEL, baue_ddb_pdf
from tests.hilfen import SCHEMA


def _blank_pdf(seiten: int = 2) -> bytes:
    doc = fitz.open()
    for _ in range(seiten):
        doc.new_page(width=603, height=774)
    return doc.tobytes()


@pytest.fixture()
def client(tmp_path):
    # synthetische DE-Vorlage
    vorlage = tmp_path / "de.pdf"
    vorlage.write_bytes(_blank_pdf(2))
    # synthetisches Glossar (Datei, weil die Konvertierung im Threadpool neu verbindet)
    gloss = tmp_path / "glossar.sqlite"
    con = sqlite3.connect(gloss)
    con.execute("CREATE TABLE glossar (term_de TEXT, term_en TEXT, offiziell INT, "
                "quelle TEXT, edition_quelle TEXT, seite TEXT)")
    con.execute("INSERT INTO glossar VALUES ('Mönch','Monk',1,'Ulisses','2024','')")
    con.commit()
    con.close()
    app = erstelle_app(provider=FakeProvider(), glossar_pfad=str(gloss), template_pfad=str(vorlage),
                       passwort=KENNWORT)
    c = TestClient(app)
    c.post("/anmeldung", data={"kennwort": KENNWORT})     # angemeldet (Keks im Client)
    return c


KENNWORT = "geheim-der-runde"


@pytest.fixture()
def anonym(tmp_path):
    """Derselbe Aufbau, aber NICHT angemeldet."""
    vorlage = tmp_path / "de.pdf"
    vorlage.write_bytes(_blank_pdf(2))
    app = erstelle_app(provider=FakeProvider(), template_pfad=str(vorlage), passwort=KENNWORT)
    return TestClient(app)


# --- GET / -------------------------------------------------------------------

def test_startseite_ist_schmaler_mvp(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Deutschen Charakterbogen erstellen" in r.text
    assert 'type="file"' in r.text and r.text.count("<button") == 1
    assert r.headers["cache-control"] == "no-store"
    assert "noindex" in r.headers["x-robots-tag"]
    assert "default-src 'none'" in r.headers["content-security-policy"]


def test_health(client):
    assert client.get("/health").text == "ok"


# --- POST /bogen: Fehlerpfade ------------------------------------------------

def test_nicht_pdf_wird_abgelehnt(client):
    r = client.post("/bogen", files={"datei": ("x.txt", b"kein pdf", "text/plain")})
    assert r.status_code == 400 and NICHT_PDF in r.text


def test_gueltige_nicht_ddb_pdf_wird_abgelehnt(client):
    r = client.post("/bogen", files={"datei": ("x.pdf", _blank_pdf(2), "application/pdf")})
    assert r.status_code == 422 and KEIN_DDB in r.text


def test_fehlendes_dateifeld(client):
    r = client.post("/bogen", data={"foo": "bar"})
    assert r.status_code == 400 and NICHT_PDF in r.text


# --- POST /bogen: Erfolg -----------------------------------------------------

def test_gueltiger_ddb_export_liefert_pdf(client):
    ddb = baue_ddb_pdf(BEISPIEL)
    r = client.post("/bogen", files={"datei": ("held.pdf", ddb, "application/pdf")})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/pdf")
    assert r.content.startswith(b"%PDF")
    assert "attachment" in r.headers["content-disposition"]
    assert "-deutsch.pdf" in r.headers["content-disposition"]
    assert r.headers["cache-control"] == "no-store"


def test_dateiname_aus_charaktername(client):
    ddb = baue_ddb_pdf(BEISPIEL)  # CharacterName = "Testheld"
    r = client.post("/bogen", files={"datei": ("egal.pdf", ddb, "application/pdf")})
    assert "Testheld-deutsch.pdf" in r.headers["content-disposition"]


# --- Sicherheitsprüfung (Unit) ----------------------------------------------

def test_pruefe_sicher_akzeptiert_normale_pdf():
    assert _pruefe_sicher(_blank_pdf(2)) is None


def test_pruefe_sicher_lehnt_nicht_pdf_ab():
    assert _pruefe_sicher(b"das ist kein pdf") == NICHT_PDF


def test_pruefe_sicher_lehnt_uebergroesse_ab():
    riesig = b"%PDF" + b"\x00" * (web.MAX_BYTES + 1)
    assert _pruefe_sicher(riesig) == NICHT_SICHER


def test_pruefe_sicher_lehnt_verschluesselte_ab():
    doc = fitz.open()
    doc.new_page(width=603, height=774)
    verschluesselt = doc.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="o", user_pw="u")
    assert _pruefe_sicher(verschluesselt) == NICHT_SICHER


def test_pruefe_sicher_lehnt_zu_viele_seiten_ab():
    assert _pruefe_sicher(_blank_pdf(web.MAX_SEITEN + 1)) == NICHT_SICHER


# --- Zugang: EIN Kennwort, kein Benutzername ---------------------------------

def test_ohne_kennwort_keine_website(anonym):
    r = anonym.get("/")
    assert r.status_code == 401
    assert "Kennwort" in r.text
    assert "Deutschen Charakterbogen erstellen" not in r.text     # Upload-Formular bleibt verborgen
    assert 'name="benutzer"' not in r.text                        # KEIN Benutzerfeld
    assert "www-authenticate" not in {k.lower() for k in r.headers}  # kein Browser-Dialog


def test_ohne_kennwort_keine_konvertierung(anonym):
    """Wichtigster Test: die teure Route ist zu, nicht nur die Seite versteckt."""
    r = anonym.post("/bogen", files={"datei": ("held.pdf", baue_ddb_pdf(BEISPIEL), "application/pdf")})
    assert r.status_code == 401
    assert not r.content.startswith(b"%PDF")


def test_falsches_kennwort(anonym):
    r = anonym.post("/anmeldung", data={"kennwort": "falsch"})
    assert r.status_code == 401 and KENNWORT_FALSCH in r.text


def test_richtiges_kennwort_oeffnet_die_seite(anonym):
    r = anonym.post("/anmeldung", data={"kennwort": KENNWORT}, follow_redirects=True)
    assert r.status_code == 200 and "Deutschen Charakterbogen erstellen" in r.text
    assert anonym.get("/").status_code == 200                     # Keks haelt


def test_zu_viele_fehlversuche_werden_gebremst(anonym):
    web._fehlversuche.clear()
    for _ in range(web.MAX_VERSUCHE):
        anonym.post("/anmeldung", data={"kennwort": "falsch"})
    r = anonym.post("/anmeldung", data={"kennwort": "falsch"})
    assert r.status_code == 429 and ZU_VIELE_VERSUCHE in r.text
    # ... und selbst das RICHTIGE Kennwort ist waehrend der Sperre blockiert:
    assert anonym.post("/anmeldung", data={"kennwort": KENNWORT}).status_code == 429
    web._fehlversuche.clear()


def test_gefaelschter_keks_wird_abgewiesen(anonym):
    anonym.cookies.set(web.KEKS, "99999999999.deadbeef")
    assert anonym.get("/").status_code == 401


def test_ohne_gesetztes_kennwort_ist_die_seite_zu(tmp_path):
    """Fail-closed: kein WEB_PASSWORT -> niemals versehentlich offen im Netz."""
    app = erstelle_app(provider=FakeProvider(), passwort=None)
    c = TestClient(app)
    assert c.get("/").status_code == 503
    assert c.post("/bogen", files={"datei": ("x.pdf", _blank_pdf(2), "application/pdf")}).status_code == 401


# --- MCP-Abschnitt (eigener Inhaltspunkt, Link nur hinter dem Login) ----------

MCP_URL_TEST = "https://beispiel.invalid/geheimer-pfad/mcp"


def _app_mit_mcp(tmp_path, mcp_url):
    vorlage = tmp_path / "de.pdf"
    vorlage.write_bytes(_blank_pdf(2))
    app = erstelle_app(provider=FakeProvider(), template_pfad=str(vorlage),
                       passwort=KENNWORT, mcp_url=mcp_url)
    return TestClient(app)


def test_mcp_link_erscheint_nur_hinter_dem_login(tmp_path):
    c = _app_mit_mcp(tmp_path, MCP_URL_TEST)
    r = c.get("/")                                   # nicht angemeldet -> Anmeldeseite
    assert r.status_code == 401
    assert MCP_URL_TEST not in r.text                # Geheimpfad NIE vor dem Login
    c.post("/anmeldung", data={"kennwort": KENNWORT})
    r = c.get("/")
    assert r.status_code == 200
    assert MCP_URL_TEST in r.text                    # kopierbares Feld mit dem Link
    assert "Foliant im Claude-Chat" in r.text        # eigener Inhaltspunkt
    assert "Kopieren" in r.text
    # B10 (Custom Connectors sind Beta): ein Ausweg muss dastehen, sonst steht ein Spieler
    # bei einem verschwundenen Connector ohne alles da. Geprueft wird die ZUSAGE, nicht der
    # Wortlaut - der Vergleichskasten "mit/ohne Foliant" stand hier mal und ist bewusst
    # gestrichen (03.08.2026, Eigentuemer-Wunsch: so viel wie noetig, so wenig wie moeglich).
    assert "Beta" in r.text and "Discord" in r.text
    assert "{{MCP_URL}}" not in r.text               # Platzhalter vollständig ersetzt


def test_projektanweisung_steht_kopierbereit_auf_der_seite(tmp_path):
    """Der GEMEINSAME Ort fuer die Runde: mehrere Spieler richten je ein eigenes
    Claude-Projekt ein und brauchen denselben aktuellen Anweisungstext. Er kommt zur
    Laufzeit aus config/projektanweisung.md - eine Kopie im Template wuerde veralten."""
    from config import stil

    c = _app_mit_mcp(tmp_path, MCP_URL_TEST)
    r = c.get("/")
    assert MCP_URL_TEST not in r.text                # vor dem Login gar nichts
    assert "Projektanweisung" not in r.text
    c.post("/anmeldung", data={"kennwort": KENNWORT})
    r = c.get("/")
    assert r.status_code == 200
    assert "{{PROJEKTANWEISUNG}}" not in r.text      # Platzhalter ersetzt
    assert 'id="anweisung"' in r.text and 'data-kopieren="anweisung"' in r.text
    anweisung = stil.projektanweisung()
    assert anweisung and len(anweisung) > 2000
    # Inhalt tatsaechlich da (und HTML-escaped: das Original enthaelt Anfuehrungszeichen):
    assert "Du hilfst unserer D&amp;D-Runde" in r.text
    assert "KEINE SPOILER" in r.text
    assert "Projektanweisungen" in r.text            # Wegbeschreibung fuer die Spieler


def test_projektanweisung_faellt_ohne_mcp_link_weg(client):
    """Ohne hinterlegten Connector-Link ist nichts einzurichten - dann zeigt die Seite
    auch keinen Anweisungs-Schritt (und bleibt der schmale Upload-MVP)."""
    r = client.get("/")
    assert r.status_code == 200
    assert 'id="anweisung"' not in r.text
    assert "{{PROJEKTANWEISUNG}}" not in r.text


def test_projektanweisung_ohne_spec_block_laesst_seite_heil(tmp_path, monkeypatch):
    """Fehlt SPEC.md (z. B. nicht im Image), verschwindet der Abschnitt - eine leere
    Textarea wuerde als 'es gibt keine Regeln' gelesen."""
    from config import stil
    monkeypatch.setattr(stil, "projektanweisung", lambda: None)
    c = _app_mit_mcp(tmp_path, MCP_URL_TEST)
    c.post("/anmeldung", data={"kennwort": KENNWORT})
    r = c.get("/")
    assert r.status_code == 200
    assert MCP_URL_TEST in r.text                    # der Link bleibt nutzbar
    assert 'id="anweisung"' not in r.text and "{{PROJEKTANWEISUNG}}" not in r.text


def test_mcp_ohne_url_zeigt_hinweis_statt_leerem_feld(client):
    from app.charakterbogen.web import MCP_FEHLT
    r = client.get("/")
    assert r.status_code == 200
    assert MCP_FEHLT in r.text                       # fail-soft: Erklärung bleibt, Feld weg
    assert 'id="mcp-url"' not in r.text
    assert "{{MCP_URL}}" not in r.text


def test_mcp_url_aus_env_zusammengesetzt(monkeypatch):
    from app.charakterbogen.web import _mcp_url_aus_env
    monkeypatch.delenv("FOLIANT_MCP_URL", raising=False)
    monkeypatch.setenv("FOLIANT_PFAD_TOKEN", "abc123")
    monkeypatch.setenv("FOLIANT_BASIS_URL", "https://beispiel.invalid/")
    assert _mcp_url_aus_env() == "https://beispiel.invalid/abc123/mcp"
    monkeypatch.setenv("FOLIANT_MCP_URL", "https://direkt.invalid/x/mcp")
    assert _mcp_url_aus_env() == "https://direkt.invalid/x/mcp"   # explizite URL gewinnt
    monkeypatch.delenv("FOLIANT_MCP_URL", raising=False)
    monkeypatch.delenv("FOLIANT_PFAD_TOKEN", raising=False)
    assert _mcp_url_aus_env() is None                              # ohne Token -> Hinweis


def test_credit_zeile_auf_der_seite(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "David Trogemann" in r.text            # Urheber-Credit im Fuß
    assert "©" in r.text and "für Nerds" in r.text


def test_discord_abschnitt_erklaert_den_bot(client):
    """Der Bot ist der zweite Weg in denselben Bestand, stand aber nirgends auf der Seite.
    Die Runde soll ohne Rueckfrage wissen, wie sie ihn anspricht - und dass Discord die
    Antworten dauerhaft im Kanal stehen laesst (SPEC par. 12)."""
    r = client.get("/")
    assert 'id="discord"' in r.text
    assert 'href="#discord"' in r.text                    # im Seitenkopf verlinkt
    assert "/regel" in r.text and "/regel-privat" in r.text
    assert "/hilfe" in r.text                             # der eine Befehl zum Merken
    # Die PERSISTENZ-Zusage, nicht ihr Wortlaut: Discord laesst Antworten dauerhaft im
    # Kanal stehen, und der Spieler muss den privaten Weg kennen. Vorher pinnte dieser
    # Test einen ganzen Satz - und schlug bei jeder Kuerzung der Seite fehl, obwohl die
    # Aussage noch dastand.
    assert "lesbar" in r.text and "/regel-privat" in r.text


def test_bestandsuebersicht_zeigt_die_buecher(tmp_path):
    """Die Runde soll nachschauen koennen, was im Bestand steht, statt zu raten - und die
    Zahl soll nicht im Template gepflegt werden muessen (dort stand am 30.07.2026 'rund
    9.500', waehrend es 12.503 waren).

    Geprueft wird die GRENZE mit: in die Web-DB gehen nur Metadaten. Buchtext und
    Dateipfade bleiben draussen (SPEC.md par. 14) - das ist der Grund, warum der
    web-Container die volle DB nicht sieht."""
    import sqlite3

    from app.charakterbogen import glossar_export, web

    korpus = tmp_path / "korpus.sqlite"
    con = sqlite3.connect(korpus)
    con.executescript(SCHEMA
                      .read_text(encoding="utf-8"))
    con.executemany(
        "INSERT INTO quellen (kuerzel,titel,sprache,edition,herkunft,lizenz,prioritaet,"
        "inhaltsart,dateipfad) VALUES (?,?,?,?,?,?,?,?,?)",
        # Titel nach dem Beschriftungs-Standard (importer/quellen.py): nur der Werktitel.
        [("srd-de", "SRD 5.2.1", "de", "2024", "pdf", "CC-BY-4.0", 10,
          "regelwerk", "/geheim/pfad/srd.pdf"),
         ("rav-en", "Ravenloft", "en", "2024", "ddb", "privat", 40,
          "abenteuer_setting", "/geheim/pfad/rav.pdf")])
    con.executemany(
        "INSERT INTO eintraege (quelle_id,kategorie,name_de,name_en,sprache,edition,"
        "body_md) VALUES (?,?,?,?,?,?,?)",
        [(1, "zauber", "Feuerball", None, "de", "2024", "Geheimer Regeltext."),
         (1, "zauber", "Licht", None, "de", "2024", "Noch ein Regeltext."),
         (2, "monster", None, "Strahd", "en", "2024", "SPOILER: Strahds Schwaeche ist ...")])
    con.commit()
    con.close()

    web_db = tmp_path / "web.sqlite"
    glossar_export.exportiere(str(korpus), str(web_db))

    # 1. Die Grenze: kein Buchtext, kein Dateipfad in der Web-DB.
    roh = web_db.read_bytes()
    assert b"SPOILER" not in roh and b"Geheimer Regeltext" not in roh
    assert b"/geheim/pfad" not in roh
    spalten = {r[1] for r in sqlite3.connect(web_db).execute("PRAGMA table_info(quellen)")}
    assert "dateipfad" not in spalten

    # 2. Die Anzeige: beide Buecher, mit Zahlen aus dem Bestand.
    quellen = web._bestand_lesen(str(web_db))
    assert {q["titel"] for q in quellen} == {"SRD 5.2.1", "Ravenloft"}
    html = web._bestand_html(quellen)
    assert "2 Büchern" in html and "3 Einträgen" in html
    # 3. Abenteuerbaende stehen getrennt, mit der Spoiler-Ansage (B6).
    assert "Abenteuer" in html and "Handlung" in html
    # 4. Jede Zeile beantwortet dieselben drei Fragen in eigenen, benannten Spalten -
    #    der Titel traegt keine davon doppelt.
    assert ">SRD 5.2.1<" in html and ">Ravenloft<" in html
    assert ">Buch<" in html and ">Sprache<" in html and ">Regelstand<" in html
    assert ">Deutsch<" in html and ">Englisch<" in html
    assert ">Regeln 2024<" in html


def test_bestandsuebersicht_zeigt_jede_angabe_genau_einmal():
    """Der Beschriftungs-Standard sichtbar gemacht: Sprache und Regelstand stehen in
    eigenen Spalten, NICHT im Titel. Die Liste war vorher nicht vergleichbar, weil jeder
    Importweg diese Angaben anders in den Titel klammerte - taucht so ein Zusatz wieder
    auf, ist der Standard umgangen worden."""
    from app.charakterbogen import web

    html = web._bestand_html([
        {"titel": "Player’s Handbook", "sprache": "en", "edition": "2024",
         "herkunft": "ddb", "inhaltsart": "regelwerk", "eintraege": 1581},
        {"titel": "Spielerhandbuch", "sprache": "de", "edition": "2014",
         "herkunft": "pdf", "inhaltsart": "regelwerk", "eintraege": 1539},
    ])
    for zusatz in ("(Deutsch)", "(Englisch)", "(D&amp;D Beyond)", "(2014)", "(Druck)"):
        assert zusatz not in html
    # Beide Zeilen tragen dieselben Marken in derselben Reihenfolge.
    assert html.count('class="sprache"') == html.count('class="regelstand"') == 3  # 2 + Kopf
    assert ">Regeln 2014<" in html and ">Regeln 2024<" in html


def test_beide_srd_fassungen_stehen_unter_denselben_regelwerken():
    """Ein Zwischenstand schnitt die dritte Gruppe nach BEZUGSWEG - und trennte damit die
    beiden Fassungen desselben Werks: die deutsche SRD-Fassung stand unter den
    Regelwerken, die englische darunter bei den 'weiteren Quellen', nur weil sie über
    eine Schnittstelle geladen wurde. Ob eine Regel als PDF oder über eine API hereinkam,
    ist eine Betriebsfrage - keine, nach der eine Liste für Spieler gliedert."""
    from app.charakterbogen import web

    html = web._bestand_html([
        {"titel": "System Reference Document 5.2.1", "sprache": "de", "edition": "2024",
         "herkunft": "pdf", "inhaltsart": "regelwerk", "eintraege": 1619},
        {"titel": "System Reference Document 5.2", "sprache": "en", "edition": "2024",
         "herkunft": "open5e", "inhaltsart": "regelwerk", "eintraege": 982},
        {"titel": "Ravenloft", "sprache": "en", "edition": "2024",
         "herkunft": "ddb", "inhaltsart": "abenteuer_setting", "eintraege": 792},
    ])
    regelwerke = html.split("<h3>Regelwerke</h3>")[1].split("<h3>")[0]
    assert ">System Reference Document 5.2.1<" in regelwerke
    assert ">System Reference Document 5.2<" in regelwerke
    assert "<h3>Abenteuer &amp; Settings</h3>" in html
    assert "3 Büchern" in html


def test_weitere_quellen_zeigen_woher_das_deutsch_kommt():
    """Der Gliederungspunkt, der vorher fehlte. Das Glossar entscheidet, wie Foliant eine
    Regel BENENNT - es stand aber nirgends auf der Seite, weil es in `glossar` liegt und
    nicht in `quellen`. Getrennt ausgewiesen wird, was von dnddeutsch.de übernommen ist
    und was Foliant selbst am Bestand belegt hat: alles als 'dnddeutsch.de' auszuweisen,
    wäre eine falsche Zuschreibung."""
    from app.charakterbogen import web

    quellen = [{"titel": "Spielerhandbuch", "sprache": "de", "edition": "2014",
                "herkunft": "pdf", "inhaltsart": "regelwerk", "eintraege": 1539}]
    ohne = web._bestand_html(quellen)
    assert "Deutsche Begriffe" not in ohne        # keine Glossardaten -> keine Gruppe

    mit = web._bestand_html(quellen, [
        {"titel": "dnddeutsch.de", "marke_a": "Begriffsdatenbank", "marke_b": "",
         "zahl": 2520},
        {"titel": "Abgleich im eigenen Bestand", "marke_a": "aus den Büchern belegt",
         "marke_b": "", "zahl": 652},
    ])
    assert "<h3>Deutsche Begriffe</h3>" in mit
    assert ">dnddeutsch.de<" in mit and "2.520" in mit
    assert ">Abgleich im eigenen Bestand<" in mit and "652" in mit
    # Eigene Spaltennamen - "Buch" und "Regelstand" passen auf Begriffspaare nicht.
    herkunft = mit.split("<h3>Deutsche Begriffe</h3>")[1]
    assert ">Quelle<" in herkunft and ">Begriffspaare<" in herkunft
    assert "Regelstand" not in herkunft
    # Und eine eigene Spaltenbreite, sonst laufen die langen Marken aus ihrer Spalte.
    assert 'class="buecher herkunft"' in mit


def test_bestandsuebersicht_faellt_ohne_quellen_weg():
    """Aeltere Web-DB ohne die Tabelle: der Abschnitt entfaellt, die Seite bleibt heil."""
    from app.charakterbogen import web

    assert web._bestand_lesen(None) == []
    assert web._bestand_html([]) == ""


def test_buchliste_folgt_der_web_db_ohne_neustart(tmp_path):
    """Die Seite sagt über der Buchliste wörtlich "sie ist immer aktuell".

    Bis zum 31.07.2026 wurde sie EINMAL beim Containerstart gebaut: `admin import`
    frischte die Web-DB auf, der laufende Container zeigte aber bis zum nächsten
    `docker compose restart web` den alten Stand - und behauptete dabei Aktualität.
    Der Test schreibt in die Web-DB, NACHDEM die App gebaut wurde."""
    from starlette.testclient import TestClient
    from app.charakterbogen import web as w

    web_db = tmp_path / "glossar_web.sqlite"
    con = sqlite3.connect(web_db)
    con.executescript(
        "CREATE TABLE glossar (term_en TEXT, term_de TEXT, offiziell INT, quelle TEXT,"
        " edition_quelle TEXT, seite TEXT);"
        "CREATE TABLE quellen (kuerzel TEXT, titel TEXT, sprache TEXT, edition TEXT,"
        " herkunft TEXT, lizenz TEXT, inhaltsart TEXT, eintraege INTEGER);")
    con.execute("INSERT INTO quellen VALUES ('srd-de','SRD 5.2.1 (Deutsch)','de','2024',"
                "'pdf','CC-BY-4.0','regelwerk',3000)")
    con.commit()

    app = w.erstelle_app(glossar_pfad=str(web_db), passwort="geheim")
    client = TestClient(app)
    client.post("/anmeldung", data={"kennwort": "geheim"})
    assert "SRD 5.2.1" in client.get("/").text

    # Neues Buch NACH dem App-Bau - so wie `admin import` es tut.
    con.execute("INSERT INTO quellen VALUES ('phb-2024-de','Spielerhandbuch 2024','de',"
                "'2024','pdf','privat','regelwerk',1500)")
    con.commit()
    con.close()

    assert "Spielerhandbuch 2024" in client.get("/").text, (
        "Die Buchliste haengt am Containerstart - die Seite behauptet Aktualitaet, "
        "die sie nicht hat")


def test_balkenbreite_kommt_ohne_inline_stil_aus():
    """Die Balken waren im Betrieb IMMER durchgezogen, lokal aber richtig proportional
    (gemeldet 31.07.2026). Ursache: die Seite liefert `style-src 'self'` aus, und darunter
    verwirft der Browser jedes Inline-`style`-Attribut - der Balken fiel auf seine
    Vorgabebreite (100 %) zurück. Lokal fiel das nie auf, weil die Vorschau ohne CSP
    ausliefert. Die Breite kommt deshalb als Klasse aus der externen Datei.

    Der Test prüft beides: keinen Inline-Stil in der Ausgabe UND dass die Klasse, die
    dort steht, in site.css auch wirklich definiert ist."""
    import re
    from pathlib import Path

    from app.charakterbogen import web

    html = web._bestand_html([
        {"titel": "Groß", "sprache": "de", "edition": "2024", "herkunft": "pdf",
         "inhaltsart": "regelwerk", "eintraege": 2000},
        {"titel": "Klein", "sprache": "de", "edition": "2024", "herkunft": "pdf",
         "inhaltsart": "regelwerk", "eintraege": 20},
    ])
    assert "style=" not in html, "Inline-Stil - unter der CSP der Seite wirkungslos"
    klassen = re.findall(r'<span class="(b\d+)">', html)
    assert klassen == ["b50", "b1"], klassen          # 2000 -> voll, 20 -> Mindestbreite

    css = (Path("app/charakterbogen/static") / "site.css").read_text(encoding="utf-8")
    for k in set(klassen):
        assert f".{k}{{width:" in css, f"Breitenklasse .{k} fehlt in site.css"


def test_die_csp_erlaubt_keine_inline_stile():
    """Die Gegenprobe zum Test darüber: würde jemand 'unsafe-inline' in die CSP
    aufnehmen, um einen Inline-Stil wirken zu lassen, wäre der Balken zwar richtig - die
    Seite hätte dafür aber ihre Stil-Schranke für ALLES aufgegeben."""
    from app.charakterbogen.web import _HTML_HEADER

    csp = _HTML_HEADER["Content-Security-Policy"]
    assert "style-src 'self'" in csp and "unsafe-inline" not in csp


def test_buchliste_ueberlebt_eine_aeltere_web_db(tmp_path):
    """Die Web-DB wird von aussen erneuert und migriert NICHT mit dem Code: nach einem
    Deploy kann der neue Code auf eine alte Datei treffen.

    Beim Zuwachs um `versions_stand` (31.07.2026) sprengte eine feste Spaltenliste im
    SELECT genau dort die Abfrage - und der Rueckfall verschluckte daraufhin die
    KOMPLETTE Buchliste statt nur des fehlenden Feldes. Die Seite behauptet ueber dieser
    Liste woertlich, sie sei "immer aktuell"; sie stattdessen ganz wegfallen zu lassen,
    ist der schlechteste aller Ausgaenge."""
    from starlette.testclient import TestClient
    from app.charakterbogen import web as w

    web_db = tmp_path / "alt_glossar_web.sqlite"
    con = sqlite3.connect(web_db)
    con.executescript(
        "CREATE TABLE glossar (term_en TEXT, term_de TEXT, offiziell INT, quelle TEXT,"
        " edition_quelle TEXT, seite TEXT);"
        # Ohne `versions_stand` - der Stand VOR dem Schema-Zuwachs.
        "CREATE TABLE quellen (kuerzel TEXT, titel TEXT, sprache TEXT, edition TEXT,"
        " herkunft TEXT, lizenz TEXT, inhaltsart TEXT, eintraege INTEGER);")
    con.execute("INSERT INTO quellen VALUES ('srd-de','SRD 5.2.1','de','2024',"
                "'pdf','CC-BY-4.0','regelwerk',3000)")
    con.commit()
    con.close()

    app = w.erstelle_app(glossar_pfad=str(web_db), passwort="geheim")
    client = TestClient(app)
    client.post("/anmeldung", data={"kennwort": "geheim"})
    seite = client.get("/").text
    assert "SRD 5.2.1" in seite            # die Liste steht, trotz fehlender Spalte
    assert "Regeln 2024" in seite          # und die Regelstand-Marke auch
