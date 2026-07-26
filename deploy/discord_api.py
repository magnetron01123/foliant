"""Kleine Discord-API-Helfer fuer deploy/discord_einrichten.sh - nur Standardbibliothek.

Der Bot-Token kommt ueber STDIN (nie als Argument: der waere in `ps` sichtbar), das
Kommando als argv[1]. Ausgabe ist tab-getrennt und zeilenweise, damit die Shell sie
ohne Parser-Gebastel lesen kann.

    printf '%s' "$TOKEN" | python3 deploy/discord_api.py app-id
    printf '%s' "$TOKEN" | python3 deploy/discord_api.py guilds

Exit-Codes: 0 = ok, 2 = Token ungueltig (401), 3 = keine Guild, 1 = sonstiger Fehler.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

API = "https://discord.com/api/v10"
TOKEN_UNGUELTIG = 2
KEINE_GUILD = 3


def hole(pfad: str, token: str):
    anfrage = urllib.request.Request(
        f"{API}{pfad}",
        headers={"Authorization": f"Bot {token}", "User-Agent": "FoliantSetup/1.0"})
    try:
        with urllib.request.urlopen(anfrage, timeout=20) as antwort:
            return json.load(antwort)
    except urllib.error.HTTPError as fehler:
        if fehler.code == 401:
            print("Token ungueltig (401). Im Bot-Tab 'Reset Token' druecken und den "
                  "NEUEN Token verwenden - ein Reset macht den alten sofort ungueltig.",
                  file=sys.stderr)
            raise SystemExit(TOKEN_UNGUELTIG)
        print(f"Discord-API-Fehler {fehler.code}: {fehler.reason}", file=sys.stderr)
        raise SystemExit(1)
    except urllib.error.URLError as fehler:
        print(f"Discord nicht erreichbar: {fehler.reason}", file=sys.stderr)
        raise SystemExit(1)


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in ("app-id", "guilds"):
        print("Aufruf: discord_api.py app-id|guilds  (Token auf stdin)", file=sys.stderr)
        raise SystemExit(1)
    token = sys.stdin.read().strip()
    if not token:
        print("Kein Token auf stdin.", file=sys.stderr)
        raise SystemExit(1)

    if sys.argv[1] == "app-id":
        # Bei Bot-Accounts ist die User-ID identisch mit der Application ID - damit
        # muss niemand die ID im Entwicklerportal suchen.
        ich = hole("/users/@me", token)
        print(f"{ich['id']}\t{ich.get('username', '?')}")
        return

    guilds = hole("/users/@me/guilds", token)
    if not guilds:
        print("Der Bot ist auf keinem Server. Einladungslink oeffnen und bestaetigen.",
              file=sys.stderr)
        raise SystemExit(KEINE_GUILD)
    for guild in guilds:
        print(f"{guild['id']}\t{guild.get('name', '?')}")


if __name__ == "__main__":
    main()
