"""Die Verhaltensregeln laufen ueber drei Kanaele (SPEC.md §7). Alle drei sind Freitext
und driften deshalb lautlos auseinander:

  1. die Server-Instruktion in `config/stil.py`
  2. die Copy-Paste-Projektanweisung in `config/projektanweisung.md`
  3. die Grounding-Hinweise IN den Tool-Ausgaben (app/tools/ausgabe.py + charakter.py)

CLAUDE.md verlangt seit jeher, sie synchron zu halten - bisher war das eine Bitte an den
Menschen, hier wird es geprueft.

Der Test prueft NICHT auf Wortgleichheit (die Kanaele haben unterschiedliche Adressaten
und duerfen anders formulieren), sondern darauf, dass jede tragende Regel vorkommt.

Kanal 3 kam am 29.07.2026 dazu. Er war der einzige ungeschuetzte - ausgerechnet der, den
SPEC.md §7 als den ZUVERLAESSIGSTEN bezeichnet, weil seine Hinweise bei jeder Antwort im
Kontext stehen. HINWEIS_LEER haette sein ❌ verlieren koennen, ohne dass irgendetwas
anschlaegt.
"""
from __future__ import annotations

import pathlib

import pytest

from app.tools import ausgabe as aus
from app.tools import charakter as ch
from config import stil
from config.stil import INSTRUCTIONS


@pytest.fixture(scope="module")
def projektanweisung() -> str:
    """Der Text aus config/projektanweisung.md - genau das, was in ein Claude-Projekt
    eingefuegt wird und was die Website ausliefert (EINE Quelle, keine Kopie)."""
    text = stil.projektanweisung()
    assert text, "config/projektanweisung.md fehlt oder ist leer"
    return text


# Je Regel ein Kennzeichen, das in BEIDEN Kanaelen vorkommen muss. Bewusst kurze,
# stabile Fragmente - keine ganzen Saetze, sonst bricht der Test bei jeder Umformulierung.
_TRAGENDE_REGELN = [
    ("Spoiler-Ablehnung", "🚫"),
    ("Leerbefund-Kennzeichnung", "❌"),
    ("Web-Kennzeichnung", "🌐"),
    ("Bestand ist einzige Quelle", "Trainingswissen"),
    ("Belegzeile", "📖"),
    ("Altstand-Warnung", "⚠️"),
    ("SL-Verweis bei Regelluecke", "⚖️"),
    ("Stern-Regel", "*"),
    ("amtliche Begriffe aus dem Tool", "begriffe_deutsch"),
    ("2024-Baureihenfolge", "Hintergrund"),
    ("Pflichtwahl Sprachen", "SPRACHEN"),
    ("Parameterfehler ist kein Leerbefund", "fehler"),
    ("Gegenprobe vor dem Leerbefund", "foliant_suche_bestand"),
    ("gekuerzte Trefferliste", "hinweis_gekuerzt"),
    ("Spoiler-Kennzeichnung der Quelle", "abenteuer_setting"),
    # Eval-Volllauf 26.07.2026 (Fall D3): der Server wies die abweichende englische
    # Vampir-Fassung als 'fremdsprachige_fassungen' aus, aber KEIN Kanal sagte dem
    # Modell, was es damit tun soll - es gab still nur die deutsche Fassung aus.
    ("abweichende Fassung offenlegen", "fremdsprachige_fassungen"),
    # A8 (Audit 28.07.2026): Der Breadcrumb stand in beiden Kanaelen, war aber als
    # einzige der tragenden Regeln UNGESCHUETZT - er konnte aus einem Kanal
    # verschwinden, ohne dass etwas anschlaegt. BACKLOG §3 stuetzt eine bewusste
    # Nicht-Behebung (24 fehlkategorisierte Zauberabschnitte) ausdruecklich darauf,
    # dass der Breadcrumb sie ausweist - dann muss die Erwartung auch verankert sein.
    ("Breadcrumb erklaert", "*Kontext:"),
]


@pytest.mark.parametrize("name,kennzeichen", _TRAGENDE_REGELN,
                         ids=[n for n, _ in _TRAGENDE_REGELN])
def test_regel_steht_in_beiden_kanaelen(name, kennzeichen, projektanweisung):
    assert kennzeichen in INSTRUCTIONS, f"{name}: fehlt in config/stil.py"
    assert kennzeichen in projektanweisung, f"{name}: fehlt in config/projektanweisung.md"


