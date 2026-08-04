# Abgleich der Anthropic-Egress-IPs (rein lesend)

Prüfe, ob die im Code hinterlegten Anthropic-Egress-Bereiche noch zu Anthropics
veröffentlichter Liste passen. **Nichts ändern** — dieser Durchgang stellt nur fest.

**Wenn nichts abweicht, ende ohne Ausgabe.**

## Warum das geprüft wird

`app/zugriff.py` lässt nur Anfragen aus Anthropics Egress-Bereichen an den MCP-Pfad. Die
Liste steht **fest im Code** (Quelle im Modul-Docstring: die Doku-Seite zu den
API-IP-Adressen, gelesen am 11.07.2026, mit der Zusage „will not change without notice").

Ändert Anthropic diese Bereiche, sperrt der eigene Server **Claude aus** — und zwar
still: Der Connector meldet nur einen Verbindungsfehler, nichts deutet auf die
IP-Allowlist. Am Spieltisch sieht das aus, als wäre Foliant kaputt. Genau deshalb ist der
Abgleich billig und der Ausfall teuer.

## Ablauf

1. Die aktuelle Liste von Anthropics Doku-Seite holen
   (`https://platform.claude.com/docs/en/api/ip-addresses`).
2. Gegen die Bereiche in `app/zugriff.py` halten — IPv4 **und** IPv6.
3. Drei Fälle:
   - **Identisch** → lautlos enden, ohne Ausgabe und ohne Benachrichtigung.
   - **Anthropic hat Bereiche ergänzt** → melden, mit der konkreten Ergänzung und dem
     Hinweis, dass ein fehlender Bereich künftige Verbindungen blockieren kann.
   - **Anthropic hat Bereiche entfernt** → melden, aber als geringere Dringlichkeit: ein
     zu viel eingetragener Bereich öffnet mehr, als nötig ist, sperrt aber niemanden aus.
4. Ist die Seite nicht erreichbar oder ihr Aufbau geändert: **das** melden, statt zu
   raten. Eine stillschweigend leere Liste wäre der gefährlichste Ausgang.

In jedem Fundfall: **eine** Push-Benachrichtigung, ein Satz — *„Anthropic hat einen
IP-Bereich ergänzt, app/zugriff.py nachziehen"*. David sitzt nicht davor.

## Danach

Der Fix ist eine Codeänderung an `app/zugriff.py` samt Deploy — die geht durch Davids
Freigabe, wie jede andere. `tests/test_zugriff.py` (falls vorhanden) und `make test`
gehören dazu; nach dem Deploy prüfen, dass der Connector noch verbindet.
