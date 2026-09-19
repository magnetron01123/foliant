"""Lebenszeichen des Bots - eine Datei mit einem Zeitstempel, mehr nicht.

WARUM (D5, Review 19.09.2026): Der Discord-Container war als einziger Dienst ohne
Healthcheck. `foliant` und `web` melden sich ueber ihren HTTP-Endpunkt, der Bot hat
keinen - er ist reiner Ausgangsverkehr. `docker ps` sagte deshalb auch dann "Up", wenn
die Gateway-Verbindung laengst tot war oder der Meldeweg nichts mehr lieferte.

Genau das ist am 11.08.2026 passiert: Ein Hautton-Emoji verschluckte die Rueckmeldungen
still, und gemerkt hat es niemand, weil niemand meldet, dass das Melden nicht geht.
BACKLOG D5 fuehrt das seither als offenen Posten - "sein Ausfall bliebe unbemerkt".

Bewusst eine DATEI und kein Netz-Endpunkt: Der Bot soll keine eingehende HTTP-Flaeche
bekommen (CONCEPT §13 fuehrt genau ihr Fehlen als Sicherheitsmerkmal). Sie liegt unter
/tmp, das im Container ohnehin als tmpfs gemountet ist - ein Neustart beginnt damit
sauber ohne Altstand, und der Healthcheck sieht das an der fehlenden Datei.

Geschrieben wird aus der Gateway-Schleife heraus (nicht bei jeder Frage): Ein Bot, den
zwei Tage niemand fragt, ist gesund; einer, dessen Verbindung steht, aber keine
Ereignisse mehr bekommt, ist es nicht.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

# Im Container ein tmpfs (docker-compose.yml), lokal das normale /tmp. Ueber die
# Umgebung ueberschreibbar, damit Tests nicht ins echte /tmp schreiben.
PFAD = Path(os.environ.get("FOLIANT_LEBENSZEICHEN") or "/tmp/foliant-discord-lebt")

# Wie alt die Datei hoechstens sein darf, bevor der Healthcheck anschlaegt. Der Bot
# schreibt jede Minute; drei verpasste Runden sind ein Ausfall, eine ist ein Hicks.
MAX_ALTER_S = 180


def schreibe(pfad: Path | None = None, jetzt=None) -> bool:
    """Zeitstempel festschreiben; True bei Erfolg.

    Wirft nie: Ein Lebenszeichen, das den Bot mit in den Abgrund zieht, waere das
    Gegenteil von Ueberwachung. Dieselbe Leitplanke wie beim Abfrage-Protokoll."""
    ziel = pfad or PFAD
    try:
        ziel.parent.mkdir(parents=True, exist_ok=True)
        ziel.write_text(f"{int((jetzt or time.time)())}\n", encoding="utf-8")
        return True
    except OSError:
        return False


def alter_s(pfad: Path | None = None, jetzt=None) -> float | None:
    """Alter des Lebenszeichens in Sekunden - None, wenn es keines gibt oder der Inhalt
    unbrauchbar ist. Beides heisst fuer den Healthcheck dasselbe: nicht gesund."""
    ziel = pfad or PFAD
    try:
        stempel = int(ziel.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    return (jetzt or time.time)() - stempel


def ist_gesund(pfad: Path | None = None, jetzt=None) -> bool:
    alter = alter_s(pfad, jetzt)
    return alter is not None and 0 <= alter <= MAX_ALTER_S


def main() -> int:
    """Einstieg fuer den Container-Healthcheck: Exitcode 0 = gesund."""
    return 0 if ist_gesund() else 1


if __name__ == "__main__":
    raise SystemExit(main())
