"""Foliant-Discord-Bot: Regelfragen der Runde in Discord, Antworten aus dem Bestand.

Aufbau (bewusst zweigeteilt, damit die Logik ohne discord.py testbar bleibt):
  haupt.py     - Entry (python -m app.discord_bot.haupt): Env, Fail-soft-Checks, run
  bot.py       - duenner Discord-Kleber (Slash /regel, @Mention, Threads)
  gespraech.py - Thread-Verlaeufe in-memory (TTL/LRU/Zeichen-Budget)
  rebuild.py   - Verlauf aus der Discord-Historie zurueckholen (nach Neustart)
  antwort.py   - 2000-Zeichen-Splitting, Thread-Titel, deutsche Fehlertexte
  schranken.py - Guild-/Kanal-Gate, Cooldown, Tagesdeckel

Die Tool-Use-Schleife kommt aus app/llm.py - dieselbe wie im Eval-Harness, damit
die gemessene Antwortqualitaet auch fuer den Bot gilt."""
