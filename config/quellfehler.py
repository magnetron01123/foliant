"""Register der BEKANNTEN FEHLER IN DEN QUELLEN selbst - kuratiert, mit Beleg.

WOFUER: Ein Bestandseintrag gibt seine Quelle treu wieder - auch dann, wenn die Quelle
sich irrt. Das offizielle deutsche SRD 5.2.1 druckt auf S. 302 "TP 287 (23W12+161)"; die
Klammerformel ergibt 310,5, nicht 287. Der Import hat nichts falsch gemacht, das Buch hat
sich verrechnet. Fuer genau diese Faelle steht hier, WAS falsch ist, WAS stattdessen gilt
und WORAUS das belegt ist.

DIE ZWEI REGELN, die dieses Register von jedem anderen Werkzeug im Repo trennen:

1. ES AENDERT KEINEN TEXT. `body_md` bleibt Wort fuer Wort, wie die Quelle es druckt. Eine
   stille Korrektur stuende in keinem Diff, waere beim naechsten Re-Import weg und liesse
   den Bestand etwas sagen, was die Quelle nicht sagt. Die Korrektur steht NEBEN dem Text
   (Ausgabefeld `hinweis_quellfehler`), nie an seiner Stelle - dieselbe Zusage wie bei
   Errata (V9), nur ohne amtliches Korrekturdokument.
2. JEDER EINTRAG IST AUS DEM BESTAND SELBST BELEGT. Kein Trainingswissen, keine Websuche.
   Ist der richtige Wert nicht im Bestand nachweisbar, gehoert der Fall NICHT hierher -
   dann bleibt es beim ehrlichen "die Quelle sagt das so" (Regel 1).

ABGRENZUNG zu den drei benachbarten Mustern - das Kriterium ist, WO der Schaden entstand:
  * `namensreparatur.KURATIERTE_TITEL` / `import_markdown.BEREINIGUNG`: Der Schaden entstand
    beim EINLESEN (OCR, PDF-Textschicht). Die Reparatur stellt wieder her, was gedruckt
    steht - deshalb darf sie den Text anfassen. Hier steht das Gegenteil: gedruckt ist es
    wirklich so.
  * `inhaltsart = 'errata'`: Der RECHTEINHABER hat korrigiert. Ein Eintrag hier ist KEIN
    Erratum und darf nie als eines auftreten - sonst behauptete der Bestand eine amtliche
    Korrektur, die es nicht gibt (fuer den Vampir-Vertrauten existiert keine).
  * `config/qualitaet_basis.json`: zaehlt Maengel, aendert an der Auskunft nichts. Das
    Register ist zugleich die gepruefte Ausnahmeliste der TP-Formel-Pruefung in
    `admin check` - Beleg, kein Deckel: findet die Pruefung eine Abweichung OHNE
    Registereintrag, bricht sie den Deploy.

SCHLUESSEL ist (quelle, name), NICHT `eintrag_id`: IDs sind zwischen Mac und Pi
verschieden und ueberleben keinen Re-Import.

WAS HIER NIE HINEINGEHOERT: eine Funktion, die Text ersetzt. Wer das einbaut, hat aus dem
Beleg einen Patcher gemacht, und der Bestand sagt etwas, was seine Quelle nicht sagt.
"""
from __future__ import annotations

from typing import NamedTuple


class Quellfehler(NamedTuple):
    """Ein belegter Fehler in einer Quelle. `wortlaute` ist zugleich der Selbsttest: steht
    einer davon nicht mehr im Bestand, ist der Eintrag ueberholt und wird gemeldet, nicht
    still ignoriert (dieselbe Mechanik wie GEPRUEFTE_HOMONYME).

    MEHRERE Wortlaute, weil EIN Quellfehler sich an mehreren Stellen zeigen kann: Der
    kaputte open5e-Datensatz des Oktopus liefert zwei unmoegliche Attributswerte. Sie
    einzeln zu registrieren wuerde denselben Beleg zweimal fuehren."""

    quelle: str                  # Quellen-Kuerzel
    name: str                    # Eintragsname, wie er im Bestand steht
    seite: str | None            # Seite in DIESER Quelle, wo der Fehler steht
    wortlaute: tuple[str, ...]   # die falschen Ausschnitte, WOERTLICH aus body_md
    richtig: str                 # der belegte korrekte Wert
    beleg: str                   # woraus im BESTAND er belegt ist (inkl. Rechenweg)
    wirkung: str                 # was ohne diesen Hinweis in der Auskunft schiefginge

    def steht_noch_im_bestand(self, body: str | None) -> bool:
        return all(w in (body or "") for w in self.wortlaute)

    def deckt_ab(self, fundstelle: str) -> bool:
        """Meldet die Logikpruefung genau diesen bekannten Fehler?"""
        return any(w in fundstelle or fundstelle in w for w in self.wortlaute)


