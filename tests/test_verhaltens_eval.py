"""Eval-Harness (Schicht 3): NUR die deterministischen Grader und die Fall-Struktur -
keine API-Aufrufe in `make test` (der echte Lauf kostet Tokens und ist bewusst ein
separates Kommando: python -m evals.verhaltens_eval)."""
from evals.faelle import FAELLE, KOPF_ANKER
from evals.verhaltens_eval import (BELEG_RE, fehlende_statblock_sektionen,
                                   projektanweisung, pruefe_deterministisch,
                                   pruefe_geruest, systeme)


def test_faelle_decken_die_backlog_checkliste():
    ids = [f["id"] for f in FAELLE]
    assert ids == sorted(set(ids), key=ids.index), "doppelte Fall-IDs"
    erwartet = {"A1", "A2", "A3", "A4", "B1", "B2", "B3", "B4", "B5",
                "C1", "C2", "C3", "D1", "D2", "D3", "E1", "E2",
                "DC1", "DC2", "DC3", "DC4",
                "F1", "F2", "F3", "F4", "F5"}
    assert set(ids) == erwartet
    for f in FAELLE:
        if f.get("uebersprungen"):
            continue                          # ehrlich dokumentierte Handarbeit
        assert f.get("frage"), f["id"]
        if f.get("richter"):
            assert f.get("rubrik"), f["id"]   # Richter braucht eine Rubrik
        assert f.get("system", "standard") in ("standard", "discord"), f["id"]


def test_nur_die_dc_faelle_fahren_den_discord_zusatz():
    """Die tragenden Regeln (Grounding, Spoiler, Deutsch-first) muessen ohne den
    Darstellungs-Zusatz gemessen bleiben - sonst misst der Eval eine Zusicherung,
    die der Zusatz selbst mittraegt."""
    mit_zusatz = {f["id"] for f in FAELLE if f.get("system") == "discord"}
    assert mit_zusatz == {"DC1", "DC2", "DC3", "DC4"}


def test_systeme_enthalten_projektanweisung_und_discord_variante():
    varianten = systeme()
    assert varianten["standard"] == projektanweisung()
    # Der Bot haengt den Zusatz an, ersetzt die Anweisung nie (haupt.py._system_prompt).
    assert varianten["discord"].startswith(varianten["standard"])
    assert "Codeblock" in varianten["discord"]


def test_grader_erkennt_markdown_tabelle_nur_ausserhalb_von_codebloecken():
    fall = dict(id="X", keine_md_tabelle=True)
    tabelle = "| Name | Wert |\n|---|---|\n| RK | 15 |"
    assert any("Markdown-Tabelle" in g
               for g in pruefe_deterministisch(fall, tabelle, []))
    # Dieselben Zeichen im Codeblock sind die ERLAUBTE Darstellung.
    im_code = f"Statblock:\n```text\n{tabelle}\n```"
    assert pruefe_deterministisch(fall, im_code, []) == []
    # Ohne das Feld interessiert die Tabelle nicht (alle uebrigen Faelle).
    assert pruefe_deterministisch(dict(id="X"), tabelle, []) == []


def test_grader_haelt_normalen_text_mit_strichen_fuer_keine_tabelle():
    """Fehlalarm-Absicherung: '-' und '|' kommen in echten Antworten vor."""
    fall = dict(id="X", keine_md_tabelle=True)
    for harmlos in ("Der Wert liegt bei 15-18 Punkten.",
                    "Trefferpunkte - Ruestungsklasse - Bewegung",
                    "Bedingung | Wirkung steht im Fliesstext."):
        assert pruefe_deterministisch(fall, harmlos, []) == [], harmlos


def test_eval_liest_die_projektanweisungs_datei():
    """Der Eval misst gegen genau den Text, den die Runde ins Claude-Projekt kopiert -
    config/projektanweisung.md. (Bis Rev. 9 stand er als Codeblock in SPEC.md; der alte
    Testname sprach noch vom 'SPEC-Block'.)"""
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


