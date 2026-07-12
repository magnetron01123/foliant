"""Chunking-Regressionstests (Leitplanke: Chunking = wichtigster Qualitaetshebel).

Die Faelle sind aus dem ECHTEN PyMuPDF4LLM-Markdown des dt. SRD 5.2.1 destilliert
(Phase-2-Fund 10.07.2026, siehe bekannte_macken['srd-de']):
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
