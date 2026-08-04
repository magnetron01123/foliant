"""Der Discord-API-Helfer (deploy/discord_api.py) - Format- und Argumentebene, ohne Netz.

Geprueft wird genau das, was ohne Discord pruefbar ist und trotzdem brechen kann: die
Argumentwahl, das Ausgabeformat und - am wichtigsten - die Zusage, dass der
Auswertungsweg KEINE Nutzerkennung ausgibt (CONCEPT.md par. 13). Der HTTP-Teil bleibt
ungetestet; er haengt an einer fremden API und wird beim Einrichten manuell abgenommen.
"""
from __future__ import annotations

import importlib.util
import pathlib

import pytest

_PFAD = pathlib.Path(__file__).resolve().parents[1] / "deploy" / "discord_api.py"
_spec = importlib.util.spec_from_file_location("discord_api", _PFAD)
discord_api = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(discord_api)


# --- Ausgabeformat --------------------------------------------------------------------

def test_zeilenumbrueche_werden_escapt():
    """Eine Bot-Antwort ist mehrzeilig, das Format zeilenweise - ohne Escaping zerfiele
    eine Nachricht in scheinbar mehrere und der Auswerter zaehlte falsch."""
    assert discord_api._eine_zeile("a\nb") == "a\\nb"
    assert discord_api._eine_zeile("a\tb") == "a b"
    assert discord_api._eine_zeile(None) == ""


def test_backslash_wird_vor_dem_umbruch_escapt():
    """Sonst waere ein echtes '\\n' im Text nicht von einem escapten Umbruch zu
    unterscheiden."""
    assert discord_api._eine_zeile("a\\nb") == "a\\\\nb"


def test_kontext_nennt_keine_nutzerkennung(monkeypatch, capsys):
    """Die harte Zusage: Der Auswertungsweg gibt `bot|mensch` aus - nie einen Namen und
    nie eine ID. Ein Autorname hier waere genau das Sozialprotokoll, das das
    Rueckmeldungs-Protokoll bewusst nicht fuehrt."""
    monkeypatch.setattr(discord_api, "hole", lambda pfad, token: [
        {"id": "20", "author": {"bot": True, "username": "Foliant", "id": "999"},
         "content": "Antwort\nmit Umbruch"},
        {"id": "10", "author": {"username": "magnetron", "id": "111"},
         "content": "Die Frage?"},
    ])
    discord_api.nachrichten("1", "2", "token")
    ausgabe = capsys.readouterr().out
    assert ausgabe == ("10\tmensch\tDie Frage?\n"
                       "20\tbot\tAntwort\\nmit Umbruch\n")
    for verraeterisch in ("magnetron", "Foliant", "111", "999"):
        assert verraeterisch not in ausgabe, verraeterisch


def test_kontext_kommt_chronologisch(monkeypatch, capsys):
    """Discord liefert neueste zuerst. Ein Gespraech rueckwaerts zu lesen, dreht Frage
    und Antwort um - und genau die Zuordnung ist der Zweck des Abrufs."""
    monkeypatch.setattr(discord_api, "hole", lambda pfad, token: [
        {"id": "300", "author": {"bot": True}, "content": "spaeter"},
        {"id": "100", "author": {}, "content": "frueher"},
        {"id": "200", "author": {"bot": True}, "content": "mitte"},
    ])
    discord_api.nachrichten("1", "2", "token")
    assert [z.split("\t")[2] for z in capsys.readouterr().out.splitlines()] \
        == ["frueher", "mitte", "spaeter"]


# --- Argumentebene --------------------------------------------------------------------

@pytest.mark.parametrize("argv", [
    ["discord_api.py"],
    ["discord_api.py", "unbekannt"],
    ["discord_api.py", "nachrichten"],                    # ohne IDs
    ["discord_api.py", "nachrichten", "nur-kanal"],       # ohne Nachricht
    ["discord_api.py", "guilds", "zuviel"],
])
def test_falscher_aufruf_endet_mit_hinweis(argv, monkeypatch, capsys):
    monkeypatch.setattr(discord_api.sys, "argv", argv)
    with pytest.raises(SystemExit) as ende:
        discord_api.main()
    assert ende.value.code == 1
    assert "Aufruf:" in capsys.readouterr().err


def test_ohne_token_bricht_es_ab(monkeypatch, capsys):
    """Ein fehlender Token darf nicht in einen 401 laufen, der wie ein abgelaufener
    aussieht - die Meldung soll sagen, WAS fehlt."""
    monkeypatch.setattr(discord_api.sys, "argv",
                        ["discord_api.py", "nachrichten", "1", "2"])
    monkeypatch.setattr(discord_api.sys.stdin, "isatty", lambda: True)
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    with pytest.raises(SystemExit) as ende:
        discord_api.main()
    assert ende.value.code == 1
    assert "DISCORD_BOT_TOKEN" in capsys.readouterr().err


def test_token_aus_der_umgebung_traegt_den_auswertungsweg(monkeypatch):
    """Im discord-Container ist die Variable ohnehin gesetzt. Die Haertung bleibt: der
    Token steht in keiner Kommandozeile, nur der Weg dorthin ist ein zweiter."""
    monkeypatch.setattr(discord_api.sys, "argv",
                        ["discord_api.py", "nachrichten", "1", "2"])
    monkeypatch.setattr(discord_api.sys.stdin, "isatty", lambda: True)
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "geheim")
    gesehen = {}
    monkeypatch.setattr(discord_api, "hole",
                        lambda pfad, token: gesehen.update(pfad=pfad, token=token) or [])
    discord_api.main()
    assert gesehen["token"] == "geheim"
    assert gesehen["pfad"] == "/channels/1/messages?around=2&limit=8"
