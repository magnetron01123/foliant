"""Was die SUCHE dem Modell zeigt (Review 28.07.2026).

Der Review fand vier Stellen, an denen die Trefferliste weniger oder Falsches lieferte,
als der Bestand hergibt — alle vier wirken direkt gegen die Verhaltensregeln:

  A1  Der Struktur-Nachfilter lief auf der bereits auf 8 gekappten Liste. Fielen dabei
      alle weg, meldete der Code HINWEIS_LEER ("Nichts im Bestand gefunden") — obwohl nur
      der Top-8-Ausschnitt geprueft war. Das System behauptete dem Modell ausgerechnet bei
      der Anti-Halluzinations-Regel etwas Falsches.
  A2  Der Spoiler-Hinweis sass nur im Detail-Abruf, obwohl schon die Trefferliste
      Volltext-Auszuege liefert (Spoiler-Schutz ist die OBERSTE Regel).
  A3  stil.py verlangt, das Feld 'zitat' woertlich auszugeben — die Suche lieferte keines.
  A4  db.py loescht den bm25-Score; das Modell konnte einen zufaelligen Body-Treffer nicht
      von einem Namenstreffer unterscheiden.

Die Negativfaelle sind hier die eigentliche Absicherung: ein zu strenger Filter ist
schlimmer als ein zu lascher, weil er als 'nicht im Bestand' beim Nutzer ankommt."""
import sqlite3
from pathlib import Path

import pytest

from app import db as adb
from app.tools import nachschlagen as ns
from app.tools import suche as su
from tests.hilfen import SCHEMA

_SCHEMA = SCHEMA
@pytest.fixture()
def bestand(tmp_path, monkeypatch):
    """12 gleichnamige Zauber (mehr als das Limit 8), davon EINER 5. Grades — der landet
    garantiert ausserhalb der ersten acht. Dazu ein Abenteuerband fuer den Spoiler-Fall."""
    pfad = tmp_path / "foliant-suchausgabe.sqlite"
    con = sqlite3.connect(pfad)
    con.executescript(_SCHEMA.read_text(encoding="utf-8"))
    con.executemany(
        "INSERT INTO quellen (kuerzel,titel,sprache,edition,herkunft,lizenz,prioritaet,"
        "inhaltsart) VALUES (?,?,?,?,?,?,?,?)",
        [("srd-de", "SRD 5.2.1 (Deutsch)", "de", "2024", "pdf", "CC-BY-4.0", 10,
          "regelwerk"),
         ("ddb-rthw-en", "Ravenloft (D&D Beyond)", "en", "2024", "ddb", "privat", 40,
          "abenteuer_setting")])
    zeilen = [
        # 11 Zauber 1. Grades + einer 5. Grades. Alle tragen denselben Suchbegriff im
        # NAMEN, damit die Volltextsuche sie alle findet.
        *[(1, "zauber", f"Pruefflamme {i}", None, "de", "2024", str(i),
           f"*Kontext: Zauber*\n\n_Hervorrufungszauber 1. Grades_\n\nPruefflamme {i} "
           f"verursacht {i}W6 Schaden.") for i in range(1, 12)],
        (1, "zauber", "Pruefflamme 12", None, "de", "2024", "12",
         "*Kontext: Zauber*\n\n_Hervorrufungszauber 5. Grades_\n\nPruefflamme 12 "
         "verursacht 12W6 Schaden."),
        # Abenteuerband: taucht bei der Suche nach 'Domaene' auf.
        (2, "regel", None, "Domain Secrets", "en", "2024", None,
         "The dark lord of this Domaene guards a secret about the mist."),
        # Reiner Body-Treffer: der NAME hat mit 'Domaene' nichts zu tun.
        (1, "regel", "Nebelwanderung", None, "de", "2024", "7",
         "*Kontext: Regeln*\n\nWer eine Domaene verlaesst, verliert die Orientierung."),
        # Befund 30.07.2026: laengerer Name, dessen ANFANG ein eigenstaendiger Begriff
        # ist. 'Elf' ist Praefix von 'Elfenruestung' - aber keine Anfrage danach.
        (1, "gegenstand", "Elfenruestung", "Elven Chain", "de", "2024", "20",
         "*Kontext: Magische Gegenstaende*\n\nEine Kettenruestung aus Mithral. Der "
         "Begriff Mithral kommt hier NUR im Fliesstext vor, nie im Namen."),
    ]
    con.executemany(
        "INSERT INTO eintraege (quelle_id,kategorie,name_de,name_en,sprache,edition,seite,"
        "body_md) VALUES (?,?,?,?,?,?,?,?)", zeilen)
    con.commit()
    con.execute("INSERT INTO eintraege_fts(eintraege_fts) VALUES('rebuild')")
    con.commit()
    con.close()
    monkeypatch.setattr(adb, "standard_pfad", lambda: pfad)
    return pfad


