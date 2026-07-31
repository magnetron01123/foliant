"""app/llm.py - der geteilte Tool-Use-Loop (Eval + Discord-Bot). Der Loop hatte als
Eval-Innenleben nie eigene Tests; mit der Extraktion bekommt er sie: Skript-Antworten
per httpx.MockTransport, Fake-MCP-Client, keine echte API."""
import asyncio
import json

import httpx
import pytest

from app import llm


class _FakeInhalt:
    def __init__(self, text):
        self.text = text


class _FakeMcp:
    """call_tool-Attrappe: liefert Text oder wirft auf Kommando."""

    def __init__(self, antwort="TOOL-AUSGABE", werfen=False):
        self.antwort, self.werfen, self.aufrufe = antwort, werfen, []

    async def call_tool(self, name, argumente):
        self.aufrufe.append((name, argumente))
        if self.werfen:
            raise ValueError("kaputtes Argument")
        ergebnis = type("R", (), {})()
        ergebnis.content = [_FakeInhalt(self.antwort)]
        return ergebnis


def _http(antworten: list, mitschrift: list) -> httpx.AsyncClient:
    """Skriptierter API-Ersatz: jede Anfrage wird mitgeschrieben, Antworten der Reihe
    nach ausgeliefert (int = purer Statuscode, dict = 200-JSON)."""

    def handler(request):
        mitschrift.append(json.loads(request.content))
        naechste = antworten.pop(0)
        if isinstance(naechste, int):
            return httpx.Response(naechste, json={})
        return httpx.Response(200, json=naechste)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _endrunde(text="Fertige Antwort."):
    return {"stop_reason": "end_turn",
            "content": [{"type": "text", "text": text}]}


def _toolrunde(name="foliant_suche_bestand", eingabe=None):
    return {"stop_reason": "tool_use",
            "content": [{"type": "tool_use", "id": "tu_1", "name": name,
                         "input": eingabe or {"suchbegriff": "Feuerball"}}]}


def _fahre(antworten, mitschrift, mcp=None, **kwargs):
    async def lauf():
        async with _http(antworten, mitschrift) as http:
            return await llm.fahre_schleife(
                mcp or _FakeMcp(), http, "test-key", "test-modell", "SYSTEM",
                [{"name": "foliant_suche_bestand"}],
                [{"role": "user", "content": "Frage?"}], **kwargs)
    return asyncio.run(lauf())


def test_direkte_antwort_ohne_tools():
    mitschrift = []
    erg = _fahre([_endrunde()], mitschrift)
    assert erg.text == "Fertige Antwort." and erg.stop_grund == "end_turn"
    assert erg.tool_namen == [] and erg.bestandsauszuege == []
    assert mitschrift[0]["system"] == "SYSTEM"          # ohne Caching: purer String


def test_toolrunde_fuettert_ergebnis_zurueck():
    mitschrift = []
    mcp = _FakeMcp(antwort="8W6 Feuerschaden")
    erg = _fahre([_toolrunde(), _endrunde()], mitschrift, mcp=mcp)
    assert erg.tool_namen == ["foliant_suche_bestand"]
    assert erg.bestandsauszuege == ["[foliant_suche_bestand]\n8W6 Feuerschaden"]
    ergebnis_block = mitschrift[1]["messages"][-1]["content"][0]
    assert ergebnis_block["type"] == "tool_result"
    assert ergebnis_block["content"] == "8W6 Feuerschaden"
    assert ergebnis_block["is_error"] is False


def test_toolfehler_geht_als_is_error_zurueck_statt_zu_reissen():
    mitschrift = []
    erg = _fahre([_toolrunde(), _endrunde()], mitschrift, mcp=_FakeMcp(werfen=True))
    block = mitschrift[1]["messages"][-1]["content"][0]
    assert block["is_error"] is True and "ValueError" in block["content"]
    assert erg.stop_grund == "end_turn"                 # Lauf ueberlebt den Fehler
    assert erg.bestandsauszuege == []                   # Fehler sind kein Bestand


def test_runden_cap_ist_expliziter_stop_grund():
    """Der alte Eval-Loop gab beim Cap stumm '' zurueck - ein Bot braucht den Grund."""
    mitschrift = []
    erg = _fahre([_toolrunde(), _toolrunde(), _toolrunde()], mitschrift, max_runden=3)
    assert erg.stop_grund == "runden_cap" and erg.text == ""
    assert len(erg.tool_namen) == 3


def test_retry_bei_529_dann_erfolg(monkeypatch):
    schlaefe = []

    async def sofort(sekunden):
        schlaefe.append(sekunden)

    monkeypatch.setattr(llm.asyncio, "sleep", sofort)
    mitschrift = []
    erg = _fahre([529, _endrunde()], mitschrift)
    assert erg.text == "Fertige Antwort." and schlaefe == [5]


def test_harter_fehler_wirft_httpfehler(monkeypatch):
    async def sofort(_s):
        pass

    monkeypatch.setattr(llm.asyncio, "sleep", sofort)
    with pytest.raises(httpx.HTTPStatusError):
        _fahre([529, 529, 400], [])                      # 3. Versuch: harter 400


def test_kappungen_tool_result_und_auszug():
    mitschrift = []
    erg = _fahre([_toolrunde(), _endrunde()], mitschrift,
                 mcp=_FakeMcp(antwort="x" * 30_000))
    block = mitschrift[1]["messages"][-1]["content"][0]
    assert len(block["content"]) == 20_000
    assert len(erg.bestandsauszuege[0]) <= 6_000 + len("[foliant_suche_bestand]\n")


def test_system_cachen_erzeugt_blockform():
    mitschrift = []
    _fahre([_endrunde()], mitschrift, system_cachen=True)
    system = mitschrift[0]["system"]
    assert isinstance(system, list) and system[0]["text"] == "SYSTEM"
    assert system[0]["cache_control"] == {"type": "ephemeral"}


def test_verlauf_wird_nie_mutiert():
    verlauf = [{"role": "user", "content": "Frage?"}]

    async def lauf():
        async with _http([_toolrunde(), _endrunde()], []) as http:
            await llm.fahre_schleife(_FakeMcp(), http, "k", "m", "S", [], verlauf)

    asyncio.run(lauf())
    assert verlauf == [{"role": "user", "content": "Frage?"}]