def test_spoilerschutz_steht_ganz_oben():
    """Reihenfolge ist Wirkung: der Spoiler-Schutz ist die oberste Verhaltensregel
    (SPEC.md §7) und muss vor allen Wissensquellen-Regeln stehen."""
    assert INSTRUCTIONS.index("KEINE SPOILER") < INSTRUCTIONS.index("PRIORITÄTSLEITER")


def test_instruktion_bleibt_kompakt():
    """Die Instruktion liegt bei JEDER Verbindung im Kontext. Waechst sie unbegrenzt,
    verduennt sie sich selbst: je mehr Regeln, desto weniger Gewicht je Regel.

    7500 ist ein Budget mit Luft, keine Klippe - der Stand liegt bei ~6000. Loest der
    Test aus, ist die Frage nicht "Grenze anheben", sondern welche Regel dafuer raus
    kann oder in die Tool-Ausgabe gehoert (der zuverlaessigere Kanal, SPEC.md §7)."""
    assert len(INSTRUCTIONS) < 7500, (
        f"stil.py INSTRUCTIONS: {len(INSTRUCTIONS)} Zeichen - erst kuerzen, dann anheben")


def test_projektanweisung_liegt_als_eigene_datei_vor():
    """Die Datei IST die Quelle - fuer die Website, den Eval-Harness, das Kopier-Skript
    und diesen Test. Faellt sie weg oder wird sie leer, muss das hier auffallen und nicht
    erst als leerer Abschnitt auf der Seite der Runde."""
    datei = pathlib.Path(__file__).resolve().parents[1] / "config" / "projektanweisung.md"
    assert datei.exists(), "config/projektanweisung.md fehlt"
    text = datei.read_text(encoding="utf-8").strip()
    assert text.startswith("Du hilfst unserer D&D-Runde")
    assert len(text) > 3000, "verdaechtig kurz - versehentlich gekuerzt?"
    assert stil.projektanweisung() == text          # eine Quelle, kein Abschreiben


def test_discord_zusatz_ist_nur_darstellung():
    """Der Discord-Zusatz (config/discord_zusatz.md) haengt an der Projektanweisung,
    ersetzt sie nie - und darf KEINE eigenen Verhaltensregeln einfuehren: die tragenden
    Regeln leben allein in den zwei gemessenen Kanaelen, sonst misst der Eval (reine
    Projektanweisung) nicht mehr das Bot-Verhalten."""
    zusatz = stil.discord_zusatz()
    assert zusatz, "config/discord_zusatz.md fehlt oder ist leer"
    assert "Codeblock" in zusatz                 # der eine Grund seiner Existenz
    assert "keine neuen Verhaltensregeln" in zusatz
    for verboten in ("OBERSTE REGEL", "PRIORITÄTSLEITER", "Trainingswissen"):
        assert verboten not in zusatz, f"Verhaltensregel im Darstellungs-Zusatz: {verboten}"


# Kanal 3: welcher Hinweis welche Zusage tragen muss. Die Fragmente sind bewusst kurz -
# geprueft wird, dass die AUSSAGE dasteht, nicht ihr Wortlaut.
_GROUNDING_HINWEISE = [
    ("Leerbefund ist ehrlich", aus.HINWEIS_LEER, ["❌", "Allgemeinwissen", "B1"]),
    ("Altstand wird gekennzeichnet", aus.HINWEIS_ALT, ["⚠️", "2024", "B5"]),
    ("Mehrdeutigkeit wird nicht geraten", aus.HINWEIS_MEHRDEUTIG, ["NICHT raten", "B4",
                                                                 "eintrag_id"]),
    ("leerer Bestand ist kein Regelmangel", aus.HINWEIS_DB_FEHLT, ["ehrlich", "B1"]),
    ("Stern wird erlaeutert", aus._HINWEIS_STERN, ["*", "S5"]),
    ("2024-Baureihenfolge", ch._HINWEIS_REIHENFOLGE, ["Klasse", "Hintergrund", "Spezies",
                                                      "SPRACHEN"]),
    ("nur Optionen aus dem Bestand", ch._HINWEIS_BESTAND, ["B1", "B2"]),
]


@pytest.mark.parametrize("name,hinweis,fragmente", _GROUNDING_HINWEISE,
                         ids=[n for n, _, _ in _GROUNDING_HINWEISE])
def test_grounding_hinweis_traegt_seine_zusage(name, hinweis, fragmente):
    """Kanal 3 ist laut SPEC.md §7 der zuverlaessigste - und war der einzige ohne Waechter."""
    for frag in fragmente:
        assert frag in hinweis, f"{name}: '{frag}' fehlt im Hinweistext"


