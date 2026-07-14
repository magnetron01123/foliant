"""Web-Tests (Starlette TestClient): schmaler Upload-MVP, Sicherheit, Fehlermeldungen.

Nur synthetische Fixtures + FakeProvider (keine echte API, keine privaten Binärdateien).
"""
from __future__ import annotations

import sqlite3

import fitz
import pytest
from starlette.testclient import TestClient

from app.charakterbogen import web
from app.charakterbogen.uebersetzer import FakeProvider
from app.charakterbogen.web import KEIN_DDB, NICHT_PDF, NICHT_SICHER, _pruefe_sicher, erstelle_app
from tests.test_charakterbogen_ddb import BEISPIEL, baue_ddb_pdf


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
    app = erstelle_app(provider=FakeProvider(), glossar_pfad=str(gloss), template_pfad=str(vorlage))
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
