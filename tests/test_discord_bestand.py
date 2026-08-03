"""Der Discord-Befehl `/bestand`: welche Buecher stehen im Bestand?

Zwei Dinge sind hier zu pruefen, und das zweite ist das wichtigere:

1. Jede Zeile beantwortet dieselben drei Fragen (Sprache, Regelstand, Umfang) - der
   Beschriftungs-Standard (importer/quellen.py), als Fliesstext-Liste. KEINE
   Codeblock-Tabelle: Discord bricht Codebloecke am Handy bei ~40 Zeichen hart um,
   die Spalten des ersten Wurfs zerfielen dort (Rueckmeldung 03.08.2026).
2. Sie sagt dasselbe wie die WEBSITE. Zwei Oberflaechen auf dieselbe Frage sind zwei
   Stellen, an denen eine Gruppierung driften kann - und eine Quelle, die auf der Seite
   unter "Abenteuer & Settings" steht (Spoiler-Ansage!) und im Bot unter "Regelwerke",
   waere kein Schoenheitsfehler, sondern eine falsche Auskunft darueber, wozu Foliant aus
   diesem Buch antwortet.
"""
from __future__ import annotations

import sqlite3

from app import bestand
from app.discord_bot import antwort
from app.discord_bot import bestand as d_bestand
from tests.hilfen import SCHEMA

QUELLEN = [
    {"titel": "System Reference Document 5.2.1", "sprache": "de", "edition": "2024",
     "inhaltsart": "regelwerk", "versions_stand": None, "eintraege": 1616},
    {"titel": "Spielerhandbuch", "sprache": "de", "edition": "2014",
     "inhaltsart": "regelwerk", "versions_stand": None, "eintraege": 1539},
    {"titel": "Forgotten Realms: Heroes of Faerûn", "sprache": "en", "edition": "2024",
     "inhaltsart": "abenteuer_setting", "versions_stand": None, "eintraege": 281},
    {"titel": "Monster Manual — Errata", "sprache": "en", "edition": "2024",
     "inhaltsart": "errata", "versions_stand": "Errata Version 1.0", "eintraege": 25},
]


def test_jede_zeile_traegt_buch_sprache_regelstand_und_zahl():
    """Die vier Angaben der Website-Zeile, als EINE Fliesstextzeile mit fettem Titel.
    Die Zahl deutsch gesetzt (1.616, nicht 1,616) wie ueberall sonst im Projekt."""
    zeile = d_bestand.zeile(QUELLEN[0])
    assert zeile.startswith("• **System Reference Document 5.2.1** — ")
    assert "Deutsch" in zeile and "Regeln 2024" in zeile and "1.616 Einträge" in zeile
    assert "\n" not in zeile                  # eine Zeile, die weich umbrechen darf
    assert "```" not in d_bestand.text(QUELLEN), (
        "Codeblock - der bricht am Handy bei ~40 Zeichen um und zerlegt die Spalten")


def test_errata_stand_steht_an_der_regelversion_nicht_am_titel():
    """Ein Errata-Band praezisiert die Regelversion, nicht den Werktitel - dieselbe
    Zuordnung wie auf der Seite (app/bestand.py: regelstand)."""
    zeile = d_bestand.zeile(QUELLEN[3])
    assert "**Monster Manual — Errata**" in zeile
    assert "Regeln 2024 · Errata Version 1.0" in zeile


def test_gruppen_trennen_abenteuer_und_errata_mit_ihrer_ansage():
    """Abenteuerbaende stehen getrennt - samt der Ansage, dass daraus nur Regelwerte
    kommen. Die Trennung IST die Auskunft (Spoiler-Schutz, B6/B4)."""
    text = d_bestand.text(QUELLEN)
    assert f"**{bestand.REGELWERKE}**" in text
    assert f"**{bestand.REVISION}**" in text
    assert f"**{bestand.ABENTEUER}**" in text
    abenteuer_teil = text.split(f"**{bestand.ABENTEUER}**")[1]
    assert "Forgotten Realms: Heroes of Faerûn" in abenteuer_teil
    assert "Spoiler-Schutz" in abenteuer_teil
    # Das Regelwerk steht NICHT im Abenteuerblock (Reihenfolge: Regelwerke zuerst).
    assert "Spielerhandbuch" not in abenteuer_teil
    assert "**4 Bücher**" in text and "3.461 Einträgen" in text


def test_erklaertext_bleibt_ein_halbsatz():
    """Die Saetze der Website wirkten in Discord aufgesagt (Rueckmeldung 03.08.2026) -
    je Gruppe bleibt genau ein Halbsatz an der Ueberschrift. Waechst er wieder zu
    Prosa, gehoert er auf die Website, nicht in jede Bot-Antwort."""
    for satz in d_bestand.ERKLAERUNG.values():
        assert len(satz) <= 60 and "." not in satz


def test_gruppe_ohne_quellen_faellt_weg():
    """Nur Regelwerke im Bestand -> keine leeren Ueberschriften."""
    text = d_bestand.text(QUELLEN[:2])
    assert bestand.ABENTEUER not in text and bestand.REVISION not in text


def test_einzahl_bleibt_einzahl():
    """'1 Bücher' und '1 Einträge' waeren der Sorte Fehler, die jede Antwort traegt."""
    text = d_bestand.text([dict(QUELLEN[0], eintraege=1)])
    assert "**1 Buch**" in text and "1 Eintrag" in text and "1 Einträge" not in text


