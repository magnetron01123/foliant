# DDB-Abgleich (rein lesend)

Prüfe, ob der Bestand noch zu dem passt, was bei D&D Beyond gekauft ist. **Nichts
importieren, nichts ändern** — dieser Durchgang stellt nur fest.

**Wenn nichts zu melden ist, ende ohne Ausgabe.** Ein Bericht, der monatlich „alles in
Ordnung" sagt, wird nach dem dritten Mal nicht mehr gelesen.

## Ablauf

1. **Was liegt im Bestand?**
   ```
   ssh $(PI) 'cd ~/foliant && docker compose exec -T foliant python -m app.admin status'
   ```
   (`PI` steht in der gitignorierten `.env`; das Muster steht im `Makefile`.)

2. **Was liefe ein?** Trockenlauf, ohne jeden Schreibvorgang:
   ```
   ssh $(PI) 'cd ~/foliant && docker compose exec -T foliant python -m app.admin ddb-import-all --dry-run'
   ```

3. **Vergleichen** und genau drei Fälle unterscheiden:
   - **Nichts Neues** → lautlos enden.
   - **Gekaufte Bücher fehlen im Bestand** → melden: welche, wie viele Einträge zu
     erwarten sind, und der Hinweis, dass `/import` (Fall B) sie mit Freigabe einspielt.
     **Nicht selbst importieren.**
   - **Cobalt-Cookie abgelaufen** (401/403) → melden, dass David ihn erneuern muss.
     **Keine Wiederholungsversuche:** Der Client wiederholt 401/403 bewusst nie, weil ein
     abgelaufener Token durch Nachfragen nicht gültiger wird (SPEC O5).

## Warum das überhaupt geprüft wird

Ein gekauftes Buch, das nie importiert wurde, ist im laufenden Betrieb **unsichtbar**:
Foliant antwortet ehrlich „nicht im Bestand", und das sieht wie eine korrekte Auskunft aus.
Nur der Abgleich zeigt den Unterschied zwischen „gibt es nicht" und „haben wir, aber nie
eingelesen".

## Grenzen

Die DDB-Endpunkte sind undokumentiert und können ohne Vorwarnung brechen. Ein Fehler hier
ist ein Befund über die Schnittstelle, kein Grund für Umwege oder Hilfskonstruktionen —
melden und stehen lassen.
