"""Chunking-Regressionstests (Leitplanke: Chunking = wichtigster Qualitaetshebel).

Die Faelle sind aus dem ECHTEN PyMuPDF4LLM-Markdown des dt. SRD 5.2.1 destilliert
(Phase-2-Fund 10.07.2026, siehe importer/import_markdown.py):
  1. Label-Pseudo-Headings ('### **Kreaturentyp:** Humanoide') zerrissen Spezies und Zauber.
  2. Tabellen-Kaesten ('Elfische Abstammungen') liegen auf der Ebene der Speziesnamen ->
     MERGE_REGELN fuehrt sie in den Spezies-Eintrag zurueck.
Die Heading-Level sind hier bewusst die des 4-Seiten-Auszugs; die Fixes sind level-agnostisch
(Label-Erkennung + Body-Start-Signal), genau das sichern die Tests."""
from importer.import_markdown import MERGE_REGELN, SPLIT_REGELN, _chunks

# Destillat der PDF-Seiten 94-96 (Spezies-Kapitel): Elf traegt die Label-Headings und den
# Tabellen-Kasten, Goliath den '_Riesische Abstammung:_'-Riss, danach ein sauberer Ork.
_SPEZIES_MD = """\
# **Charakterherkunft**

## **Charakterspezies**

### **Beschreibungen der Spezies**

#### **Elf**

##### **Kreaturentyp:** Humanoide

**Größe:** Mittelgroß (150–180 cm) **Bewegungsrate:** 9 m

Als Elf hast du diese besonderen Merkmale: **_Dunkelsicht:_** Reichweite 18 Meter.

##### **Elfische Abstammungen**

|**Abstammung**|**1. Stufe**|
|---|---|
|Drow|Dunkelsicht 36 Meter.|

**_Trance:_** Du musst nicht schlafen.

#### **Goliath**

**Kreaturentyp:** Humanoide

**Größe:** Mittelgroß (210–240 cm) **Bewegungsrate:** 10,5 m

##### **_Riesische Abstammung:_** Du stammst von

Riesen ab. Wähle einen Vorzug aus.

#### **Ork**

**Kreaturentyp:** Humanoide **Größe:** Mittelgroß (180–210 cm)

Als Ork hast du diese besonderen Merkmale.
"""

_ZAUBER_MD = """\
# **Zauber**

## **Zauberbeschreibungen**

###### **Feuerball**

_Hervorrufung 3. Grades (Hexenmeister, Magier)_

###### **Zeitaufwand:** Aktion

###### **Reichweite:** 45 Meter

**Komponenten:** V, G, M **Wirkungsdauer:** Unmittelbar

Ein heller Lichtstreif schießt auf einen Punkt.

###### **Federfall**

_Bannmagie 1. Grades (Barde, Magier)_

Wähle bis zu fünf fallende Kreaturen.
"""


def test_label_headings_zerreissen_keine_zauber():
    """'Zeitaufwand:'/'Reichweite:'-Headings sind Fortsetzungszeilen, keine Eintraege."""
    chunks = _chunks(_ZAUBER_MD, split_regeln=SPLIT_REGELN["srd-de"])
    namen = [c["name"] for c in chunks]
    assert namen == ["Feuerball", "Federfall"], namen
    feuerball = chunks[0]["body"]
    assert "**Zeitaufwand:** Aktion" in feuerball
    assert "**Reichweite:** 45 Meter" in feuerball
    assert "Lichtstreif" in feuerball


# Destillat der 2014-Scans: derselbe Riss wie oben, aber der Zauberkopf steht OHNE
# Fettschrift - genau daran ging _LABEL_HEADING vorbei (Befund 27.07.2026). Der letzte
# Abschnitt ist der Negativfall: eine ECHTE Ueberschrift, die einen Doppelpunkt enthaelt.
_ZAUBER_2014_MD = """\
# KAPITEL 10: ZAUBER

###### FEUERBALL

Hervorrufung des 3. Grades

###### Zeitaufwand: 1 Aktion

###### Reichweite: 45 m

###### Komponenten: V, G, M (Fledermauskot)

Ein heller Lichtstreif schießt auf einen Punkt.

###### KAPITEL 3: KLASSEN

Dieser Abschnitt ist eine echte Ueberschrift.
"""


