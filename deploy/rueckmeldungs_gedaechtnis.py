"""Der Sichtungsstand als Zahlen - fuer den Rueckmeldungs-Durchgang (O4/M5).

Drei Dinge, die eine Freigabekarte braucht und die sonst niemand ausrechnet:
der Wiederholungszaehler je Regel-ID, die offenen `spaeter`-Befunde und die frueher
abgelehnten Vorschlaege. Alle drei stecken in `config/rueckmeldungen_stand.json`, verteilt
ueber verschachtelte Listen.

WARUM ALS PROGRAMM UND NICHT VON HAND: Der Zaehler traegt eine Doktrin - eine Regel, die
zum dritten Mal bricht, ist kein Modellfehler mehr, sondern eine Regel, die im falschen
Kanal sitzt. Diese Grenze loest die `Achtung`-Zeile der Karte aus. Verzaehlt sich der
Durchgang, faellt der Ausloeser still aus, und zwar unbeaufsichtigt um 18:07 - niemand
sieht zu. Eine Zahl, an der eine Entscheidung haengt, gehoert nicht in eine Kopfrechnung.

Ausgabe tab-getrennt und zeilenweise wie deploy/discord_api.py, erste Spalte ist die
Satzart:

    marke          <iso-zeitpunkt>
    wiederholung   <regel-id>  <anzahl>  <zuletzt>
    offen          <datum>  <regel-ids>  <grund>  <was>
    abgelehnt      <datum>  <regel-ids>  <grund>  <was>

    python3 deploy/rueckmeldungs_gedaechtnis.py        (oder: make gedaechtnis)

Gelesen wird nur - die Datei schreibt der Durchgang selbst, damit die Aenderung im Diff
steht (`_pflege` in der JSON).
"""
from __future__ import annotations

import collections
import json
import pathlib
import sys

STAND = pathlib.Path(__file__).resolve().parents[1] / "config/rueckmeldungen_stand.json"


def lies(pfad: pathlib.Path = STAND) -> dict:
    return json.loads(pfad.read_text(encoding="utf-8"))


def wiederholungen(stand: dict) -> dict[str, tuple[int, str]]:
    """Je Regel-ID: wie oft sie bisher gebrochen hat und wann zuletzt.

    Ein Befund mit vier IDs zaehlt fuer jede einzeln - er hat ja auch jede verletzt.
    Gezaehlt werden BEFUNDE, nicht Durchgaenge: Zwei Befunde am selben Tag gegen dieselbe
    Regel sind zwei Brueche, und genau das soll die Doktrin sehen."""
    anzahl: collections.Counter[str] = collections.Counter()
    zuletzt: dict[str, str] = {}
    for durchgang in stand["durchgaenge"]:
        for befund in durchgang["befunde"]:
            for regel in befund["regeln"]:
                anzahl[regel] += 1
                zuletzt[regel] = max(zuletzt.get(regel, ""), durchgang["datum"])
    return {r: (n, zuletzt[r]) for r, n in anzahl.items()}


def mit_entscheidung(stand: dict, welche: str) -> list[dict]:
    """Alle Befunde einer Entscheidung, juengste zuerst - `spaeter` fuer die offenen
    Posten, `nein` fuer die Wiedervorlage-Warnung."""
    treffer = [
        {"datum": d["datum"], "regeln": b["regeln"],
         "grund": b.get("grund", ""), "was": b["was"]}
        for d in stand["durchgaenge"] for b in d["befunde"]
        if b.get("entscheidung") == welche
    ]
    return sorted(treffer, key=lambda t: t["datum"], reverse=True)


def _zeile(*felder: object) -> str:
    # Tabs trennen, also duerfen die Felder keine tragen. Zeilenumbrueche in `was`
    # wuerden einen Satz zu zwei Saetzen machen - beides still und beides falsch.
    return "\t".join(str(f).replace("\t", " ").replace("\n", " ") for f in felder)


def main() -> int:
    stand = lies()
    zeilen = [_zeile("marke", stand["zuletzt_gesichtet_bis"])]

    # Absteigend nach Anzahl: Wer dreimal bricht, steht oben - dort wird hingesehen.
    for regel, (anzahl, zuletzt) in sorted(
            wiederholungen(stand).items(), key=lambda p: (-p[1][0], p[0])):
        zeilen.append(_zeile("wiederholung", regel, anzahl, zuletzt))

    for art, satzart in (("spaeter", "offen"), ("nein", "abgelehnt")):
        for t in mit_entscheidung(stand, art):
            zeilen.append(_zeile(satzart, t["datum"], ",".join(t["regeln"]),
                                 t["grund"], t["was"]))

    print("\n".join(zeilen))
    return 0


if __name__ == "__main__":
    sys.exit(main())
