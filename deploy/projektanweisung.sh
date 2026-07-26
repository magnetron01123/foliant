#!/usr/bin/env bash
# Projektanweisung in die Zwischenablage legen und claude.ai oeffnen - so weit es ohne
# claude.ai-API geht. Quelle ist config/projektanweisung.md (ueber config.stil, also
# dieselbe Leseestelle wie Website, Eval und Kanal-Sync-Test - nie eine veraltete Kopie).
# Danach nur noch: Projekt "D&D Runde" -> Projektanweisungen -> Cmd+A, Cmd+V, speichern.
#
# Die Runde braucht das Skript nicht: Mitspieler holen den Text kopierbereit auf der
# Charakterbogen-Website (Abschnitt "Foliant im Claude-Chat").
set -euo pipefail
cd "$(dirname "$0")/.."

python3 - <<'PY' | pbcopy
import sys

from config.stil import projektanweisung

text = projektanweisung()
if not text:
    sys.exit("config/projektanweisung.md fehlt - nichts zu kopieren.")
print(text, end="")
PY

echo "Projektanweisung in der Zwischenablage ($(pbpaste | wc -c | tr -d ' ') Zeichen)."
echo "claude.ai oeffnet sich: Projekt 'D&D Runde' -> Projektanweisungen -> Cmd+A, Cmd+V, speichern."
open "https://claude.ai/projects"