def test_zauberkopf_ohne_fettschrift_wird_kein_eintragsname():
    """Der 2014-Fall: '###### Zeitaufwand: 1 Aktion' ist eine Fortsetzungszeile. Wurde sie
    als Eintrag genommen, verlor der Zauber seinen Namen UND seinen Text (46 Faelle im
    phb-2014-de). Der zweite Teil sichert die enge Fassung des Musters ab: eine echte
    Ueberschrift mit Doppelpunkt bleibt ein Eintrag."""
    chunks = _chunks(_ZAUBER_2014_MD, split_regeln=SPLIT_REGELN["phb-2014-de"])
    namen = [c["name"] for c in chunks]
    assert namen == ["FEUERBALL", "KAPITEL 3: KLASSEN"], namen

    feuerball = chunks[0]["body"]
    for zeile in ("Zeitaufwand: 1 Aktion", "Reichweite: 45 m",
                  "Komponenten: V, G, M (Fledermauskot)", "Lichtstreif"):
        assert zeile in feuerball, f"{zeile!r} fehlt im Body"


def test_kopf_heading_trifft_nur_zauberkopf_woerter():
    """Negativabsicherung des Musters selbst: es darf NUR die Kopf-Schluesselwoerter
    fassen. Ein 'Wort:'-Muster allgemein wuerde halbe Kapitel entwerten."""
    from importer.import_markdown import KOPF_HEADING

    for treffer in ("Zeitaufwand: 1 Aktion", "Reichweite: Berührung", "Range: Touch",
                    "KOMPONENTEN: V, G", "Wirkungsdauer: unmittelbar", "Duration: 1 hour"):
        assert KOPF_HEADING.match(treffer), treffer
    for kein_treffer in ("KAPITEL 3: KLASSEN", "Schritt 1: Klasse auswählen",
                         "Kämpfer-Unterklasse: Champion", "Feuerball",
                         "Reichweitenwaffen", "Zeitaufwandsrechnung"):
        assert not KOPF_HEADING.match(kein_treffer), kein_treffer


def test_spezies_bleiben_ganz():
    """Elf/Goliath/Ork je EIN Eintrag; Tabellen-Kasten und Label-Risse im Body (MERGE)."""
    chunks = _chunks(_SPEZIES_MD, split_regeln=SPLIT_REGELN["srd-de"],
                     merge_regeln=MERGE_REGELN["srd-de"])
    spezies = [c for c in chunks if c["kategorie"] == "spezies"]
    namen = [c["name"] for c in spezies]
    assert namen == ["Elf", "Goliath", "Ork"], namen

    elf = spezies[0]["body"]
    assert elf.startswith("*Kontext:")                     # Kontextzeile kommt NACH dem Merge
    assert "**Kreaturentyp:** Humanoide" in elf            # Label-Heading -> Body
    assert "**Elfische Abstammungen**" in elf              # Tabellen-Kasten gemergt
    assert "Trance" in elf                                 # Text NACH dem Kasten auch
    goliath = spezies[1]["body"]
    assert "Riesische Abstammung" in goliath and "Riesen ab" in goliath


def test_echte_doppelpunkt_headings_bleiben():
    """Doppelpunkt MITTEN im Fettblock ist ein echter Name, kein Label (Unterklassen!)."""
    md = ("# **Klassen**\n\n### **Kämpfer**\n\nHauptmerkmale.\n\n"
          "##### **Kämpfer-Unterklasse: Champion**\n\nStrebe nach Höchstleistung.\n")
    chunks = _chunks(md, split_regeln=SPLIT_REGELN["srd-de"])
    namen = [c["name"] for c in chunks]
    assert "Kämpfer-Unterklasse: Champion" in namen


def test_nfc_und_soft_hyphen_normalisierung():
    """PDF-Markdown mit NFD-Umlauten und Soft-Hyphens (U+00AD) wird an der Wurzel
    normalisiert - Namen und Bodies kommen NFC-sauber ohne Layout-Zeichen an."""
    nfd_name = "Einflüsterung"                       # NFD: u + combining diaeresis
    md = (f"# **Zauber**\n\n## **Zauberbeschreibungen**\n\n###### **{nfd_name}**\n\n"
          f"_Verzauberung 2. Grades_\n\nDu beeinflusst die Kämpfer­Unterklasse nicht.\n")
    chunks = _chunks(md, split_regeln=SPLIT_REGELN["srd-de"])
    assert chunks[0]["name"] == "Einflüsterung"            # NFC, exakt vergleichbar
    assert "­" not in chunks[0]["body"]
    assert "KämpferUnterklasse" in chunks[0]["body"]