def test_facettenfilter_erzeugt_keinen_falschen_leerbefund(bestand):
    """A1 — DER Kernfall: 'Pruefflamme' trifft 12 Eintraege, aber nur der zwoelfte ist
    5. Grades. Vor dem Fix lief der Gradfilter auf den ersten acht, fand nichts und der
    Code meldete 'Nichts im Bestand gefunden' — fuer einen Eintrag, den es gibt."""
    r = su.foliant_suche_bestand("Pruefflamme", grad=5)
    namen = [t["name_de"] for t in r["treffer"]]
    assert namen == ["Pruefflamme 12"], f"5.-Grad-Zauber nicht gefunden: {namen}"
    assert "hinweis" not in r or "Nichts im Bestand" not in r.get("hinweis", "")


def test_leerer_filtertreffer_ist_kein_nicht_im_bestand(bestand):
    """Gegenprobe: passt WIRKLICH kein Treffer auf den Filter, muss der Hinweis trotzdem
    klarstellen, dass der Suchbegriff getroffen hat — sonst meldet das Modell faelschlich
    eine Fehlanzeige."""
    r = su.foliant_suche_bestand("Pruefflamme", grad=9)
    assert r["treffer"] == []
    hinweis = r.get("hinweis", "")
    assert "Nichts im Bestand" not in hinweis
    assert "KEIN" in hinweis and "Filter" in hinweis


def test_abenteuertreffer_ist_schon_in_der_trefferliste_markiert(bestand):
    """A2 — Spoiler-Schutz ist die oberste Regel. Die Trefferliste liefert Volltext, also
    muss die Kennzeichnung dort stehen und nicht erst im Detail-Abruf."""
    r = su.foliant_suche_bestand("Domaene")
    aus_abenteuer = [t for t in r["treffer"] if t.get("inhaltsart") == "abenteuer_setting"]
    assert aus_abenteuer, "Abenteuertreffer nicht markiert"
    assert "hinweis_inhaltsart" in r
    assert "Spoiler" in r["hinweis_inhaltsart"]


def test_suchtreffer_traegt_zitat_und_anzeigename(bestand):
    """A3/A6 — 'zitat' woertlich ausgeben ist Prompt-Pflicht, und Deutsch-first darf nicht
    erst im Detail greifen."""
    t = su.foliant_suche_bestand("Pruefflamme")["treffer"][0]
    assert t["zitat"].startswith("Quelle: SRD 5.2.1 (Deutsch)")
    assert "Regelversion: 2024" in t["zitat"]
    assert "S. " in t["zitat"]                     # Seite ist gesetzt -> muss drinstehen
    assert t["anzeige_name"]


def test_relevanz_trennt_namenstreffer_von_texterwaehnung(bestand):
    """A4 — 'Nebelwanderung' erwaehnt 'Domaene' nur im Fliesstext; sein Name hat mit der
    Anfrage nichts zu tun. Ohne dieses Signal sah das Modell beide Treffer als gleichwertig
    (der Beholder-Fall: 8 plausible Treffer fuer etwas, das es nicht gibt)."""
    r = su.foliant_suche_bestand("Domaene")
    nach_namen = {t["name_de"] or t["name_en"]: t["relevanz"] for t in r["treffer"]}
    assert nach_namen.get("Nebelwanderung") == "nur_im_text"
    # Und wenn KEIN Treffer am Namen passt, muss die Suche das ausdruecklich sagen:
    assert r.get("hinweis_geringe_relevanz")


def test_detail_traegt_eintrag_id_und_quelle_kuerzel(bestand):
    """A7 — der Rundlauf war einseitig: ohne eintrag_id konnte das Modell den gelieferten
    Eintrag nicht erneut referenzieren, ohne quelle_kuerzel nicht in derselben Quelle
    weitersuchen (die Suche verlangt dort das Kuerzel, nicht den Titel)."""
    d = ns.foliant_hol_eintrag("zauber", "Pruefflamme 12")
    assert d["gefunden"] is True
    assert isinstance(d["eintrag_id"], int)
    assert d["quelle_kuerzel"] == "srd-de"
    # Die ID muss den Eintrag auch wirklich wieder aufloesen:
    assert ns.foliant_hol_eintrag("zauber", eintrag_id=d["eintrag_id"])["name_de"] == "Pruefflamme 12"


# --------------------------------------------------- Nachzug aus dem Audit 28.07.2026
# Drei Luecken, die beim Nachpruefen der Phase 1 auffielen: A2 und A6 wirkten NUR im
# Suchpfad, A5 im Facetten-Pfad gar nicht.

