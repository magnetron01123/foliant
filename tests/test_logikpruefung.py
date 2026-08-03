"""Die rechnerischen Plausibilitaetspruefungen (app/logikpruefung.py).

WARUM ES SIE GIBT: Der Datenbank-Audit vom 03.08.2026 suchte nach Import- und OCR-Schaeden
und fand: Fast jeder aendert eine ZAHL, und eine falsche Zahl sieht aus wie eine richtige.
Was sie verraet, ist der Widerspruch zu einer anderen Zahl im selben Text. Diese Pruefungen
fanden am Vollbestand genau drei echte Defekte und kein Rauschen - deshalb stehen sie
dauerhaft in `admin check`.

DIE ZWEI FALLSTRICKE, an denen die Pruefung wertlos wuerde, stehen als eigene Tests hier:
  * Die DDB-Quellen escapen ihr Markdown ('10d8 \\+ 20\\)'). Ohne toleriertes Backslash
    faellt ein Viertel des Korpus stumm aus der Pruefung - und der Check meldet OK.
  * Ein Modifikator, der zu einem UNMOEGLICHEN Wert passt, ist trotzdem unmoeglich. Der
    einzige echte Attributsfund (open5e 'Octopus': KON 0 -> -5) ist formeltreu; wer nur die
    Formel prueft, haelt ihn faelschlich fuer geprueft.
"""
from app import logikpruefung as lp


# --------------------------------------------------------------------------------------
# TP-Formel
# --------------------------------------------------------------------------------------

def test_stimmige_trefferpunkte_sind_kein_befund():
    assert lp.pruefe_tp_formel("**TP** 105 (10W12+40)") == []
    assert lp.pruefe_tp_formel("**HP:** 19 (3d8 + 6)") == []


def test_rundung_um_eins_wird_toleriert():
    """Die Buecher runden mal auf, mal ab: 3W8+6 ergibt 19,5 und steht als 19 oder 20."""
    assert lp.pruefe_tp_formel("**HP** 20 (3d8 + 6)") == []
    assert lp.pruefe_tp_formel("**HP** 19 (3d8 + 6)") == []


def test_abweichende_formel_faellt_auf():
    """Der echte Fall aus dem deutschen SRD: 23 x 6,5 + 161 = 310,5, gedruckt sind 287."""
    (befund,) = lp.pruefe_tp_formel("**TP** 287 (23W12+161)")
    assert befund.art == "tp_formel"
    assert "310" in befund.erklaerung and "287" in befund.erklaerung


def test_ddb_backslash_escapes_werden_geprueft():
    """DER teuerste Fallstrick: 'HP** 150 (20d10 \\+ 40\\)' ist das DDB-Format. Faellt es
    aus dem Muster, bleiben ueber 2000 Eintraege ungeprueft und der Check meldet OK."""
    assert lp.pruefe_tp_formel("**HP** 150 (20d10 \\+ 40\\)") == []
    assert len(lp.pruefe_tp_formel("**HP** 999 (20d10 \\+ 40\\)")) == 1
    assert lp.zaehle_geprueft("**HP** 150 (20d10 \\+ 40\\)")["tp_formel"] == 1


def test_alle_vier_statblock_formate_werden_erreicht():
    """Vier Formate, alle im Bestand belegt. Ein Muster, das nur drei trifft, meldet fuer
    das vierte dauerhaft null Befunde - ununterscheidbar von 'sauber'."""
    for text in ("**TP** 287 (23W12+161)",                 # srd-de
                 "**HP:** 105 (10d12 + 40)",               # open5e
                 "**HP** 150 (20d10 \\+ 40\\)",            # ddb-br-2024
                 "Hit Points 135 (18d10 \\+ 36\\)"):       # ddb-basic-rules-2014
        assert lp.zaehle_geprueft(text)["tp_formel"] == 1, text


def test_minuszeichen_in_allen_schreibweisen():
    """Das deutsche SRD setzt U+2212, DDB einen ASCII-Bindestrich. Beide meinen minus."""
    assert lp.pruefe_tp_formel("**TP** 1 (1W4−1)") == []
    assert lp.pruefe_tp_formel("**TP** 1 (1W4-1)") == []


def test_zerrissene_wuerfelgroesse_wird_nicht_doppelt_gemeldet():
    """'(0W1|2+40)' ist ein Zellriss - die Wuerfelpruefung meldet ihn. Die TP-Pruefung
    haelt sich dann heraus, sonst stuende derselbe Defekt zweimal im Bericht."""
    assert lp.pruefe_tp_formel("**TP** 105 (0W1+40)") == []
    assert len(lp.pruefe_wuerfel("**TP** 105 (0W1+40)")) == 1


# --------------------------------------------------------------------------------------
# Attributswerte
# --------------------------------------------------------------------------------------

def test_stimmige_attribute_sind_kein_befund():
    assert lp.pruefe_attribute("**Abilities:** STR 16 (+3), DEX 14 (+2), CON 14 (+2)") == []


def test_unmoeglicher_attributswert_faellt_auf_obwohl_der_modifikator_passt():
    """Der Octopus-Fall. (0-10)//2 = -5 und (-3-10)//2 = -7 - beide Modifikatoren sind
    formeltreu. Nur der Wertebereich verraet den kaputten Datensatz."""
    befunde = lp.pruefe_attribute("**Abilities:** CON 0 (-5), CHA -3 (-7)")
    assert len(befunde) == 2
    assert all("Wertebereich" in b.erklaerung for b in befunde)


