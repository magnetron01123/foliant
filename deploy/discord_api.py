"""Kleine Discord-API-Helfer fuer deploy/discord_einrichten.sh und den
Rueckmeldungs-Durchgang (O4/M5) - nur Standardbibliothek.

Der Bot-Token kommt ueber STDIN (nie als Argument: der waere in `ps` sichtbar), das
Kommando als argv[1]. Ausgabe ist tab-getrennt und zeilenweise, damit die Shell sie
ohne Parser-Gebastel lesen kann.

    printf '%s' "$TOKEN" | python3 deploy/discord_api.py app-id
    printf '%s' "$TOKEN" | python3 deploy/discord_api.py guilds
    docker compose exec -T discord python deploy/discord_api.py nachrichten <kanal> <id>

Exit-Codes: 0 = ok, 2 = Token ungueltig (401), 3 = keine Guild, 1 = sonstiger Fehler.

`nachrichten` holt den Gespraechskontext um eine markierte Antwort. Warum es hier steht
und nicht in einem eigenen Modul: `hole()` setzt bereits den `User-Agent`, ohne den
Discord hinter Cloudflare mit "error code: 1010" abweist - ein zweiter Client haette
dieselbe Falle noch einmal zu lernen.

WAS DIESES KOMMANDO NICHT TUT: Es schreibt nichts in eine Datei, und der Aufrufer darf
das auch nicht. Der Antworttext steht bewusst NICHT im Protokoll (CONCEPT.md par. 13,
"kein Gespraechsinhalt in einer Log-Datei") - ihn beim Auswerten in eine Datei
umzuleiten waere derselbe Schritt durch die Hintertuer. Ausgegeben wird nur
`bot|mensch`, nie ein Autorname und nie eine Nutzer-ID.
"""
from __future__ import annotations

import json
import os
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


def _eine_zeile(text: str) -> str:
    """Zeilenumbrueche escapen: Eine Bot-Antwort ist mehrzeilig, das Ausgabeformat
    zeilenweise. Ohne das zerfiele eine Nachricht in scheinbar mehrere."""
    return (text or "").replace("\\", "\\\\").replace("\n", "\\n").replace("\t", " ")


def nachrichten(kanal_id: str, nachricht_id: str, token: str) -> None:
    """Der Gespraechskontext um eine markierte Antwort - fuer den Auswertungs-Durchgang.

    Ausgegeben wird je Zeile `id \\t bot|mensch \\t inhalt`. Bewusst OHNE Autorname und
    ohne Nutzer-ID: Das ist dieselbe Datenklasse, die `rueckmeldung.frage_aus_umgebung`
    ohnehin verarbeitet, und haelt die Zusage aus CONCEPT.md par. 13 auch auf dem
    Auswertungsweg ein - wer etwas gefragt hat, ist fuer die Kuration ohne Bedeutung."""
    daten = hole(f"/channels/{kanal_id}/messages?around={nachricht_id}&limit=8", token)
    for m in sorted(daten, key=lambda m: int(m["id"])):
        wer = "bot" if m.get("author", {}).get("bot") else "mensch"
        print(f"{m['id']}\t{wer}\t{_eine_zeile(m.get('content'))}")


def main() -> None:
    argumente = sys.argv[1:]
    kommando = argumente[0] if argumente else None
    if kommando in ("app-id", "guilds") and len(argumente) != 1:
        kommando = None
    if kommando == "nachrichten" and len(argumente) != 3:
        kommando = None
    if kommando not in ("app-id", "guilds", "nachrichten"):
        print("Aufruf: discord_api.py app-id|guilds  (Token auf stdin)\n"
              "        discord_api.py nachrichten <kanal-id> <nachricht-id>",
              file=sys.stderr)
        raise SystemExit(1)

    # Token weiterhin NIE als Argument. `nachrichten` laeuft im discord-Container, wo die
    # Variable ohnehin gesetzt ist - sie ueber `docker compose exec` erneut auf stdin zu
    # reichen brauchte einen zweiten Weg, ohne irgendetwas sicherer zu machen. Die
    # Haertung bleibt: der Token steht in keiner Kommandozeile.
    token = sys.stdin.read().strip() if not sys.stdin.isatty() else ""
    if not token:
        token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    if not token:
        print("Kein Token auf stdin und kein DISCORD_BOT_TOKEN in der Umgebung.",
              file=sys.stderr)
        raise SystemExit(1)

    if kommando == "nachrichten":
        nachrichten(argumente[1], argumente[2], token)
        return

    if kommando == "app-id":
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
