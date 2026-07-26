"""Eval-Harness (Schicht 3): NUR die deterministischen Grader und die Fall-Struktur -
keine API-Aufrufe in `make test` (der echte Lauf kostet Tokens und ist bewusst ein
separates Kommando: python -m evals.verhaltens_eval)."""
from evals.faelle import FAELLE
from evals.verhaltens_eval import BELEG_RE, projektanweisung, pruefe_deterministisch


def test_faelle_decken_die_backlog_checkliste():
    ids = [f["id"] for f in FAELLE]
    assert ids == sorted(set(ids), key=ids.index), "doppelte Fall-IDs"
    erwartet = {"A1", "A2", "A3", "A4", "B1", "B2", "B3", "B4", "B5",
                "C1", "C2", "C3", "D1", "D2", "D3", "E1", "E2"}
    assert set(ids) == erwartet
    for f in FAELLE:
        if f.get("uebersprungen"):
            continue                          # ehrlich dokumentierte Handarbeit
        assert f.get("frage"), f["id"]
        if f.get("richter"):
            assert f.get("rubrik"), f["id"]   # Richter braucht eine Rubrik


def test_projektanweisung_extraktor_findet_den_spec_block():
    text = projektanweisung()
    assert text.startswith("Du hilfst unserer D&D-Runde")
    assert "🚫" in text and "❌" in text      # tragende Marker sind drin


def test_grader_pflicht_verboten_und_alternativen():
    fall = dict(id="X", pflicht=["❌"], pflicht_eine=["−2", "-2"],
                verboten=["Sonnenschwert"], erwartete_tools=["foliant_suche_bestand"])
    ok = pruefe_deterministisch(fall, "❌ nichts gefunden, Malus -2.",
                                ["foliant_suche_bestand"])
    assert ok == []
    schlecht = pruefe_deterministisch(
        fall, "Das Sonnenschwert hilft gegen Strahd.", [])
    assert len(schlecht) == 4                 # pflicht, pflicht_eine, verboten, tools


def test_grader_belegzeilen_format():
    fall = dict(id="X")
    # Beide Schreibweisen gelten: der Server baut das 'zitat' mit Doppelpunkten, aeltere
    # Prompt-Beispiele standen ohne (Befund Volllauf 26.07.2026).
    for gut in ("Feuerball wirkt.\n📖 SRD 5.2.1 (Deutsch) · S. 241 · Regelversion 2024",
                "Feuerball wirkt.\n📖 Quelle: SRD 5.2.1 (Deutsch) · S. 241 · "
                "Regelversion: 2024"):
        assert pruefe_deterministisch(fall, gut, []) == [], gut
        assert BELEG_RE.search(gut)
    kaputt = "Feuerball wirkt. 📖 irgendwo"
    assert any("Belegzeile" in g for g in pruefe_deterministisch(fall, kaputt, []))


def test_grader_leere_antwort_ist_fail():
    assert any("Leere Antwort" in g
               for g in pruefe_deterministisch(dict(id="X"), "   ", []))


def test_grader_erwartete_tools_ist_oder_verknuepft():
    fall = dict(id="X", erwartete_tools=["foliant_hol_zauber", "foliant_suche_bestand"])
    assert pruefe_deterministisch(fall, "ok", ["foliant_suche_bestand"]) == []
    assert pruefe_deterministisch(fall, "ok", ["foliant_hol_monster"]) != []