def test_br_tags_werden_zu_leerzeichen():
    """QS-Fund: <br> aus PDF-Tabellenzellen sind HTML-Muell im Plain-Text-Body -> Leerzeichen."""
    md = ("# **Klassen**\n\n### **Kämpfer**\n\n|**Rettungswürfe, in**<br>**denen du geübt "
          "bist**|Stärke<br/>und Konstitution|\n|---|---|\n")
    chunks = _chunks(md, split_regeln=SPLIT_REGELN["srd-de"])
    body = chunks[0]["body"]
    assert "<br>" not in body and "<br/>" not in body.lower()
    assert "geübt bist" in body and "Stärke und Konstitution" in body


_ZAUBER_STATBLOCK_MD = """\
# **Zauber**

## **Beschreibungen der Zauber**

###### **Geist herbeirufen**

_Beschwörungszauber 3. Grades (Druide, Waldläufer)_

Du rufst einen Geist herbei.

###### **Merkmale**

**_Gemeinsame Resistenzen:_** Der Geist widersteht Gift.

###### **Aktionen**

**_Mehrfachangriff:_** Der Geist greift zweimal an.

###### **Materialien**

|**Material**|**Dauer**|
|---|---|
|Stein|24 Stunden|

###### **RK 15**

**TP** 10 (mittelgroß), 20 (groß)

###### **Prismatischer Strahl**

_Hervorrufungszauber 7. Grades (Magier)_

Acht Strahlen schießen hervor.

###### **Treffer-**

**punkte** Der Effekt trifft.

###### **Shillelagh**

die Spielwerte der ursprünglichen Kreatur bleiben erhalten.
"""


def test_zauber_statblock_fragmente_mergen_ohne_zauberverlust():
    """QS-Fund 11.07.2026: Kreatur-Statblocks IN Beschwoerungszaubern (Merkmale/Aktionen)
    und Tabellen-/Statblock-Reste (Materialien-Tabelle, 'RK 15', 'Treffer-') landeten als
    eigene H6-Eintraege. Sie mergen in den Elternzauber - aber ein fehl-geheadeter ECHTER
    Zauber ('Shillelagh', dessen PDF-Text nur verschoben ist) bleibt erhalten (kein Verlust)."""
    chunks = _chunks(_ZAUBER_STATBLOCK_MD, split_regeln=SPLIT_REGELN["srd-de"],
                     merge_regeln=MERGE_REGELN["srd-de"])
    namen = [c["name"] for c in chunks if c["kategorie"] == "zauber"]
    # Statblock-/Tabellen-Fragmente sind KEINE eigenen Eintraege mehr:
    for frag in ("Merkmale", "Aktionen", "Materialien", "RK 15", "Treffer-"):
        assert frag not in namen, (frag, namen)
    # Echte Zauber bleiben - inkl. des fehl-geheadeten 'Shillelagh' (kein Zauberverlust):
    assert "Geist herbeirufen" in namen and "Prismatischer Strahl" in namen
    assert "Shillelagh" in namen, namen
    # Der Statblock-Text wandert in den Elternzauber zurueck:
    geist = next(c for c in chunks if c["name"] == "Geist herbeirufen")
    assert "Mehrfachangriff" in geist["body"] and "Stein" in geist["body"]
    strahl = next(c for c in chunks if c["name"] == "Prismatischer Strahl")
    assert "punkte" in strahl["body"]


def test_fragment_reparatur_wortanfang():
    """Unterlaenge fehlt am WORTANFANG ('eübt' + g = 'geübt') - Fund 10.07.2026: der alte
    Blind-Fallback setzte das g in die erste Luecke ('ingdenen du eübt bist')."""
    md = ("# **Klassen**\n\nDu bist in Stärke geübt.\n\n"
          "### **Rettungswürfe, in denen du eübt bist** **<u>g</u>**\n\n"
          "Stärke und Konstitution.\n")
    chunks = _chunks(md, split_regeln=SPLIT_REGELN["srd-de"])
    namen = [c["name"] for c in chunks]
    assert "Rettungswürfe, in denen du geübt bist" in namen, namen