def test_grader_regex_muster_mit_ankern():
    """Die F-Serie (B12-Antwortgeruest) prueft POSITIONEN - Kopfzeilen-Emoji am
    Antwortanfang, Belegzeile als letzte Zeile. Substrings koennen das nicht."""
    fall = dict(id="X", muster_pflicht=[KOPF_ANKER,
                                        r"📖[^\n]*Regelversion:? \d{4}\W*\Z"],
                muster_verboten=[r"unterabschnitt"])
    gut = "🪄 **Feuerball (Fireball)**\nGrad 3.\n📖 Quelle: SRD · Regelversion: 2024"
    assert pruefe_deterministisch(fall, gut, []) == []
    # Emoji nicht am Anfang + Beleg nicht zuletzt + Meta-Wort (case-insensitiv).
    schlecht = ("Gerne! 🪄 Feuerball.\n📖 Quelle: SRD · Regelversion: 2024\n"
                "Der Eintrag hat noch einen Unterabschnitt.")
    assert len(pruefe_deterministisch(fall, schlecht, [])) == 3


def test_kopfanker_akzeptiert_fettgedruckte_kopfzeile():
    """Erster echter Lauf (06.08.2026): '**🪄 Feuerball (Fireball)**' - das Emoji steht
    am Kopf, nur INNERHALB des Fettdrucks. Das erfuellt B12 Slot 1; ein Anker, der
    daran scheitert, ist ein Fehlalarm wie frueher A3 ('Schwaeche') und B1 ('-2')."""
    fall = dict(id="X", muster_pflicht=[KOPF_ANKER])
    for gut in ("**🪄 Feuerball (Fireball)**\nGrad 3.", "🪄 **Feuerball**", "❌ Nichts."):
        assert pruefe_deterministisch(fall, gut, []) == [], gut
    # Fliesstext VOR der Kopfzeile bleibt ein Fehler (Floskel, S13).
    assert pruefe_deterministisch(fall, "Gerne! **🪄 Feuerball**", []) != []


def test_grader_leere_antwort_ist_fail():
    assert any("Leere Antwort" in g
               for g in pruefe_deterministisch(dict(id="X"), "   ", []))


def test_grader_erwartete_tools_ist_oder_verknuepft():
    fall = dict(id="X", erwartete_tools=["foliant_hol_eintrag", "foliant_suche_bestand"])
    assert pruefe_deterministisch(fall, "ok", ["foliant_suche_bestand"]) == []
    assert pruefe_deterministisch(fall, "ok", ["foliant_liste_optionen"]) != []


# --------------------------------------------------------------- Das Antwortgeruest
# Was fuer JEDE Antwort gilt (B12/B13/B16), sitzt bewusst in `pruefe_geruest` und nicht
# in `pruefe_deterministisch`: Die Fixtures dort sind nackte Textschnipsel ohne Kopfzeile,
# und zwei Tests zaehlen ihre Gruende exakt. Eine unbedingte Pruefung darin haette sechs
# bestehende Tests gebrochen, ohne dass ein Verhalten sich geaendert haette.

# Jede Phrase, die S14/B12 woertlich vorschreiben - der Selbstschutz unten faehrt sie
# alle auf einmal gegen den Pruefsatz.
_PFLICHTPHRASEN = (
    "❌ Dazu finde ich nichts im Foliant-Bestand.",
    "⚠️ Nur 2014-Fassung im Bestand - ggf. an 2024 anzupassen.",
    "🌐 Aus dem Web (NICHT aus dem Foliant-Bestand, ungeprüft):",
    "⚖️ Regelt der Text nicht eindeutig - SL entscheidet.",
    "Welchen meinst du?",
    "Sag Bescheid, wenn du den vollen Wortlaut brauchst.",
    "* keine offizielle deutsche Übersetzung",
    "📖 Quelle: SRD 5.2.1 (Deutsch) · S. 139 · Regelversion: 2024",
)


def test_geruest_laesst_alle_pflichtphrasen_durch():
    """Der wichtigste Test der Reihe - er schuetzt den Pruefsatz vor sich selbst.

    Die Verbotsliste darf nur Feld- und Werkzeugnamen enthalten, nie Alltagswoerter:
    'Bestand' steht in DREI vorgeschriebenen Phrasen, 'Quelle' in der Belegzeile,
    'Uebersetzung' in der *-Fussnote. Wer hier kuenftig ein Wort ergaenzt, das eine
    Pflichtphrase zerschiesst, faellt sofort auf - und nicht erst nach einem bezahlten
    Volllauf, wie bei A3 ('Schwaeche'), B1 ('-2') und F2 ('ruchlos')."""
    assert pruefe_geruest("\n".join(_PFLICHTPHRASEN)) == []


