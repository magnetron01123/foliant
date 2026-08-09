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
    erg = _fahre([_toolrunde(), _toolrunde(), _toolrunde(),
                  _endrunde("Aus dem Geholten:")], mitschrift, max_runden=3)
    assert erg.stop_grund == "runden_cap"
    assert len(erg.tool_namen) == 3


def test_runden_cap_erzwingt_noch_eine_antwort_ohne_werkzeuge():
    """Befund 07.08.2026 (Eval-Fall DC3, dreimal in Folge): Bei einer breiten Listenfrage
    braucht das Modell 12-28 Werkzeugaufrufe, reisst den Rundendeckel - und der Nutzer
    bekam nach acht Runden bezahlter Recherche eine LEERE Antwort.

    Die letzte Anfrage geht deshalb ohne 'tools' raus: Dann kann das Modell nur noch
    schreiben, und aus dem bereits Geholten wird eine - womoeglich unvollstaendige -
    Auskunft. Der Stop-Grund bleibt erhalten, der Bot weist weiterhin darauf hin."""
    mitschrift = []
    erg = _fahre([_toolrunde(), _toolrunde(), _endrunde("Aus dem bisher Geholten: ...")],
                 mitschrift, max_runden=2)
    assert erg.stop_grund == "runden_cap"
    assert erg.text == "Aus dem bisher Geholten: ..."
    assert "tools" not in mitschrift[-1], "die Schlussrunde darf keine Werkzeuge anbieten"
    assert "tools" in mitschrift[0], "die regulaeren Runden schon"
    # Der Auftrag haengt am LETZTEN Nutzer-Turn - zwei Nutzer-Turns hintereinander weist
    # die API zurueck. Ohne ihn kam ein Denkblock und ein leerer Text (gemessen am Pi).
    letzter = mitschrift[-1]["messages"][-1]
    assert letzter["role"] == "user"
    assert any(b.get("type") == "text" and "JETZT abschliessend" in b.get("text", "")
               for b in letzter["content"]), letzter


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


def test_system_cachen_setzt_auch_den_request_weiten_breakpoint():
    """Der System-Breakpoint deckt nur tools+system ab. Der WACHSENDE Teil - die
    Tool-Ergebnisse (bis 20k Zeichen je Runde) und der Thread-Verlauf - braucht den
    request-weiten Breakpoint, sonst zahlt jede Folgerunde ihn erneut voll."""
    mitschrift = []
    _fahre([_toolrunde(), _endrunde()], mitschrift, system_cachen=True)
    for anfrage in mitschrift:
        assert anfrage["cache_control"] == {"type": "ephemeral"}, anfrage


def test_ohne_cachen_bleibt_die_anfrage_frei_von_cache_feldern():
    """Der Eval ist das Messinstrument: seine Anfrageform muss byte-gleich zum
    gemessenen Stand bleiben, sonst gilt die Messung nicht mehr fuer den Bot."""
    mitschrift = []
    _fahre([_toolrunde(), _endrunde()], mitschrift)
    for anfrage in mitschrift:
        assert "cache_control" not in anfrage
        assert "tool_choice" not in anfrage


def test_schlussrunde_behaelt_beim_cachen_die_werkzeuge_und_sperrt_sie():
    """Werkzeuge WEGLASSEN entzieht sie - und wirft den Cache weg, weil die Werkzeuge
    ganz oben im Praefix stehen. 'tool_choice: none' entzieht sie eine Ebene tiefer:
    das Modell kann keines aufrufen, das gecachte tools+system-Praefix bleibt gueltig."""
    mitschrift = []
    erg = _fahre([_toolrunde(), _toolrunde(), _endrunde("Aus dem Geholten: ...")],
                 mitschrift, max_runden=2, system_cachen=True)
    assert erg.stop_grund == "runden_cap"
    schluss = mitschrift[-1]
    assert schluss["tools"] == [{"name": "foliant_suche_bestand"}]
    assert schluss["tool_choice"] == {"type": "none"}


def test_verbrauch_summiert_ueber_alle_runden():
    """Ohne diese Zahlen ist jede Aussage ueber das Caching geraten - ein verfehlter
    Cache sieht von aussen aus wie ein Treffer, er kostet nur mehr."""
    runden = [_toolrunde(), _endrunde()]
    for i, runde in enumerate(runden):
        runde["usage"] = {"cache_read_input_tokens": 100 * (i + 1),
                          "cache_creation_input_tokens": 10,
                          "input_tokens": 5, "output_tokens": 20}
    erg = _fahre(runden, [])
    assert erg.verbrauch.cache_gelesen == 300      # 100 + 200
    assert erg.verbrauch.cache_geschrieben == 20
    assert erg.verbrauch.ungecacht == 10
    assert erg.verbrauch.ausgabe == 40
    assert erg.verbrauch.trefferquote == pytest.approx(300 / 330)


def test_verbrauch_ohne_usage_feld_bleibt_null_statt_zu_reissen():
    """Aeltere/abweichende Antworten duerfen die Schleife nicht kosten - die Messung
    ist Beiwerk, die Auskunft an den Nutzer ist der Zweck."""
    erg = _fahre([_endrunde()], [])
    assert erg.verbrauch.cache_gelesen == 0 and erg.verbrauch.trefferquote == 0.0


def test_verlauf_wird_nie_mutiert():
    verlauf = [{"role": "user", "content": "Frage?"}]

    async def lauf():
        async with _http([_toolrunde(), _endrunde()], []) as http:
            await llm.fahre_schleife(_FakeMcp(), http, "k", "m", "S", [], verlauf)

    asyncio.run(lauf())
    assert verlauf == [{"role": "user", "content": "Frage?"}]
