#!/usr/bin/env bash
# Projektanweisung aktualisieren, so weit es ohne claude.ai-API geht:
# extrahiert den KANONISCHEN Codeblock aus SPEC.md §8 (dieselbe Quelle wie
# tests/test_verhaltensregeln.py - nie eine veraltete Kopie), legt ihn in die
# Zwischenablage und oeffnet claude.ai. Dann nur noch: Projekt "D&D Runde"
# -> Projektanweisungen -> alles markieren (Cmd+A) -> einfuegen (Cmd+V).
# Nach JEDER Aenderung an SPEC.md §8 / config/stil.py erneut ausfuehren.
set -euo pipefail
cd "$(dirname "$0")/.."

python3 - <<'PY' | pbcopy
import pathlib
import re

text = pathlib.Path("SPEC.md").read_text(encoding="utf-8")
bloecke = re.findall(r"```\n(Du hilfst unserer D&D-Runde.*?)```", text, re.S)
assert len(bloecke) == 1, "SPEC.md §8 muss genau EINEN Projektanweisungs-Block enthalten"
print(bloecke[0], end="")
PY

echo "Projektanweisung in der Zwischenablage ($(pbpaste | wc -c | tr -d ' ') Zeichen)."
echo "claude.ai oeffnet sich: Projekt 'D&D Runde' -> Projektanweisungen -> Cmd+A, Cmd+V, speichern."
open "https://claude.ai/projects"