BEKANNTE_QUELLFEHLER: tuple[Quellfehler, ...] = (
    Quellfehler(
        quelle="srd-de",
        name="Balor",
        seite="302",
        wortlaute=("**TP** 287 (23W12+161)",),
        richtig="287 (23W12+138)",
        beleg="Die englische Fassung im Bestand (open5e-srd-2024, 'Balor') fuehrt "
              "'HP 287 (23d12 + 138)', und das offizielle WotC-Erratum im Bestand "
              "(errata-mm-2025-en, 'Balor') schreibt woertlich 'HP: 287 (23d12 + 138) "
              "[was 300 (24d12 + 144)]'. Rechenweg: 23 x 6,5 + 138 = 287,5 -> 287 stimmt; "
              "23 x 6,5 + 161 = 310,5 stimmt nicht. Falsch ist also NUR die Klammerformel, "
              "der Gesamtwert 287 ist richtig.",
        wirkung="Wer die Trefferpunkte auswuerfelt statt den Durchschnitt zu nehmen, "
                "bekommt einen um ~23 TP zu starken Balor.",
    ),
    Quellfehler(
        quelle="srd-de",
        name="Vampir-Vertrauter",
        seite="381",
        wortlaute=("**TP** 65 (10W8+30)",),
        richtig="65 (10W8+20)",
        beleg="Die englische Fassung im Bestand (open5e-srd-2024, 'Vampire Familiar') "
              "fuehrt 'HP 65 (10d8 + 20)'. Gegenprobe am Statblock selbst: KON 15 (+2) "
              "x 10 Trefferwuerfel = +20. Rechenweg: 10 x 4,5 + 20 = 65 stimmt; "
              "10 x 4,5 + 30 = 75 stimmt nicht. Kein amtliches Erratum - deshalb ist das "
              "hier ein Quellfehler und keine Revision.",
        wirkung="Wie beim Balor: ausgewuerfelte Trefferpunkte fallen im Schnitt 10 TP zu "
                "hoch aus.",
    ),
    Quellfehler(
        quelle="open5e-srd-2024",
        name="Octopus",
        seite=None,
        wortlaute=("CON 0 (-5)", "CHA -3 (-7)"),
        richtig="CON 11 (+0), CHA 4 (-3), Rettungswurf Kon +0",
        beleg="Der vollstaendige deutsche Oktopus-Statblock steht im Bestand - im Body des "
              "srd-de-Eintrags 'Nashorn' (S. 399, zweiter Statblock der Druckspalte): "
              "'**Sta** 4 -3, **GeS** 15 +2, **Kon** 11 +0, **Int** 3 -4, **WeI** 10 +0, "
              "**Cha** 4 -3'. Ein Attributswert von 0 bzw. -3 ist ausserdem regelseitig "
              "unmoeglich (Wertebereich 1-30), und 'Con +30' als Rettungswurf passt zu "
              "keinem Uebungsbonus. RK 12, TP 3 (1W6) und HG 0 im open5e-Eintrag stimmen.",
        wirkung="Ein Statblock, mit dem man wuerfeln kann und der grob falsch ist: "
                "Konstitutions-Rettungswurf +30 statt +0.",
    ),
)


def quellfehler_zu(kuerzel: str | None, name_de: str | None,
                   name_en: str | None) -> Quellfehler | None:
    """Der Registereintrag zu einem Bestandseintrag, oder None.

    Bewusst ein exakter Namensvergleich ohne Glossar-Bruecke: Das Register benennt EINEN
    konkreten Eintrag EINER Quelle. Eine unscharfe Zuordnung haenge den Hinweis an den
    falschen Statblock - und ein falscher Korrekturhinweis ist schlimmer als keiner."""
    if not kuerzel:
        return None
    namen = {n for n in (name_de, name_en) if n}
    for eintrag in BEKANNTE_QUELLFEHLER:
        if eintrag.quelle == kuerzel and eintrag.name in namen:
            return eintrag
    return None
