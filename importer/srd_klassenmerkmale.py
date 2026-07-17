"""2024-Klassenmerkmalsnamen DE<->EN per STRUKTUR-Abgleich aus dem Bestand (17.07.2026).

Befund (Charakterbogen-Review): Die amtlichen deutschen 2024-Merkmalsnamen stehen im
srd-de-Bestand ("3. Stufe: Angriffe umleiten"), aber nicht im Glossar - der
Charakterbogen-Uebersetzer erfand deshalb eigene Namen mit Stern ("Angriffe abwehren*"),
und Bogen und Foliant benutzten verschiedene Namen fuers selbe Merkmal.

Abgleich (strukturelle Identitaet, KEIN Uebersetzungs-Raten - Datenprinzip):
- DE: srd-de "Klassenmerkmale des X" - Ueberschriften '###### **N. Stufe: Name**',
  Sub-Features als '**_Name:_**' im Stufenabschnitt.
- EN: ddb-br-2024-en - je Merkmal EIN Eintrag 'Level N: Name' (Kontextzeile
  '*Kontext: <Klasse> > <Klasse> Features*'), Sub-Features als '***Name.***' im Body.
- Klassenbruecke DE->EN ueber das Glossar (exakt + offiziell: Moench->Monk).
- Paarung je (Klasse, Stufe) in Dokumentreihenfolge - NUR bei gleicher Anzahl;
  Sub-Features je gepaartem Merkmal ebenso. Ungleiche Gruppen werden verworfen
  und im Report genannt (lieber eine Luecke als ein falsches Paar).

Beide Quellen bilden dasselbe Regelwerk ab (SRD 5.2.1 de / Basic Rules 2024 en),
die Stufenstruktur ist identisch - dieselbe Mechanik wie die Monster-Bruecke
(seed_monster_bruecke_aus_bestand), eine Ebene hoeher.
"""
from __future__ import annotations

import re
import sqlite3

from app import glossar

QUELLE = "SRD 5.2.1 (Strukturabgleich Klassen)"

_KONTEXT = re.compile(r"^\*Kontext:\s*(.+?)\*\s*$", re.M)
_DE_STUFE = re.compile(r"^#+\s*\**\s*(\d+)\.\s*Stufe:\s*(.+?)\s*\**\s*$", re.M)
_DE_SUB = re.compile(r"\*\*_([^_\n]{2,60}?):_\*\*")
_EN_LEVEL = re.compile(r"^Level\s+(\d+):\s*(.+?)\s*$")
_EN_SUB = re.compile(r"\*\*\*([^*\n]{2,60}?)\.\*\*\*")

# Merkmalsnamen, die KEINE eigenstaendigen Begriffe sind (reine Verweise) - nicht seeden.
_STOPP_EN = {"subclass feature"}


def _kontext_teil(body: str, index: int) -> str | None:
    """Teil der Kontextzeile: index -1 = letzter ('Klassen > Moench' -> 'Moench'),
    index 0 = erster ('Monk > Monk Features' -> 'Monk')."""
    m = _KONTEXT.search(body or "")
    if not m:
        return None
    teile = [t.strip() for t in m.group(1).split(">") if t.strip()]
    try:
        return teile[index]
    except IndexError:
        return None


def _de_klassen(con: sqlite3.Connection) -> dict[str, list[tuple[int, str, str]]]:
    """{klasse_de: [(stufe, name_de, abschnitts_body), ...] in Dokumentreihenfolge}."""
    rows = con.execute(
        "SELECT e.body_md FROM eintraege e JOIN quellen q ON q.id = e.quelle_id "
        "WHERE q.kuerzel = 'srd-de' AND e.kategorie = 'klasse' "
        "AND e.name_de LIKE 'Klassenmerkmale de%' ORDER BY e.id").fetchall()
    aus: dict[str, list[tuple[int, str, str]]] = {}
    for (body,) in rows:
        klasse = _kontext_teil(body, -1)
        if not klasse:
            continue
        treffer = list(_DE_STUFE.finditer(body))
        merkmale = []
        for i, m in enumerate(treffer):
            ende = treffer[i + 1].start() if i + 1 < len(treffer) else len(body)
            merkmale.append((int(m.group(1)), m.group(2).strip(), body[m.end():ende]))
        if merkmale:
            aus[klasse] = merkmale
    return aus


