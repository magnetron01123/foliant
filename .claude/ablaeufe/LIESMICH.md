# Abläufe für wiederkehrende Arbeit

Diese Dateien beschreiben wiederkehrende Arbeitsabläufe. Ein Teil davon läuft
**zeitgesteuert von selbst** — als geplante Aufgabe in Claude Code auf Davids Mac
(`~/.claude/scheduled-tasks/`); die übrigen stößt David an. Welcher Ablauf wie läuft,
steht in der Spalte „Läuft". Slash-Befehle sind es in keinem Fall.

> Die Spalte „Läuft" ist eine Behauptung über den Zustand von Davids Mac, nicht über
> dieses Repo. Steht dort „geplant", muss dazu eine registrierte Aufgabe existieren —
> ein Ordner unter `~/.claude/scheduled-tasks/` allein genügt nicht, der kann seine
> Registrierung verlieren, ohne dass es auffällt. Im Zweifel gegenprüfen.

Der Prompt jeder Aufgabe verweist auf die Datei hier, statt den Ablauf zu kopieren. So
liegt er versioniert im Repo, ist im PR reviewbar, und eine Änderung am Ablauf wirkt beim
nächsten Lauf — ohne die Aufgabe anzufassen.

| Datei | Läuft | Was sie tut |
|---|---|---|
| `rueckmeldungen.md` | geplant, 2×/Woche | 👎/👍 der Runde auswerten, gegen die Doku prüfen, Freigabekarten vorlegen |
| `ddb-abgleich.md` | auf Zuruf | Fehlen gekaufte DDB-Bücher im Bestand? Cobalt-Cookie noch gültig? |
| `egress-abgleich.md` | auf Zuruf | Passen die IP-Bereiche in `app/zugriff.py` noch zu Anthropics Liste? |
| `import.md` | auf Zuruf | Geführter Quellen-Import (neue PDFs / DDB) — kein Zeitplan, David stößt ihn an |

Die beiden Abgleiche liefen bis August 2026 monatlich als geplante Aufgabe. David hat sie
am 29.08.2026 abgeschaltet; die Abläufe hier bleiben gültig und werden bei Bedarf von Hand
angestoßen. Beim Egress-Abgleich heißt das: Ändert Anthropic seine IP-Bereiche, fällt es
erst auf, wenn jemand nachsieht oder der Connector nicht mehr durchkommt.

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
