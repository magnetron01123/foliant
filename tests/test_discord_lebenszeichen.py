"""Lebenszeichen des Bots (D5, Review 19.09.2026).

Der Discord-Container war als einziger Dienst ohne Healthcheck - `docker ps` sagte auch
dann "Up", wenn die Gateway-Verbindung tot war. Am 11.08.2026 blieb genau so ein stiller
Meldeweg tagelang unbemerkt: Niemand meldet, dass das Melden nicht geht.
"""
from app.discord_bot import lebenszeichen as lz


def test_frisches_zeichen_ist_gesund(tmp_path):
    pfad = tmp_path / "lebt"
    assert lz.schreibe(pfad, jetzt=lambda: 1000) is True
    assert lz.ist_gesund(pfad, jetzt=lambda: 1000) is True
    assert lz.alter_s(pfad, jetzt=lambda: 1030) == 30


def test_veraltetes_zeichen_ist_ungesund(tmp_path):
    """Der Kernfall: Der Prozess lebt, die Gateway-Schleife nicht mehr. Drei verpasste
    Runden sind ein Ausfall - eine ist ein Hicks."""
    pfad = tmp_path / "lebt"
    lz.schreibe(pfad, jetzt=lambda: 1000)
    assert lz.ist_gesund(pfad, jetzt=lambda: 1000 + lz.MAX_ALTER_S) is True
    assert lz.ist_gesund(pfad, jetzt=lambda: 1000 + lz.MAX_ALTER_S + 1) is False


def test_fehlendes_zeichen_ist_ungesund(tmp_path):
    """Nach einem Neustart ist /tmp (tmpfs) leer - ein Altstand kann keine Gesundheit
    vortaeuschen. Bis das erste Zeichen da ist, deckt start_period den Fall ab."""
    assert lz.alter_s(tmp_path / "gibtsnicht") is None
    assert lz.ist_gesund(tmp_path / "gibtsnicht") is False


def test_unbrauchbarer_inhalt_ist_ungesund(tmp_path):
    pfad = tmp_path / "lebt"
    pfad.write_text("kein zeitstempel\n", encoding="utf-8")
    assert lz.ist_gesund(pfad) is False


def test_zeichen_aus_der_zukunft_ist_ungesund(tmp_path):
    """Eine verstellte Uhr darf kein Dauergruen erzeugen - negatives Alter faellt durch."""
    pfad = tmp_path / "lebt"
    lz.schreibe(pfad, jetzt=lambda: 5000)
    assert lz.ist_gesund(pfad, jetzt=lambda: 1000) is False


def test_schreiben_wirft_nie(tmp_path):
    """Ein Lebenszeichen, das den Bot mit in den Abgrund zieht, waere das Gegenteil von
    Ueberwachung - dieselbe Leitplanke wie beim Abfrage-Protokoll."""
    unbeschreibbar = tmp_path / "datei" / "lebt"
    (tmp_path / "datei").write_text("ich bin eine Datei, kein Verzeichnis")
    assert lz.schreibe(unbeschreibbar) is False