def _en_klassen(con: sqlite3.Connection) -> dict[str, list[tuple[int, str, str]]]:
    """{klasse_en: [(stufe, name_en, body), ...] in Dokumentreihenfolge (id)}."""
    rows = con.execute(
        "SELECT e.name_en, e.body_md FROM eintraege e JOIN quellen q ON q.id = e.quelle_id "
        "WHERE q.kuerzel = 'ddb-br-2024-en' AND e.kategorie = 'klasse' "
        "AND e.name_en LIKE 'Level %' ORDER BY e.id").fetchall()
    aus: dict[str, list[tuple[int, str, str]]] = {}
    for name_en, body in rows:
        kopf = _EN_LEVEL.match(name_en or "")
        klasse = _kontext_teil(body, 0)
        if not kopf or not klasse:
            continue
        aus.setdefault(klasse, []).append((int(kopf.group(1)), kopf.group(2).strip(), body))
    return aus


def _klasse_en(con: sqlite3.Connection, klasse_de: str,
               en_klassen: set[str]) -> str | None:
    """Klassenbruecke DE->EN: exakter, OFFIZIELLER Glossar-Treffer, der auch WIRKLICH als
    EN-Klasse im Bestand existiert ('Magier' hat die Glossar-Kandidaten 'Mage' UND
    'Wizard' - nur 'Wizard' fuehrt Level-Eintraege)."""
    for z in glossar.lookup(con, klasse_de, richtung="de_en"):
        if z["match"] == "exakt" and z["offiziell"] and z["term_en"] in en_klassen:
            return z["term_en"]
    return None


def _belegte_de(con: sqlite3.Connection, term_en: str) -> set[str]:
    """Bereits belegte deutsche Formen eines EN-Begriffs (exakte Glossar-Zeilen beliebiger
    Herkunft ausser der eigenen - die wurde vor dem Lauf geloescht)."""
    return {z["term_de"] for z in glossar.lookup(con, term_en, richtung="en_de")
            if z["match"] == "exakt"}


def _paare_stufe(con: sqlite3.Connection,
                 de_liste: list[tuple[str, str]],
                 en_liste: list[tuple[str, str]],
                 klasse_en: str) -> tuple[list[tuple[int, int]], int]:
    """(Index-Paare, Anzahl unaufloesbarer Reste) fuer EINE Stufe. Die Positions-Annahme
    gilt nur bei GENAU einem Merkmal: srd-de sortiert innerhalb der Stufe alphabetisch
    DEUTSCH, DDB alphabetisch ENGLISCH - bei mehreren Merkmalen je Stufe entstuenden
    Kreuzpaarungen (real: 'Extra Attack' -> 'Betäubender Schlag', Pi-Lauf 17.07.2026).
    Nur BEWEISBARE Zuordnungen: (1) Struktur-Anker '<Klasse> Subclass' <-> dem einzigen
    '…-Unterklasse'-Merkmal (Endung, weil der DE-Stamm Genitiv sein kann:
    'Barbaren-Unterklasse'); (2) bereits belegte Glossar-Paare; (3) belegte SUB-Features
    identifizieren ihr Eltern-Merkmal (Schlaghagel in 'Mönchsfokus' <-> Flurry of Blows
    in 'Monk's Focus'); (4) genau EIN Rest je Seite -> Ausschlussprinzip. Unaufloesbare
    Reste werden verworfen - die sicheren Paare bleiben."""
    if len(de_liste) == 1 and len(en_liste) == 1:
        return [(0, 0)], 0
    offen_de = set(range(len(de_liste)))
    offen_en = set(range(len(en_liste)))
    paare: list[tuple[int, int]] = []

    def _fixiere(i: int, j: int) -> None:
        paare.append((i, j))
        offen_de.discard(i)
        offen_en.discard(j)

    anker_en = f"{klasse_en} Subclass".lower()
    for j in list(offen_en):
        if en_liste[j][0].strip().lower() == anker_en:
            kandidaten = [i for i in offen_de
                          if de_liste[i][0].strip().lower().endswith("-unterklasse")]
            if len(kandidaten) == 1:
                _fixiere(kandidaten[0], j)
    for j in list(offen_en):
        belegt = _belegte_de(con, en_liste[j][0])
        treffer = [i for i in offen_de if de_liste[i][0] in belegt]
        if len(treffer) == 1:
            _fixiere(treffer[0], j)
    # Sub-Feature-Anker: ein belegtes Sub-Paar gehoert zu genau EINEM Merkmal je Seite
    for j in list(offen_en):
        for sub_en in _EN_SUB.findall(en_liste[j][1]):
            belegt = _belegte_de(con, sub_en)
            treffer = [i for i in offen_de
                       if belegt & set(_DE_SUB.findall(de_liste[i][1]))]
            if len(treffer) == 1:
                _fixiere(treffer[0], j)
                break
    if len(offen_de) == 1 and len(offen_en) == 1:
        _fixiere(offen_de.pop(), offen_en.pop())
    return paare, len(offen_de) + len(offen_en)


