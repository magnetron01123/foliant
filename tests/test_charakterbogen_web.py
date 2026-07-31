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
    assert "ohne Foliant" in r.text                  # Vergleich mit/ohne MCP
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
        [("srd-de", "SRD 5.2.1 (Deutsch)", "de", "2024", "pdf", "CC-BY-4.0", 10,
          "regelwerk", "/geheim/pfad/srd.pdf"),
         ("rav-en", "Ravenloft (D&D Beyond)", "en", "2024", "ddb", "privat", 40,
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
    assert {q["titel"] for q in quellen} == {"SRD 5.2.1 (Deutsch)", "Ravenloft (D&D Beyond)"}
    html = web._bestand_html(quellen)
    assert "2 Büchern" in html and "3 Einträgen" in html
    # 3. Abenteuerbaende stehen getrennt, mit der Spoiler-Ansage (B6).
    assert "Abenteuer" in html and "Handlung" in html
    # 4. Einheitliche Zeile: Titel OHNE den Klammer-Zusatz, Sprache und Regelversion
    #    als eigene Angaben daneben - die Herkunft steht nicht doppelt im Titel.
    assert ">SRD 5.2.1<" in html and "(Deutsch)" not in html
    assert ">Ravenloft<" in html and "(D&D Beyond)" not in html
    assert "Regeln 2024" in html


def test_bestandsuebersicht_faellt_ohne_quellen_weg():
    """Aeltere Web-DB ohne die Tabelle: der Abschnitt entfaellt, die Seite bleibt heil."""
    from app.charakterbogen import web

    assert web._bestand_lesen(None) == []
    assert web._bestand_html([]) == ""


def test_buchtitel_verlieren_nur_die_doppelten_zusaetze():
    """Die Buchliste war uneinheitlich, weil jeder Importweg einen anderen Klammer-Zusatz
    an denselben Werktitel haengt. Entfernt wird deshalb NUR, was daneben ohnehin als
    eigene Angabe steht (Sprache, Regelversion, Bezugsweg) - ein echter Namenszusatz
    bleibt, sonst schneidet die Kosmetik Werktitel ab."""
    from app.charakterbogen.web import _titel_schlicht

    # Weg: Sprache, Regelversion, Bezugsweg - auch zwei Klammern hintereinander.
    assert _titel_schlicht("SRD 5.2.1 (Deutsch)") == "SRD 5.2.1"
    assert _titel_schlicht("Basic Rules (2014) (D&D Beyond)") == "Basic Rules"
    assert _titel_schlicht("Spielerhandbuch (Deutsch, 2014er Regeln)") == "Spielerhandbuch"
    assert _titel_schlicht("Eberron: Forge of the Artificer (Druck)") == \
        "Eberron: Forge of the Artificer"

    # Bleibt: alles, was zum Werknamen gehoert.
    assert _titel_schlicht("Monstrous Compendium Vol. 1 (Spelljammer Creatures)") == \
        "Monstrous Compendium Vol. 1 (Spelljammer Creatures)"
    assert _titel_schlicht("Curse of Strahd: Character Options") == \
        "Curse of Strahd: Character Options"
    # Ein Titel, der NUR aus dem Zusatz besteht, wird nicht zu einer leeren Zeile.
    assert _titel_schlicht("(Deutsch)") == "(Deutsch)"
    assert _titel_schlicht("") == ""
