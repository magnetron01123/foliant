"""Regressionstests A10/SYN-P1-008 (Open5e-Inhalte fachlich vollstaendig abbilden) -
gegen LOKALE API-Fixtures (echte v2-Antworten vom 10.07.2026, tests/fixtures/), ohne
Live-Netz. Ausnahme: open5e_spell_counterspell.json ist strukturgleich zur echten
Fireball-Antwort nachgebaut (Reaktionszauber-Fall: dort ist reaction_condition belegt
statt null; Inhalt gemaess SRD 5.2)."""
import json
from pathlib import Path

from importer.import_open5e import _md_creature, _md_spell

_FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _lade(name: str) -> dict:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))["results"][0]


def test_a10_creature_sinne_und_passive_perception():
    """Sichtweiten (*_range) und Passive Perception landen im Statblock."""
    md = _md_creature(_lade("open5e_creature.json"))          # Aboleth
    assert "Darkvision 120 ft." in md
    assert "Passive Perception:** 20" in md


def test_a10_creature_resistenzen():
    """resistances_and_immunities wird uebernommen (Vampir: necrotic-Resistenz)."""
    vampir = _lade("open5e_creature_vampire.json")
    md = _md_creature(vampir)
    assert "Damage Resistances:** necrotic" in md
    # Leere Felder erzeugen KEINE leeren Labels:
    assert "Damage Immunities" not in md


def test_a10_spell_strukturfelder():
    """Fireball: damage_roll/damage_types und shape_* werden nicht verworfen."""
    md = _md_spell(_lade("open5e_spell_fireball.json"))
    assert "Damage:** 8d6 fire" in md
    assert "Shape:** 20 feet sphere" in md
    assert "Level:** 3" in md and "fiery explosion" in md.lower() or "8d6" in md


def test_syn_p1_008_spell_reaktions_trigger():
    """Counterspell: reaction_condition (der Ausloeser der Reaktion) haengt an der
    Casting Time - ohne ihn ist unklar, WANN der Zauber ueberhaupt erlaubt ist."""
    md = _md_spell(_lade("open5e_spell_counterspell.json"))
    assert ("Casting Time:** reaction, which you take when you see a creature "
            "within 60 feet of yourself casting a spell") in md
    # Gegenprobe: reaction_condition=null (Fireball) haengt nichts an.
    md_fb = _md_spell(_lade("open5e_spell_fireball.json"))
    assert "Casting Time:** action ·" in md_fb


def test_syn_p1_008_creature_recharge_form_initiative():
    """Vampir: usage_limits (RECHARGE), limited_to_form und initiative_bonus
    ueberleben den Import - alles regelentscheidend am Spieltisch."""
    md = _md_creature(_lade("open5e_creature_vampire.json"))
    assert "**Charm (Recharge 5–6).**" in md            # usage_limits RECHARGE/5
    assert "**Bite (Bat or Vampire Form Only).**" in md  # limited_to_form
    assert "Initiative:** +14" in md                     # initiative_bonus (nicht DEX-Mod!)
    # Kosten 1 sind der stillschweigende Normalfall und duerfen NICHT auftauchen:
    assert "**Deathless Strike.**" in md
    assert "Costs 1 Action" not in md


def test_syn_p1_008_creature_per_day_und_stille_einzelkosten():
    """Aboleth: usage_limits PER_DAY wird '2/Day'; legendary_action_cost 1 an
    NORMALEN Aktionen (API-Modellierung, z. B. Tentacle) bleibt ohne Zusatz."""
    md = _md_creature(_lade("open5e_creature.json"))
    assert "**Dominate Mind (2/Day).**" in md
    assert "**Tentacle.**" in md
    assert "Initiative:** +7" in md


def test_syn_p1_008_creature_legendary_mehrkosten():
    """Mehrkosten (>1) legendaerer Aktionen werden genannt. Kein Fixture belegt
    Kosten 2, darum synthetischer Minimalfall mit den Fixture-Feldnamen."""
    md = _md_creature({"name": "Testwesen", "actions": [
        {"name": "Schweifhieb", "desc": "Zwei Hiebe.", "action_type": "LEGENDARY_ACTION",
         "legendary_action_cost": 2, "limited_to_form": None, "usage_limits": None}]})
    assert "**Schweifhieb (Costs 2 Actions).**" in md