def test_geruest_verlangt_kopfzeilen_emoji():
    """Negativfaelle sind ECHTE Antworten aus den Pi-Laeufen vom 06./07.08.2026, die
    beide gruen durchliefen: F4 eroeffnete ohne ❓, D1 mit einer Meta-Aussage."""
    for gut in ("🪄 **Feuerball (Fireball)**", "**⚔️ Klasse**", "# 🐉 Solar", "❓ Schild"):
        assert pruefe_geruest(gut) == [], gut
    for schlecht in ('"Schild" ist mehrdeutig – gemeint sein könnte der **Zauber**',
                     "No dedizierte Regelauslegung dazu; die Antwort ergibt sich aus …",
                     "Für den Hexenmeister (Warlock) sind fünf Unterklassen gelistet."):
        assert any("Kopfzeile" in g for g in pruefe_geruest(schlecht)), schlecht


def test_geruest_verbietet_werkzeug_und_feldnamen():
    """Echte C3-Antwort (Pi, 06.08.2026): Sie zitierte den Feldnamen mitten im Menue."""
    schlecht = "⚔️ **Klassen**\n**Zusätzlich aus Erweiterungsbänden (🚫 abenteuer_setting)**"
    assert any("Feldname" in g for g in pruefe_geruest(schlecht))
    # Der Fliesstext-Begriff bleibt erlaubt - gebannt ist die snake_case-Form.
    assert pruefe_geruest("⚔️ **Klassen**\nAus einem Abenteuer-Setting-Band.") == []


def test_geruest_verlangt_belegzeile_als_letzte_zeile():
    """B12 Slot 5. Mehrere 📖-Zeilen sind erlaubt, ebenso ein Zusatz je Quelle - die
    Menue-Antwort vom 07.08.2026 endet auf '… Regelversion: 2024 (Untoter Schutzherr)'
    und darf daran nicht scheitern."""
    gut = ("🪄 **Feuerball**\nGrad 3.\n📖 Quelle: SRD · Regelversion: 2024 (Grundtext)\n"
           "📖 Quelle: Ravenloft · Regelversion: 2024 (Untoter Schutzherr)")
    assert pruefe_geruest(gut) == []
    schlecht = ("🪄 **Feuerball**\n📖 Quelle: SRD · Regelversion: 2024\n"
                "Sag Bescheid, wenn du mehr brauchst.")
    assert any("letzte Zeile" in g for g in pruefe_geruest(schlecht))
    # Ohne Beleg greift die Regel nicht (❌-Antworten tragen keinen).
    assert pruefe_geruest("❌ Dazu finde ich nichts im Foliant-Bestand.") == []


def test_geruest_erlaubt_hoechstens_ein_angebot_und_ordnet_die_fussnote():
    zwei = ("🪄 **Feuerball**\nSag Bescheid, wenn du A brauchst.\n"
            "Sag Bescheid, wenn du B brauchst.\n📖 Quelle: SRD · Regelversion: 2024")
    assert any("Angebote" in g for g in pruefe_geruest(zwei))
    verdreht = ("🪄 **Feuerball**\n📖 Quelle: SRD · Regelversion: 2024\n"
                "* keine offizielle deutsche Übersetzung")
    gruende = pruefe_geruest(verdreht)
    assert any("Fussnote" in g for g in gruende)


# ----------------------------------------------------- Statblock-Vollstaendigkeit (B3)

def _auszug(regeltext: str) -> str:
    """Ein Auszug so, wie app/llm.py ihn baut: Werkzeug-Praefix plus die JSON-ZEILE der
    Tool-Ausgabe. Entscheidend ist das JSON: dort steht ein Zeilenumbruch als die zwei
    Zeichen '\\' und 'n'. Ein handgemalter Markdown-String wuerde am Grader vorbeitesten
    und die Pruefung als stillen No-Op durchgehen lassen."""
    import json

    return "[foliant_hol_eintrag]\n" + json.dumps(
        {"regeltext_md": regeltext, "hinweis_abkuerzungen": "…"},
        ensure_ascii=False, separators=(",", ":"))