def test_leerbefund_hinweis_deckt_sich_mit_der_web_regel():
    """HINWEIS_LEER ist der Ort, an dem das Modell die Websuche-Regel im Moment des
    Nulltreffers liest - also genau dann, wenn die Versuchung zum Auffuellen entsteht.
    Er muss dieselbe Kennzeichnung verlangen wie die beiden Prompt-Kanaele."""
    assert "🌐" in aus.HINWEIS_LEER
    assert "🚫" in aus.HINWEIS_LEER              # Spoiler-Regel gilt auch im Web
    for kanal in (INSTRUCTIONS, stil.projektanweisung()):
        assert "🌐" in kanal


# --------------------------------------------------------------------- Kanal 2
# Die Tool-BESCHREIBUNGEN waren bis zum 30.07.2026 der einzige Verhaltenskanal ohne
# Waechter - ausgerechnet der, den app/server.py:6-15 als Ausfallsicherung fuer Clients
# begruendet, die `instructions` nicht durchreichen. Ohne Pruefung war der KERNREGELN-Block
# in sieben Varianten von 39 bis 159 Byte auseinandergedriftet, und foliant_hol_attributs-
# werte hatte die Quellenpflicht bereits ganz verloren.
#
# Geprueft wird wie in den anderen Kanaelen die AUSSAGE, nicht der Wortlaut: die Tools
# haben verschiedene Aufgaben und duerfen verschieden formulieren. Ein Uebersetzungs-
# Werkzeug nennt keine Regelversion, ein Listen-Werkzeug keinen Regeltext.

def _tool_beschreibungen() -> dict[str, str]:
    """Die Beschreibungen so, wie FastMCP sie dem Client schickt."""
    import asyncio

    from app.server import mcp

    return {name: (werkzeug.description or "")
            for name, werkzeug in asyncio.run(mcp.get_tools()).items()}


def test_jede_tool_beschreibung_traegt_die_kernregeln():
    """Jede Beschreibung muss die drei tragenden Zusagen mitfuehren: nur aus dem Bestand,
    Herkunft nennen, Deutsch-first. Das ist Kanal 2 - er greift, wenn ein Client die
    Server-`instructions` nicht durchreicht."""
    fehlend: list[str] = []
    for name, text in _tool_beschreibungen().items():
        if "KERNREGELN" not in text:
            fehlend.append(f"{name}: kein KERNREGELN-Block")
            continue
        block = text[text.index("KERNREGELN"):]
        # Geerdet: 'nur aus dem Bestand' fuer die Nachschlage-Werkzeuge, 'nichts erfinden'
        # fuer das Glossar, 'nichts aus Allgemeinwissen ergaenzen' fuer die Build-Pruefung.
        # Drei Formulierungen derselben Zusage - der Kanal traegt sie, nicht ein Wortlaut.
        if not any(w in block for w in ("Bestand", "Allgemeinwissen", "erfinden")):
            fehlend.append(f"{name}: sagt nicht, dass nur der Bestand gilt")
        # Herkunft: Regelwerks-Werkzeuge nennen Quelle+Version, das Glossar seine Herkunft
        # ueber das Original in Klammern - beides ist 'sag, woher es kommt'.
        if not any(w in block for w in ("Quelle", "Original", "erfinden")):
            fehlend.append(f"{name}: nennt keine Herkunftspflicht")
        if "Deutsch-first" not in block and "Klammern" not in block:
            fehlend.append(f"{name}: sagt nichts zu Deutsch-first")
    assert not fehlend, "Kanal 2 unvollstaendig:\n  " + "\n  ".join(fehlend)


def test_tool_schema_bleibt_im_kontextbudget():
    """Die Beschreibungen kosten Kontext bei JEDER Verbindung. Sie zu kuerzen ist der
    billigste Eingriff ins Verhalten und war als einziger voellig ungeprueft - ein
    Budget-Deckel macht sowohl Wachstum als auch heimliches Schrumpfen sichtbar.

    Dieselbe Bauart wie der INSTRUCTIONS-Deckel oben: eine Grenze mit Luft, keine Klippe.
    Reisst sie, ist die Frage 'zusammenlegen?' faellig, nicht 'Assert anheben?'."""
    import json

    schema = sum(len(json.dumps({"name": n, "description": t}, ensure_ascii=False))
                 for n, t in _tool_beschreibungen().items())
    assert schema < 11_000, (
        f"Tool-Beschreibungen: {schema} Zeichen - erst zusammenlegen, dann anheben")