def test_2014_scans_splitten_auf_eintragsebene():
    """Deutsche 2014-Scans (PHB/Xanathar/SCAG): pymupdf4llm vergibt Heading-Ebenen
    relativ zur Schriftgroessen-Verteilung des GESAMTdokuments - in diesen Baenden
    besetzen die Kapitel-Titelseiten H1-H5, der Inhalt liegt komplett auf H6. Mit dem
    Standard-Level 3 entstanden drei Riesen-Chunks von 300-500 kB ('KAPITEL 1',
    'KAPITEL 2'), in denen die Suche nichts findet (Import-Befund 27.07.2026)."""
    from importer.import_markdown import SPLIT_REGELN, _chunks

    md = "\n".join([
        "# 7,", "", "## **KAPITEL 1**", "",
        "###### **KAVALIER**", "", "Ein Kavalier ist ein Kaempfer-Archetyp.", "",
        "###### **SAMURAI**", "", "Der Samurai kaempft mit Kampfgeist.", "",
    ])
    for kuerzel in ("phb-2014-de", "xgte-2014-de", "scag-2014-de"):
        regeln = SPLIT_REGELN.get(kuerzel)
        assert regeln, f"{kuerzel} braucht Split-Regeln"
        chunks = _chunks(md, kategorie_standard="regel", split_regeln=regeln)
        namen = [c["name"] for c in chunks]
        assert "KAVALIER" in namen and "SAMURAI" in namen, (kuerzel, namen)
    # Gegenprobe: OHNE Quell-Regeln (Standard-Level 3) verschwinden sie im Kapitel
    ohne = [c["name"] for c in _chunks(md, kategorie_standard="regel")]
    assert "KAVALIER" not in ohne


def test_2014_scans_ueberspringen_endlose_anhaenge():
    """Am Buchende versagt die Heading-Erkennung: der letzte Abschnitt sammelte alles
    bis zum Dokumentende ein (PHB: 130 kB Leseliste + Register). Reiner Ballast."""
    from importer.import_markdown import SKIP_NAMEN, SPLIT_REGELN, _chunks

    md = "\n".join([
        "# 7,", "", "###### **KAVALIER**", "", "Regeltext.", "",
        "###### **ANHANG E: LEKTÜRE ZUR INSPIRATION**", "", "Leseliste " * 200, "",
    ])
    chunks = _chunks(md, kategorie_standard="regel",
                     split_regeln=SPLIT_REGELN["phb-2014-de"],
                     skip_namen=SKIP_NAMEN["phb-2014-de"])
    namen = [c["name"] for c in chunks]
    assert "KAVALIER" in namen
    assert not any(n.startswith("ANHANG E") for n in namen), namen


# --------------------------------------------------------------------------- Errata

# Aufbau eines offiziellen WotC-Errata-PDFs: keine Heading-Struktur, die der Konverter
# erkennen koennte - jede Korrektur ist ein Absatz mit fettem Kopf aus betroffener Regel
# und Seite im Grundbuch. Ohne Vorverarbeitung entstuende EIN Riesen-Chunk je Rubrik.
_ERRATA_MD = """\
# Player's Handbook Errata

## Chapter 1: Playing the Game

**Jumping (p. 30).** The rules for jumping clarify that your Speed is halved.

**Difficulty Class (pp. 27-28).** The DC table replaces the old one.

## Chapter 7: Spells

**Fireball (p. 275).** The spell's damage is 8d6, not 6d6.
"""


def test_errata_werden_je_korrektur_ein_eintrag():
    """Der Eintragsname ist die BETROFFENE REGEL - nur so findet das Erratum, wer nach
    der Regel sucht. Und die Seite im Grundbuch steht im BODY, nicht in `eintraege.seite`:
    dort steht die Fundstelle in DIESER Quelle, und das Erratum steht nicht auf S. 275,
    es sagt nur etwas ueber sie."""
    from importer.import_markdown import BEREINIGUNG, SPLIT_REGELN, _chunks

    md = _ERRATA_MD
    for schritt in BEREINIGUNG["errata-phb-2024-en"]:
        md = schritt(md)
    chunks = _chunks(md, kategorie_standard="regel",
                     split_regeln=SPLIT_REGELN["errata-phb-2024-en"])
    namen = [c["name"] for c in chunks]
    assert "Jumping" in namen and "Difficulty Class" in namen and "Fireball" in namen, namen
    feuerball = next(c for c in chunks if c["name"] == "Fireball")
    assert "8d6" in feuerball["body"]
    assert "S. 275" in feuerball["body"]          # Buchseite als Aussage IM Text
    assert feuerball["kategorie"] == "regel"
    # Gegenprobe: ohne die Vorverarbeitung bleibt nur das Kapitel uebrig
    ohne = [c["name"] for c in _chunks(_ERRATA_MD, kategorie_standard="regel",
                                       split_regeln=SPLIT_REGELN["errata-phb-2024-en"])]
    assert "Fireball" not in ohne, ohne


