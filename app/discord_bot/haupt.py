"""Entry des Discord-Bots: python -m app.discord_bot.haupt

Fail-soft wie die Website (web.py ohne Kennwort = Seite zu): fehlende Konfiguration
oder fehlender Bestand fuehren zu einem klaren Log-Hinweis plus Warteschleife, nie zu
einem Crash-Loop unter `restart: unless-stopped` - der verlaermt nur die Pi-Logs.
Secrets (Bot-Token, API-Key) kommen NUR aus der Umgebung und werden nie geloggt."""
from __future__ import annotations

import logging
import os
import sys
import time

from app import db as _db
from app import llm as _llm
from config import stil

_log = logging.getLogger("foliant.discord")


def _warte_ewig(meldung: str) -> None:
    """Konfig fehlt: Container laeuft ruhig weiter und erinnert stuendlich - David
    ergaenzt die .env und macht `docker compose restart discord`."""
    while True:
        _log.error("%s", meldung)
        time.sleep(3600)


def _zahl(name: str, standard: float) -> float:
    """Optionale Zahl aus der Umgebung. Unsinn faellt mit Log-Hinweis auf den Standard
    zurueck: ein Tippfehler in der .env darf den Bot nicht ausknipsen (fail-soft) und
    schon gar nicht eine Schranke stillschweigend auf 0 setzen."""
    roh = (os.environ.get(name) or "").strip()
    if not roh:
        return standard
    try:
        wert = float(roh)
    except ValueError:
        wert = -1.0
    if wert < 0:
        _log.warning("%s ist keine gueltige Zahl - nutze %s.", name, standard)
        return standard
    return wert


def _lies_konfig() -> dict:
    token = (os.environ.get("DISCORD_BOT_TOKEN") or "").strip()
    guild = (os.environ.get("DISCORD_GUILD_ID") or "").strip()
    key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    if not token:
        _warte_ewig("DISCORD_BOT_TOKEN fehlt in der .env - Bot bleibt aus.")
    if not guild.isdigit():
        _warte_ewig("DISCORD_GUILD_ID fehlt/ungueltig in der .env - ohne Guild-Sperre "
                    "startet der Bot NICHT (SPEC par. 12: Bestand ist privat).")
    if not key:
        _warte_ewig("ANTHROPIC_API_KEY fehlt in der .env - Bot bleibt aus.")
    kanaele = frozenset(int(k) for k in
                        (os.environ.get("DISCORD_KANAL_IDS") or "").split(",")
                        if k.strip().isdigit())
    return {"token": token, "guild_id": int(guild), "kanal_ids": kanaele,
            "tagesdeckel": int(_zahl("DISCORD_TAGESDECKEL", 100)),
            "cooldown_s": _zahl("DISCORD_COOLDOWN_S", 10.0),
            "api_key": key,
            "modell": (os.environ.get("ANTHROPIC_MODEL") or "").strip()
                      or _llm.STANDARD_MODELL}


def _warte_auf_bestand() -> None:
    while not _db.standard_pfad().exists():
        _log.error("Bestand %s fehlt - warte 60 s (Import/Mount pruefen).",
                   _db.standard_pfad())
        time.sleep(60)


def _system_prompt() -> str:
    anweisung = stil.projektanweisung()
    if not anweisung:
        _warte_ewig("config/projektanweisung.md fehlt - ohne Verhaltensregeln "
                    "startet der Bot nicht (B1: kein ungeerdeter Betrieb).")
    zusatz = stil.discord_zusatz()
    return f"{anweisung}\n\n{zusatz}" if zusatz else anweisung


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    konfig = _lies_konfig()
    _warte_auf_bestand()
    from app.discord_bot.bot import FoliantBot   # discord.py erst nach den Checks laden

    bot = FoliantBot(guild_id=konfig["guild_id"], kanal_ids=konfig["kanal_ids"],
                     tagesdeckel=konfig["tagesdeckel"], api_key=konfig["api_key"],
                     modell=konfig["modell"], system=_system_prompt(),
                     cooldown_s=konfig["cooldown_s"])
    # log_handler=None: discord.py wuerde sonst ein zweites basicConfig aufsetzen.
    bot.run(konfig["token"], log_handler=None)


if __name__ == "__main__":
    sys.exit(main())
