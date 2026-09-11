# Abgleich der Anthropic-Egress-IPs (rein lesend)

Prüfe, ob die in der Cloudflare-WAF-Regel hinterlegten Anthropic-Egress-Bereiche noch zu
Anthropics veröffentlichter Liste passen. **Nichts ändern** — dieser Durchgang stellt nur
fest.

**Wenn nichts abweicht, ende ohne Ausgabe.**

## Warum das geprüft wird

Seit dem 02.09.2026 lässt eine WAF-Regel auf `mcp.magnetron.me` nur Anfragen aus Anthropics
Egress-Bereichen durch — für **alle** MCP-Server des Geräts, nicht nur für Foliant. Die
Bereiche stehen als Literale in dieser Regel (Cloudflare → Security → Sicherheitsregeln →
„MCP nur aus Anthropic-Egress"); der Wortlaut steht in `CONCEPT.md` §9. Quelle der Liste ist
die Doku-Seite zu den API-IP-Adressen, mit der Zusage „will not change without notice".

Ändert Anthropic diese Bereiche, sperrt die Regel **Claude aus** — und zwar still: Der
Connector meldet nur einen Verbindungsfehler, nichts deutet auf die Allowlist. Am Spieltisch
sieht das aus, als wäre Foliant kaputt; beim Mealie-MCP, als wäre Mealie kaputt.

Dieser Abgleich wiegt schwerer als früher: Bis zum 02.09.2026 stand dieselbe Liste in
`app/zugriff.py`, war versioniert und wurde mitgetestet. Jetzt liegt sie im Dashboard —
kein Test, kein Diff, kein PR sieht sie. Dieser Ablauf ist das einzige, was noch hinschaut.

## Ablauf

1. Die aktuelle Liste von Anthropics Doku-Seite holen
   (`https://platform.claude.com/docs/en/api/ip-addresses`).
2. Gegen die Bereiche in der WAF-Regel halten — IPv4 **und** IPv6. Den Wortlaut der Regel
   im Cloudflare-Dashboard nachsehen; die in `CONCEPT.md` §9 abgedruckte Fassung ist eine
   Kopie und kann veraltet sein.
   Anthropics Seite führt nur `160.79.104.0/21` unter *ausgehend*, `2607:6bc0::/48` dagegen
   unter *eingehend*. Der IPv6-Block steht bewusst in der Regel (`CONCEPT.md` §9) und ist
   **kein** Fund. Die Adressen unter *Phased out* dürfen dagegen nicht in der Regel stehen.
3. Prüfen, dass die Regel überhaupt noch existiert und greift:
   ```sh
   curl -s -o /dev/null -w '%{http_code}\n' https://mcp.magnetron.me/nichts-hier   # muss 403 sein
   ```
   **404 statt 403 ist der dringendste Fund dieses Ablaufs** — dann ist die Regel weg und
   jeder MCP des Geräts steht offen.
4. Vier Fälle:
   - **Identisch und 403** → lautlos enden, ohne Ausgabe und ohne Benachrichtigung.
   - **Regel fehlt (404)** → sofort melden, höchste Dringlichkeit.
   - **Anthropic hat Bereiche ergänzt** → melden, mit der konkreten Ergänzung und dem
     Hinweis, dass ein fehlender Bereich künftige Verbindungen blockieren kann.
   - **Anthropic hat Bereiche entfernt** → melden, aber als geringere Dringlichkeit: ein
     zu viel eingetragener Bereich öffnet mehr, als nötig ist, sperrt aber niemanden aus.
5. Ist die Doku-Seite nicht erreichbar oder ihr Aufbau geändert: **das** melden, statt zu
   raten. Eine stillschweigend leere Liste wäre der gefährlichste Ausgang.

In jedem Fundfall: **eine** Push-Benachrichtigung, ein Satz — *„Anthropic hat einen
IP-Bereich ergänzt, die WAF-Regel nachziehen"*. David sitzt nicht davor.

## Danach

Der Fix ist eine Änderung im Cloudflare-Dashboard und geht durch Davids Freigabe. Die Regel
**bearbeiten**, nicht löschen und neu anlegen — im Löschfenster steht alles offen. Danach
den 403-Test aus Schritt 3 wiederholen und mit einem lesenden Tool-Aufruf gegenprüfen, dass
Claude weiterhin durchkommt. Die Kopie in `CONCEPT.md` §9 mit nachziehen.
