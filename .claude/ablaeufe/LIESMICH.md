# Abläufe für wiederkehrende Arbeit

Diese Dateien beschreiben Arbeitsabläufe, die **zeitgesteuert von selbst laufen** — als
geplante Aufgaben in Claude Code auf Davids Mac (`~/.claude/scheduled-tasks/`). Sie sind
**keine** Slash-Befehle: David soll nichts tippen müssen.

Der Prompt jeder Aufgabe verweist auf die Datei hier, statt den Ablauf zu kopieren. So
liegt er versioniert im Repo, ist im PR reviewbar, und eine Änderung am Ablauf wirkt beim
nächsten Lauf — ohne die Aufgabe anzufassen.

| Datei | Läuft | Was sie tut |
|---|---|---|
| `rueckmeldungen.md` | 2×/Woche | 👎/👍 der Runde auswerten, gegen die Doku prüfen, Freigabekarten vorlegen |
| `ddb-abgleich.md` | monatlich | Fehlen gekaufte DDB-Bücher im Bestand? Cobalt-Cookie noch gültig? |
| `egress-abgleich.md` | monatlich | Passen die IP-Bereiche in `app/zugriff.py` noch zu Anthropics Liste? |
| `import.md` | auf Zuruf | Geführter Quellen-Import (neue PDFs / DDB) — kein Zeitplan, David stößt ihn an |

## Zwei Regeln, die für alle gelten

1. **Stillschweigen bei Fundlosigkeit.** Eine Aufgabe, die regelmäßig „alles in Ordnung"
   meldet, wird nach dem dritten Mal weggeklickt — und dann auch die Meldung, die zählt.
   Technisch hängt das an **zwei** Schaltern, und beide müssen stimmen:
   - Die Aufgaben laufen mit **abgeschalteter Abschluss-Benachrichtigung**
     (`notifyOnCompletion: false`) — sonst meldet die App jeden Lauf, egal wie still er
     endete.
   - Bei einem Fund meldet sich die Aufgabe deshalb **selbst**, mit einer
     Push-Benachrichtigung in einem Satz: *was gefunden wurde und was David tun muss.*
     Ohne diesen zweiten Schalter wäre die Aufgabe nicht still, sondern stumm — und ein
     Befund, den niemand sieht, ist kein Befund.
2. **Analyse automatisch, Änderung nur nach Freigabe.** Die Aufgaben lesen, prüfen und
   legen vor. Sie legen keinen Branch an und ändern nichts. Bei der Feedback-Auswertung ist
   das nicht Vorsicht, sondern strukturell nötig: Dort bewertet Claude Antworten und würde
   danach die Regeln ändern, die sein eigenes Verhalten steuern.

**Warum lokal und nicht in der Cloud:** Der Pi steht im Heimnetz. Nur eine Aufgabe, die auf
Davids Mac läuft, erreicht ihn per SSH. Sie läuft, während die App offen ist; war sie zur
fälligen Zeit zu, holt die Aufgabe den Lauf beim nächsten Start nach.

**Warum die Zugangsdaten nirgends hier stehen:** `PI` kommt aus der gitignorierten `.env`
(Muster im `Makefile`), der Discord-Token bleibt in der Container-Umgebung auf dem Pi.