def test_falscher_modifikator_faellt_auf():
    (befund,) = lp.pruefe_attribute("**Abilities:** STR 18 (+3)")
    assert "+4" in befund.erklaerung and "+3" in befund.erklaerung


def test_grenzwerte_1_und_30_sind_gueltig():
    assert lp.pruefe_attribute("**Abilities:** STR 1 (-5), CHA 30 (+10)") == []


def test_ddb_attributstabelle_wird_gelesen():
    """'| Str | 21 | \\+5 | \\+5 |' ist das DDB-2024-Format - eine Tabelle, keine Liste."""
    assert lp.zaehle_geprueft("| Str | 21 | \\+5 | \\+5 |")["attribut"] == 1
    assert lp.pruefe_attribute("| Str | 21 | \\+5 | \\+5 |") == []
    assert len(lp.pruefe_attribute("| Str | 21 | \\+9 | \\+5 |")) == 1


def test_attributstabelle_auch_in_grossschrift():
    """Beide Schreibweisen stehen im Bestand ('| STR |' 283-mal). Ein Muster nur fuer die
    haeufigere liess 283 Werte stumm ungeprueft (Review-Befund 03.08.2026)."""
    assert lp.zaehle_geprueft("| STR | 21 | \\+5 | \\+5 |")["attribut"] == 1
    assert len(lp.pruefe_attribute("| STR | 21 | \\+9 | \\+5 |")) == 1


def test_deutsches_srd_attributsformat_wird_gelesen():
    """srd-de schreibt '**Stä** 19 +4 +4' - Wert, Modifikator, Rettungswurf ohne Klammern.
    Ohne dieses Muster blieben 339 Monster der wichtigsten deutschen Quelle ungeprueft;
    die Abdeckung stieg dadurch von 6668 auf 8421 Werte, ohne einen einzigen Fehlalarm."""
    heil = "**Stä** 19 +4 +4 **GeS** 14 +2 +2 **Kon** 17 +3 +3"
    assert lp.zaehle_geprueft(heil)["attribut"] == 3
    assert lp.pruefe_attribute(heil) == []
    (befund,) = lp.pruefe_attribute("**Stä** 19 +9 +4")
    assert "+4" in befund.erklaerung and "+9" in befund.erklaerung


def test_ocr_verschliffene_deutsche_kuerzel_zaehlen_mit():
    """Die Kuerzel kommen aus dem PDF verschliffen ('GeS' statt 'Ges', 'WeI' statt 'Wei').
    Ein strenges Muster verlore genau die Quelle, um die es geht."""
    for kuerzel in ("**GeS** 14 +2", "**WeI** 12 +1", "**Sta** 10 +0"):
        assert lp.zaehle_geprueft(kuerzel)["attribut"] == 1, kuerzel


def test_zerrissene_deutsche_attributstabelle_erzeugt_keinen_fehlalarm():
    """Die kaputten Statblock-Tabellen ('|**Stä**|5|−3|') sind ein CHUNKING-Problem und
    gehoeren ins Bereinigungsregister - hier wuerden sie nur Rauschen erzeugen."""
    assert lp.pruefe_attribute("|**Stä**|5|−3|−3 **GeS**|16|+3|") == []


def test_initiative_wird_nicht_als_attribut_gelesen():
    """'**Initiative** +14 (24)' hat die umgekehrte Form (erst Modifikator, dann Wert).
    Wer sie mitliest, erzeugt lauter Fehlalarme an jedem Statblock."""
    assert lp.pruefe_attribute("**Initiative** +14 (24)") == []
    assert lp.zaehle_geprueft("**Initiative** +14 (24)")["attribut"] == 0


# --------------------------------------------------------------------------------------
# Wuerfelnotation
# --------------------------------------------------------------------------------------

def test_gueltige_wuerfel_sind_kein_befund():
    assert lp.pruefe_wuerfel("8W6 Feuerschaden, 1d20, 2W3, 1W100") == []


def test_w2_und_w3_sind_gueltig():
    """1W3 kommt im Bestand hundertfach offiziell vor - eine Whitelist ohne 2 und 3 haette
    die Pruefung unbrauchbar gemacht."""
    assert lp.pruefe_wuerfel("1W3 Wuchtschaden") == []


def test_grosse_wuerfelzahl_ist_kein_befund():
    """Der Lich wirft echte 42W8. Eine Obergrenze waere geraten, kein Beleg."""
    assert lp.pruefe_wuerfel("42W8 nekrotischer Schaden") == []


def test_ocr_risse_fallen_auf():
    """Die drei echten Formen aus den 2014-Scans und dem srd-de-Zellriss."""
    assert len(lp.pruefe_wuerfel("1W1")) == 1        # OCR: '1W10' ohne die Null
    assert len(lp.pruefe_wuerfel("2W1 2")) == 1      # zerrissenes 2W12
    assert len(lp.pruefe_wuerfel("0W1")) == 1        # Zellriss aus '10W12'


def test_leerer_body_ist_kein_befund():
    assert lp.pruefe_text(None) == [] and lp.pruefe_text("") == []
    assert lp.zaehle_geprueft(None)["wuerfel"] == 0