def test_kandidatenliste_des_detailpfads_ist_markiert_und_deutsch(bestand):
    """A2/A6 — der schwerste der drei. Bei Mehrdeutigkeit liefert foliant_hol_eintrag eine
    `kandidaten`-Liste MIT Auszug aus dem Bestand; die trug weder die Abenteuer-
    Kennzeichnung noch den Deutsch-first-Namen. Gemessen am echten Bestand kamen so
    Auszuege aus Abenteuerbaenden voellig unmarkiert beim Modell an - genau der
    Fehlermodus, den A2 beseitigen sollte, nur eine Tuer weiter."""
    d = ns.foliant_hol_eintrag("regel", "Domaene")
    kandidaten = d.get("kandidaten") or d.get("vorhandene_fassungen") or []
    assert kandidaten, f"kein mehrdeutiger Fall erzeugt: {d.get('gefunden')}"
    aus_abenteuer = [k for k in kandidaten if k.get("inhaltsart") == "abenteuer_setting"]
    assert aus_abenteuer, "Abenteuer-Kandidat nicht markiert"
    assert "Spoiler" in (d.get("hinweis_inhaltsart") or "")
    assert all(k.get("anzeige_name") for k in kandidaten), "Deutsch-first fehlt"


def test_detail_hinweis_wird_nicht_von_der_zaehlung_ueberschrieben(bestand):
    """Der Sammelhinweis ('N Treffer stammen aus...') darf den spezifischeren Hinweis des
    gelieferten Eintrags ('DIESER Eintrag stammt aus...') nicht verdraengen."""
    d = ns.foliant_hol_eintrag("regel", "Domain Secrets")
    assert d["gefunden"] is True
    assert d.get("inhaltsart") == "abenteuer_setting"
    assert "Dieser Eintrag" in d["hinweis_inhaltsart"]


def test_facettenpfad_meldet_die_gekuerzte_menge(bestand):
    """A5 — 11 der 12 Pruefflammen sind 1. Grades, gezeigt werden 8. Die Zaehlung stand
    HINTER dem Kappen, war damit per Konstruktion gleich der Anzeigemenge, und der
    hinweis_gekuerzt konnte nie feuern: die Liste kuerzte still."""
    r = su.foliant_suche_bestand("Pruefflamme", grad=1)
    assert len(r["treffer"]) == 8
    assert r["anzahl_gesamt"] == 11
    assert "mindestens 11" in r["hinweis_gekuerzt"]


# ------------------------------------------------- Nachzug aus der Review 30.07.2026
# A4 zog die Namensrelevanz in den SUCHpfad. Der DETAILpfad - der verbindlicher
# antwortet, weil er einen einzelnen Eintrag als DIE Auskunft ausgibt - hatte sie nicht.

def test_detailabruf_bestaetigt_keinen_kurzen_praefix_als_namenstreffer(bestand):
    """_name_score gab JEDEM Praefix 100.0, ohne Mindestlaenge: 'Elf' war damit ein
    voller Namenstreffer auf 'Elfenruestung'. Der Detailpfad lieferte den Fremdeintrag
    als sauber zitierte Auskunft auf eine nicht gestellte Frage aus - genau die
    Fehlerform, gegen die B1 antritt, nur schwerer zu bemerken als eine Fehlanzeige."""
    d = ns.foliant_hol_eintrag("gegenstand", "Elf")
    assert d.get("gefunden") is not True, \
        f"Praefix als Treffer bestaetigt: {d.get('anzeige_name')}"


def test_wortriss_bleibt_ein_namenstreffer(bestand):
    """Gegenprobe und Grund, warum der Praefix-Kurzschluss NICHT durch eine Mindestlaenge
    ersetzt wurde: die echten Faelle (Wortrisse, OCR-Verstuemmelung um ein bis zwei
    Zeichen) traegt fuzz.ratio ohnehin - ein Praefix ab rund 82 % Namensdeckung liegt
    ueber der Schwelle. Faellt dieser Test, war die Streichung zu grob."""
    assert ns.foliant_hol_eintrag("gegenstand", "Elfenruestun")["gefunden"] is True
    assert ns.foliant_hol_eintrag("regel", "Nebelwanderun")["gefunden"] is True


def test_einzelner_kandidat_wird_nicht_ungeprueft_geliefert(bestand):
    """Der Sonderzweig 'genau ein FTS-Kandidat -> liefern' umging das Relevanzgate
    vollstaendig. Er ist gestrichen; ein Einzelkandidat muss dieselbe Schranke nehmen wie
    jeder andere. 'Mithral' kommt nur im FLIESSTEXT der Elfenruestung vor."""
    d = ns.foliant_hol_eintrag("gegenstand", "Mithral")
    assert d.get("gefunden") is not True, \
        f"Body-Erwaehnung als Treffer bestaetigt: {d.get('anzeige_name')}"


def test_fuzzy_namenspfad_ersetzt_die_angefragte_edition_nicht(bestand):
    """V5 galt nur im exakt-Zweig. Im Relevanz-Zweig darunter fehlte die Editionspruefung,
    die eine Zeile hoeher stand: eine AUSDRUECKLICH angefragte Regelversion wurde still
    durch die 2024-Fassung ersetzt - ohne 'hinweis_alter_stand', weil der gelieferte
    Eintrag ja 2024 war. Der Nutzer bekam die falsche Regelversion ohne jedes Signal."""
    d = ns.foliant_hol_eintrag("regel", "Nebelwanderun", edition="2014")
    assert d.get("gefunden") is not True, \
        f"2024-Fassung fuer eine 2014-Anfrage geliefert: {d.get('edition')}"