def _nach_stufe(merkmale: list[tuple[int, str, str]]) -> dict[int, list[tuple[str, str]]]:
    aus: dict[int, list[tuple[str, str]]] = {}
    for stufe, name, body in merkmale:
        aus.setdefault(stufe, []).append((name, body))
    return aus


def finde_paare(con: sqlite3.Connection) -> tuple[list[tuple[str, str]], list[str]]:
    """[(term_en, term_de), ...] fuer Merkmale UND deren Sub-Features + Verwerfungs-Report."""
    de_alle = _de_klassen(con)
    en_alle = _en_klassen(con)
    paare: list[tuple[str, str]] = []
    report: list[str] = []
    for klasse_de, de_merkmale in sorted(de_alle.items()):
        klasse_en = _klasse_en(con, klasse_de, set(en_alle))
        if not klasse_en:
            report.append(f"{klasse_de}: keine EN-Klasse gefunden")
            continue
        de_stufen = _nach_stufe(de_merkmale)
        en_stufen = _nach_stufe(en_alle[klasse_en])
        for stufe, de_liste in sorted(de_stufen.items()):
            en_liste = [(n, b) for n, b in en_stufen.get(stufe, [])
                        if n.strip().lower() not in _STOPP_EN]
            if len(en_liste) != len(de_liste):
                report.append(f"{klasse_de} Stufe {stufe}: {len(de_liste)} DE vs. "
                              f"{len(en_liste)} EN - verworfen")
                continue
            index_paare, reste = _paare_stufe(con, de_liste, en_liste, klasse_en)
            if reste:
                report.append(f"{klasse_de} Stufe {stufe}: {reste} Merkmal(e) nicht "
                              f"eindeutig zuzuordnen - verworfen")
            for i, j in index_paare:
                name_de, body_de = de_liste[i]
                name_en, body_en = en_liste[j]
                paare.append((name_en, name_de))
                subs_de = _DE_SUB.findall(body_de)
                subs_en = _EN_SUB.findall(body_en)
                if subs_de and len(subs_de) == len(subs_en):
                    paare.extend(zip(subs_en, subs_de))
                elif subs_de or subs_en:
                    report.append(f"{klasse_de}/{name_de}: Sub-Features {len(subs_de)} DE "
                                  f"vs. {len(subs_en)} EN - verworfen")
    # dedupe (z.B. 'Attributswerterhoehung' in jeder Klasse; 'Schlaghagel' in Stufe 2+10)
    gesehen: set[tuple[str, str]] = set()
    eindeutig = []
    for p in paare:
        if p not in gesehen:
            gesehen.add(p)
            eindeutig.append(p)
    return eindeutig, report


def apostroph_varianten(term_en: str) -> list[str]:
    """DDB nutzt das typografische Apostroph (U+2019), Nutzer tippen oft ASCII -
    beide Formen belegen, damit der exakte Lookup unabhaengig davon trifft."""
    formen = {term_en, term_en.replace("’", "'"), term_en.replace("'", "’")}
    return sorted(formen)