def test_leerer_bestand_sagt_es_ehrlich_statt_leerer_liste():
    """B1: nichts da heisst "nichts da" - keine leere Liste, die nach einem Bestand
    ohne Buecher aussieht."""
    assert d_bestand.text([]) == d_bestand.LEER
    assert d_bestand.LEER.startswith("❌")


def test_ausgabe_passt_durch_das_discord_splitting():
    """Discord kappt bei 2000 Zeichen. Ein grosser Bestand (32 Buecher) muss deshalb
    durch `antwort.teile` gehen, und die Schnitte fallen an Absatzgrenzen - keine
    zerrissene Buchzeile."""
    viele = [dict(q, titel=f"{q['titel']} {i}") for i in range(8) for q in QUELLEN]
    teile = antwort.teile(d_bestand.text(viele))
    assert len(teile) > 1, "Testdaten zu klein - der Splitpfad wird gar nicht geprueft"
    for teil in teile:
        assert len(teil) <= antwort.LIMIT
    zeilen = [z for teil in teile for z in teil.split("\n") if z.startswith("•")]
    assert len(zeilen) == len(viele), "eine Buchzeile wurde beim Split zerrissen"


def test_lange_titel_bleiben_ganz():
    """Ohne Spaltenzwang gibt es keinen Grund mehr zu kuerzen - der Titel ist die
    Antwort auf die Frage, ob das Buch drinsteht, und bricht am Handy weich um."""
    lang = "Ein wirklich ausufernd langer Buchtitel mit Untertitel und allem Drum und Dran"
    assert lang in d_bestand.zeile({"titel": lang, "sprache": "de", "edition": "2024",
                                    "inhaltsart": "regelwerk", "versions_stand": None,
                                    "eintraege": 5})


def test_website_und_discord_ordnen_dieselbe_quelle_gleich_ein():
    """Der Anti-Drift-Test. Beide Oberflaechen lesen dieselbe Gruppierung und dieselben
    Marken aus `app/bestand.py`; wer eine davon lokal nachbaut, faellt hier auf."""
    from app.charakterbogen import web

    html = web._bestand_html(QUELLEN)
    text = d_bestand.text(QUELLEN)

    # Gleiche Ueberschriften (HTML nur escaped).
    assert f"<h3>{bestand.ABENTEUER.replace('&', '&amp;')}</h3>" in html
    assert f"**{bestand.ABENTEUER}**" in text
    # Gleiche Marken je Quelle.
    for q in QUELLEN:
        marke = bestand.regelstand(q["edition"], q["versions_stand"])
        assert f">{marke}<" in html and marke in text
        assert bestand.sprachname(q["sprache"]) in html
    # Gleiche Einordnung: das Abenteuerbuch steht in BEIDEN unter Abenteuer & Settings.
    web_abenteuer = html.split(bestand.ABENTEUER.replace("&", "&amp;"))[1]
    assert "Forgotten Realms: Heroes of Faerûn" in web_abenteuer
    assert "Forgotten Realms: Heroes of Faerûn" in text.split(f"**{bestand.ABENTEUER}**")[1]


def test_liste_kommt_aus_der_datenbank_und_nur_die_metadaten(tmp_path):
    """`lies_quellen` zaehlt am echten Schema - und holt KEINEN Buchtext. Eine
    Uebersicht sagt, was im Schrank steht, nicht was drinsteht."""
    pfad = tmp_path / "bestand.sqlite"
    con = sqlite3.connect(pfad)
    con.executescript(SCHEMA.read_text(encoding="utf-8"))
    con.executemany(
        "INSERT INTO quellen (kuerzel,titel,sprache,edition,herkunft,lizenz,prioritaet,"
        "inhaltsart) VALUES (?,?,?,?,?,?,?,?)",
        [("srd-de", "SRD 5.2.1", "de", "2024", "pdf", "CC-BY-4.0", 10, "regelwerk"),
         ("rav-en", "Ravenloft", "en", "2024", "ddb", "privat", 40,
          "abenteuer_setting")])
    con.executemany(
        "INSERT INTO eintraege (quelle_id,kategorie,name_de,name_en,sprache,edition,"
        "body_md) VALUES (?,?,?,?,?,?,?)",
        [(1, "zauber", "Feuerball", None, "de", "2024", "Geheimer Regeltext."),
         (1, "zauber", "Licht", None, "de", "2024", "Noch ein Regeltext."),
         (2, "monster", None, "Strahd", "en", "2024", "SPOILER: Strahds Schwaeche ...")])
    con.commit()
    con.close()

    con = sqlite3.connect(f"file:{pfad}?mode=ro", uri=True)
    try:
        quellen = bestand.lies_quellen(con)
    finally:
        con.close()

    assert [(q["titel"], q["eintraege"]) for q in quellen] == [("SRD 5.2.1", 2),
                                                               ("Ravenloft", 1)]
    text = d_bestand.text(quellen)
    assert "SPOILER" not in text and "Regeltext" not in text
    assert "SRD 5.2.1" in text and "Ravenloft" in text


def test_uninitialisierte_datenbank_liefert_leere_liste(tmp_path):
    """Keine `quellen`-Tabelle (frische Datei) - dann sagt der Bot "kein Buch", statt
    dem Nutzer einen SQL-Fehler zu zeigen."""
    con = sqlite3.connect(tmp_path / "leer.sqlite")
    try:
        assert bestand.lies_quellen(con) == []
    finally:
        con.close()


def test_hilfe_nennt_den_befehl():
    """`/hilfe` ist "der eine Befehl, den man sich merken muss" - was dort fehlt,
    existiert fuer die Runde nicht."""
    assert "/bestand" in antwort.HILFE