def test_errata_kopf_deckt_die_realen_schreibweisen_ab():
    """Die veroeffentlichten Errata schreiben ihre Koepfe nicht einheitlich. Geprueft an
    den Varianten, die real vorkommen - jede verfehlte Form waere ein Absatz, der ohne
    eigenen Eintrag im Riesen-Chunk verschwindet.

    Der kursive Fall ist der Grund fuer die Namensbereinigung: '**_Fireball_ (p. 275).**'
    haette sonst einen Eintrag namens '_Fireball_' erzeugt - den findet weder die Suche
    noch die Glossar-Bruecke."""
    from importer.import_markdown import _errata_headings

    faelle = {
        "**Jumping (p. 30).** Text.": "### Jumping",
        "**Difficulty Class (pp. 27-28).** Text.": "### Difficulty Class",
        "**Cover (page 30).** Text.": "### Cover",
        "**Jumping (p. 30)**. Text.": "### Jumping",          # Punkt ausserhalb der Sterne
        "**Rules (pp. 27\u201328).** Text.": "### Rules",         # Gedankenstrich
        "**Grappled (pp. 12, 40).** Text.": "### Grappled",   # mehrere Seiten
        "**_Fireball_ (p. 275).** Text.": "### Fireball",     # kursiv -> Name bereinigt
        "**Oil (flask) (p. 30).** Text.": "### Oil (flask)",  # Klammer IM Namen bleibt
    }
    for probe, erwartet in faelle.items():
        assert _errata_headings(probe).split("\n")[0] == erwartet, probe
    # Nicht zu gierig: Buchstaben gehoeren nicht in eine Seitenangabe.
    ungreifbar = "**Weapons (p. 12 and see also 40).** Text."
    assert not _errata_headings(ungreifbar).startswith("###")


def test_errata_erste_seitenangabe_gilt():
    """Review-Befund 31.07.2026: Ein Kopf kann eine ZWEITE Seitenangabe als Querverweis
    fuehren. Der frueher einteilige Regex backtrackte bis zur letzten und schrieb beides
    falsch - den Namen ('Jumping (p. 182). See also Long Jump') und die Buchseite (27
    statt 182). Eine falsche Fundstelle ist schlimmer als keine: sie sieht belegt aus."""
    from importer.import_markdown import _errata_headings

    aus = _errata_headings(
        "**Jumping (p. 182). See also Long Jump (p. 27).** Your jump distance ...")
    assert aus.split("\n")[0] == "### Jumping", aus.split("\n")[0]
    assert "S. 182" in aus and "S. 27 im Grundbuch" not in aus, aus


def test_errata_erkennt_beide_fettformen():
    """Zwei reale Schreibweisen, und die zweite fehlte (Review-Befund 31.07.2026):
    '**Jumping (p. 182).**' hat die Seite INNERHALB der Fettung, '**Jumping** (p. 182).'
    dahinter. Nicht erkannte Koepfe bekommen keinen eigenen Eintrag - ihre Korrektur
    haengt dann stumm am Vorgaenger."""
    from importer.import_markdown import _errata_headings

    aus = _errata_headings(
        "**Cover (p. 30).** Erste.\n\n**Jumping** (p. 182). Zweite.\n")
    assert "### Cover" in aus and "### Jumping" in aus, aus
    assert "S. 30" in aus and "S. 182" in aus, aus


def test_errata_kopf_mitten_in_der_zeile_wird_eigener_eintrag():
    """Befund 03.08.2026, erster Import an der ECHTEN Datei: Vier der 17 PHB-Korrekturen
    beginnen nicht am Zeilenanfang, sondern direkt hinter dem Satzende der vorigen
    ('… to move”. **_Poisoner (p. 206)._** In the Brew Poison …'). Sie hingen stumm am
    Vorgaenger - Poisoner, Conjure Fey, Polymorph und Shapechange fehlten im Bestand.

    Der Wortlaut hier ist aus dem echten PDF genommen, nicht erfunden."""
    from importer.import_markdown import _errata_headings

    echt = ("**_Grappler (p. 204)._** In the Fast Wrestler benefit, "
            "“extra movement to move” is now “You don’t have to spend extra movement "
            "to move”. **_Poisoner (p. 206)._** In the Brew Poison benefit, the text "
            "is corrected.")
    aus = _errata_headings(echt)
    assert "### Grappler" in aus and "### Poisoner" in aus, aus
    assert "S. 204" in aus and "S. 206" in aus, aus
    # Die zweite Ueberschrift muss am ZEILENANFANG stehen - mitten in der Zeile waere
    # '### Poisoner' fuer Markdown keine Ueberschrift, sondern Text mit Rauten.
    assert "\n### Poisoner" in aus, aus


