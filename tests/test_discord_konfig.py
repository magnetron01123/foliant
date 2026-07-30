"""Konfiguration des Bots aus der Umgebung: optionale Zahlen sind fail-soft. Ein
Tippfehler in der .env darf weder den Container ausknipsen noch eine Schranke still
auf 0 setzen - beides waere schlimmer als der Standardwert."""
from app.discord_bot.haupt import _zahl


def test_leer_und_fehlend_geben_den_standard(monkeypatch):
    monkeypatch.delenv("DISCORD_COOLDOWN_S", raising=False)
    assert _zahl("DISCORD_COOLDOWN_S", 10.0) == 10.0
    monkeypatch.setenv("DISCORD_COOLDOWN_S", "   ")
    assert _zahl("DISCORD_COOLDOWN_S", 10.0) == 10.0


def test_gueltige_werte_werden_uebernommen(monkeypatch):
    monkeypatch.setenv("DISCORD_COOLDOWN_S", "2.5")
    assert _zahl("DISCORD_COOLDOWN_S", 10.0) == 2.5
    monkeypatch.setenv("DISCORD_COOLDOWN_S", "0")       # bewusst aus: gilt
    assert _zahl("DISCORD_COOLDOWN_S", 10.0) == 0.0


def test_unsinn_und_negatives_fallen_auf_den_standard(monkeypatch):
    for roh in ("abc", "-5", "1,5"):                    # 1,5 ist deutsche Schreibweise
        monkeypatch.setenv("DISCORD_TAGESDECKEL", roh)
        assert _zahl("DISCORD_TAGESDECKEL", 100) == 100, roh
