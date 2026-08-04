# DDB-Abgleich (rein lesend)

Prüfe, ob der Bestand noch zu dem passt, was bei D&D Beyond gekauft ist. **Nichts
importieren, nichts ändern** — dieser Durchgang stellt nur fest.

**Wenn nichts zu melden ist, ende ohne Ausgabe.** Ein Bericht, der monatlich „alles in
Ordnung" sagt, wird nach dem dritten Mal nicht mehr gelesen.

## Ablauf

1. **Bestand und Trockenlauf holen** — beides rein lesend, in einem Aufruf:
   ```
   make ddb-abgleich-pi
   ```
   Zeigt erst `admin status` (was liegt drin), dann `admin ddb-import-all --dry-run` (was
   liefe ein). Das SSH-Ziel löst das Makefile aus der gitignorierten `.env` auf — **nie
   selbst ein `ssh`-Kommando bauen**, der Hostname gehört in keine versionierte Datei.

   **Bewerte die Ausgabe, nicht den Exitcode.** „Keine DDB-Artefakte unter … — erst
   'ddb-exporter sync' laufen lassen" ist ein **normaler Zustand** und **kein Befund**:
   Die Artefakte entstehen erst beim Export und liegen zwischen zwei Importen nicht
   herum. Ein echter Fehler steht im Klartext in der Ausgabe.

2. **Vergleichen** und genau drei Fälle unterscheiden:
   - **Nichts Neues** → lautlos enden, ohne Ausgabe und ohne Benachrichtigung.
   - **Gekaufte Bücher fehlen im Bestand** → melden: welche, wie viele Einträge zu
     erwarten sind, und der Hinweis, dass der geführte Import (`import.md`, Fall B) sie
     mit Freigabe einspielt. **Nicht selbst importieren.**
   - **Cobalt-Cookie abgelaufen** (401/403) → melden, dass David ihn erneuern muss.
     **Keine Wiederholungsversuche:** Der Client wiederholt 401/403 bewusst nie, weil ein
     abgelaufener Token durch Nachfragen nicht gültiger wird (SPEC O5).

   In beiden Fundfällen: **eine** Push-Benachrichtigung, ein Satz, das Handlungsbedürftige
   zuerst — *„2 gekaufte DDB-Bücher fehlen im Bestand"* bzw. *„DDB-Cookie abgelaufen,
   erneuern"*. David sitzt nicht davor; ohne die Meldung erfährt er es nie.

## Warum das überhaupt geprüft wird

Ein gekauftes Buch, das nie importiert wurde, ist im laufenden Betrieb **unsichtbar**:
Foliant antwortet ehrlich „nicht im Bestand", und das sieht wie eine korrekte Auskunft aus.
Nur der Abgleich zeigt den Unterschied zwischen „gibt es nicht" und „haben wir, aber nie
eingelesen".

## Grenzen

Die DDB-Endpunkte sind undokumentiert und können ohne Vorwarnung brechen. Ein Fehler hier
ist ein Befund über die Schnittstelle, kein Grund für Umwege oder Hilfskonstruktionen —
melden und stehen lassen.