def test_errata_kopf_mitten_im_satz_wird_NICHT_abgetrennt():
    """Ein fetter Name mit Seitenangabe mitten im Satz ist eher ein Querverweis als eine
    neue Korrektur. Abtrennen wuerde den Satz zerreissen und einen Scheineintrag bauen.
    Er faellt dafuer in der Bilanz auf (siehe test_errata_bilanz_zaehlt_...)."""
    from importer.import_markdown import _errata_headings

    aus = _errata_headings("**Cover (p. 30).** Siehe auch **Jumping (p. 12).** dazu.")
    assert aus.count("###") == 1, aus


def test_errata_kursivmarke_landet_nicht_im_body():
    """Das echte Errata setzt '**_Polymorph (p. 306)._**'. Die schliessende Kursiv-Marke
    stand als einzelnes '_' am Anfang JEDES Bodys ('… im Grundbuch.** _ In the …') -
    kosmetisch, aber in fast jedem Eintrag."""
    from importer.import_markdown import _errata_headings

    aus = _errata_headings("**_Polymorph (p. 306)._** In the spell description ...")
    assert "Grundbuch.** In the spell" in aus, aus


def test_errata_bilanz_zaehlt_kopfFORMEN_nicht_zeilenanfaenge():
    """Der gefaehrlichere Fall als 'gar nichts erkannt': der Import laeuft durch, ein Teil
    der Korrekturen hat aber keinen eigenen Eintrag.

    Die Zaehlung war bis zum 03.08.2026 gleichzeitig BLIND und LAUT: Kandidat war 'fetter
    Lauf am Zeilenanfang'. Die vier verpassten Koepfe standen mitten in der Zeile, waren
    also nie Kandidaten - dafuer galt der Dokumenttitel ('**Player's Handbook (2024)**')
    als verpasster Kopf. Gemeldet wurde '1 von 14': ein Fehlalarm, waehrend der echte
    Ausfall unerwaehnt blieb. Gezaehlt wird jetzt, was wie ein Korrektur-Kopf AUSSIEHT."""
    from importer.import_markdown import _errata_headings, letzte_bilanz

    # (a) Ein Titel in Klammern OHNE Seitenangabe ist kein Kandidat - kein Fehlalarm.
    letzte_bilanz().wirkungslos.clear()
    _errata_headings("**Player’s Handbook (2024)**\n\n**Cover (p. 30).** Text.")
    assert not letzte_bilanz().wirkungslos, letzte_bilanz().wirkungslos

    # (b) Ein Kopf, dessen Seitenangabe unlesbar ist, IST ein Kandidat - und faellt auf.
    letzte_bilanz().wirkungslos.clear()
    _errata_headings("**Cover (p. 30).** Erste.\n\n"
                     "**Weapons (p. 12 and see also 40).** Zweite.")
    meldung = " ".join(letzte_bilanz().wirkungslos)
    assert "_errata_headings" in meldung and "1 von 2" in meldung, meldung
    letzte_bilanz().wirkungslos.clear()


def test_errata_muster_meldet_sich_wenn_es_nicht_greift():
    """Das Muster ist an den veroeffentlichten PDFs abgeleitet, aber nie an ihnen
    JUSTIERT worden (sie lagen bei der Umsetzung nicht vor). Fuehrt eine kuenftige
    Fassung einen anderen Kopf, darf das nicht still einen Riesen-Chunk erzeugen -
    dann muss die Bilanz es als WIRKUNGSLOS ausweisen (D1)."""
    from importer.import_markdown import _errata_headings, letzte_bilanz

    letzte_bilanz().wirkungslos.clear()
    _errata_headings("## Chapter 1\n\nEine Korrektur ganz ohne fetten Kopf.\n")
    assert any("_errata_headings" in w for w in letzte_bilanz().wirkungslos)
    letzte_bilanz().wirkungslos.clear()
