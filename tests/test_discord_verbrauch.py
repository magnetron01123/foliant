"""Die Token-Abrechnung im Antwortweg des Bots (app/discord_bot/bot.py).

Die Zahlen sind die EINZIGE Auskunft darueber, ob das Prompt-Caching greift: ein
verfehlter Cache meldet sich nirgends sonst, er kostet nur still den vollen Preis.
Genau deshalb muss die Log-Zeile geprueft werden - sie laeuft im Betrieb durch einen
Pfad, den kein anderer Test beruehrt, und ein Formatfehler dort faellt sonst erst auf,
wenn man die Zahlen braucht und keine hat. logging formatiert traege: eine falsche
Platzhalterzahl wirft nicht, sie verschluckt die Meldung.
"""
from __future__ import annotations

import asyncio
import logging

from app import llm
from app.discord_bot.bot import FoliantBot


def _bot() -> FoliantBot:
    return FoliantBot(guild_id=1, kanal_ids=frozenset(), tagesdeckel=100,
                      api_key="x", modell="x", system="x")


ANTWORT = "Eine Antwort mit ein paar Zeichen."


def _ergebnis(verbrauch: llm.Verbrauch) -> llm.SchleifenErgebnis:
    return llm.SchleifenErgebnis(ANTWORT, [], [], "end_turn", verbrauch)


def test_die_token_zahlen_landen_vollstaendig_im_log(monkeypatch, caplog):
    verbrauch = llm.Verbrauch(cache_gelesen=43_415, cache_geschrieben=0,
                              ungecacht=6, ausgabe=631)

    async def fake_schleife(*_a, **_k):
        return _ergebnis(verbrauch)

    monkeypatch.setattr(llm, "fahre_schleife", fake_schleife)
    with caplog.at_level(logging.INFO, logger="foliant.discord"):
        asyncio.run(_bot()._beantworte(42, "Feuerball?", []))

    zeilen = [r.getMessage() for r in caplog.records if "Tokens:" in r.getMessage()]
    assert len(zeilen) == 1, caplog.text
    zeile = zeilen[0]
    for zahl in ("43415", "631", "6"):
        assert zahl in zeile, zeile
    # Trefferquote 43415/(43415+0+6) = 99,99 % -> gerundet 100
    assert "100 %" in zeile, zeile
    # Die Antwortlaenge steht daneben, weil Sonnet 5 ohne 'thinking'-Feld adaptiv denkt:
    # liegt 'Ausgabe' weit ueber der Laenge, geht der Rest ins Denken - und teilt sich
    # max_tokens mit der Antwort.
    assert f"{len(ANTWORT)} Zeichen" in zeile, zeile


def test_ohne_treffer_meldet_das_log_null_prozent(monkeypatch, caplog):
    """Der Fall, den man sehen WILL: geschrieben, nie gelesen - dann stimmt am
    Praefix etwas nicht (zu kurz, instabil, oder die Frist ist abgelaufen)."""
    async def fake_schleife(*_a, **_k):
        return _ergebnis(llm.Verbrauch(cache_geschrieben=11_638, ungecacht=50,
                                       ausgabe=200))

    monkeypatch.setattr(llm, "fahre_schleife", fake_schleife)
    with caplog.at_level(logging.INFO, logger="foliant.discord"):
        asyncio.run(_bot()._beantworte(42, "Feuerball?", []))

    zeile = next(r.getMessage() for r in caplog.records if "Tokens:" in r.getMessage())
    assert "0 %" in zeile and "11638" in zeile, zeile


def test_der_antwortweg_ueberlebt_eine_antwort_ohne_text(monkeypatch, caplog):
    """len(erg.text) wuerde bei None reissen - und ein Absturz im Logging kostete
    die bereits BEZAHLTE Antwort, was die Zahlen erst recht wertlos machte."""
    async def fake_schleife(*_a, **_k):
        return llm.SchleifenErgebnis("", [], [], "runden_cap", llm.Verbrauch())

    monkeypatch.setattr(llm, "fahre_schleife", fake_schleife)
    with caplog.at_level(logging.INFO, logger="foliant.discord"):
        text = asyncio.run(_bot()._beantworte(42, "Feuerball?", []))

    assert text                                   # ehrliche Meldung statt Absturz
    assert any("Tokens:" in r.getMessage() for r in caplog.records)