def test_statblock_check_liest_ueberschriften_aus_der_json_zeile():
    auszug = _auszug("###### Merkmale\n\nMagieresistenz: Vorteil.\n\n"
                     "###### Aktionen\n\nBogen des Tötens: +15 auf den Angriff.")
    assert "\\n" in auszug, "Vorbedingung: der Auszug ist JSON, kein Markdown"
    assert fehlende_statblock_sektionen("🐉 Solar\nMerkmale … Aktionen …", [auszug]) == []
    fehlt = fehlende_statblock_sektionen("🐉 Solar\nMerkmale: Magieresistenz", [auszug])
    assert any("Aktionen" in g for g in fehlt)


def test_statblock_check_ueberspringt_leere_sektionen():
    """Der srd-de-Solar traegt '###### Bonusaktionen' als LETZTE Zeile ohne Inhalt (der
    Import hat den Block verloren, 5 Faelle im Bestand). Was der Bestand nicht hat, darf
    keine Antwort schulden - sonst waere der Fall dauerhaft rot und keine Prompt-Regel
    koennte ihn heilen."""
    auszug = _auszug("###### Aktionen\n\nBogen des Tötens: +15.\n\n###### Bonusaktionen")
    assert fehlende_statblock_sektionen("🐉 Solar\nAktionen: Bogen", [auszug]) == []


def test_statblock_check_verwechselt_aktionen_nicht_mit_legendaeren():
    """'Aktionen' ist Teilstring von 'Legendäre Aktionen' - ohne Maskierung bestuende
    eine Antwort ohne Aktionsblock, nur weil sie legendaere Aktionen nennt."""
    auszug = _auszug("###### Aktionen\n\nBogen des Tötens.\n\n"
                     "###### Legendäre Aktionen\n\nSchlag: Ein Angriff.")
    fehlt = fehlende_statblock_sektionen("🐉 Solar\nLegendäre Aktionen: Schlag", [auszug])
    assert [g for g in fehlt if "'Aktionen'" in g], fehlt
    assert not [g for g in fehlt if "Legendäre" in g]


def test_statblock_check_ignoriert_trefferlisten():
    """Eine Suchliste enthaelt Abschnitte FREMDER Kreaturen - daraus etwas einzufordern,
    waere ein Fehlalarm."""
    liste = "[foliant_suche_bestand]\n" + _auszug("###### Aktionen\n\nFremdes Monster.")[22:]
    assert fehlende_statblock_sektionen("🐉 Solar", [liste]) == []


def test_paritaetsmodus_faehrt_jeden_fall_in_beiden_varianten():
    """Eigentuemer-Anspruch (08.08.2026): Discord-Bot und Direkt-Konnektor sollen
    moeglichst identisch antworten. '--prompt beide' macht die Paritaet messbar, statt
    sie von Hand zu vergleichen; im Normalmodus ('fall') aendert sich NICHTS am
    gemessenen Verhalten."""
    from evals.verhaltens_eval import zu_fahrende_varianten

    varianten = {"standard": "S", "discord": "S\n\nZUSATZ"}
    fall = {"id": "X", "system": "discord"}
    assert zu_fahrende_varianten(fall, varianten, "fall") == [("discord", "S\n\nZUSATZ")]
    assert zu_fahrende_varianten({"id": "Y"}, varianten, "fall") == [("standard", "S")]
    beide = zu_fahrende_varianten(fall, varianten, "beide")
    assert [v for v, _s in beide] == ["discord", "standard"]
    # Fehlende Variante: ehrlich leer (der Lauf meldet 'uebersprungen') bzw. bei
    # 'beide' nur das, was existiert - nie ein stiller Lauf gegen den falschen Prompt.
    assert zu_fahrende_varianten(fall, {"standard": "S"}, "fall") == []
    assert zu_fahrende_varianten(fall, {"standard": "S"}, "beide") == [("standard", "S")]
