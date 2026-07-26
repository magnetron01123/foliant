#!/usr/bin/env bash
# Discord-Bot fertig einrichten - der Bot-Token ist die EINZIGE Eingabe.
#
# Alles andere holt das Skript selbst ueber die Discord-API (deploy/discord_api.py):
# die Application ID fuer den Einladungslink aus /users/@me, die Server-ID nach der
# Einladung aus /users/@me/guilds. Kein Menue-Suchen im Entwicklerportal, kein
# Entwicklermodus, kein Abtippen von IDs.
#
# Sicherheit: Der Token wird verdeckt eingelesen, NIE als Kommandozeilen-Argument
# uebergeben (waere in `ps` sichtbar) und NIE geloggt - Python bekommt ihn per stdin,
# der Pi per scp einer chmod-600-Datei, die dort sofort geschreddert wird. Muster wie
# beim DDB-Cobalt-Cookie (CONCEPT.md: "nie .env/argv").
#
# Laeuft LOKAL auf dem Mac:  bash deploy/discord_einrichten.sh
set -euo pipefail

HIER="$(cd "$(dirname "$0")" && pwd)"
PI="${PI:-pi@raspberrypi.local}"
# Genau die Rechte, die app/discord_bot/bot.py braucht: View Channel, Send Messages,
# Read Message History, Create Public Threads, Send Messages in Threads.
PERMISSIONS=309237713920

command -v python3 >/dev/null || { echo "python3 fehlt." >&2; exit 1; }

echo "=== Foliant-Discord-Bot einrichten ==="
echo
echo "Du brauchst NUR den Bot-Token (Entwicklerportal -> Bot -> 'Reset Token')."
echo "Application ID und Server-ID frage ich selbst bei Discord ab."
echo
read -rsp "Bot-Token (Eingabe bleibt unsichtbar): " BOT_TOKEN
echo
[[ -n "${BOT_TOKEN}" ]] || { echo "Kein Token eingegeben - abgebrochen." >&2; exit 1; }

# --- Schritt 1: Application ID + Bot-Name ------------------------------------------
echo
echo "Frage Discord, zu welcher App dieser Token gehoert ..."
if ! BOT_INFO="$(printf '%s' "${BOT_TOKEN}" | python3 "${HIER}/discord_api.py" app-id)"; then
  exit 1                     # discord_api.py hat den Grund schon erklaert
fi
APP_ID="${BOT_INFO%%$'\t'*}"
BOT_NAME="${BOT_INFO##*$'\t'}"
echo "Erkannt: Bot '${BOT_NAME}' (Application ID ${APP_ID})"

# --- Schritt 2: Einladungslink -----------------------------------------------------
EINLADUNG="https://discord.com/oauth2/authorize?client_id=${APP_ID}&permissions=${PERMISSIONS}&scope=bot%20applications.commands"
echo
echo "1. Oeffne diesen Link (Browser, in dem du bei Discord eingeloggt bist):"
echo
echo "   ${EINLADUNG}"
echo
echo "2. Waehle euren Server und bestaetige die Berechtigungen."
if command -v open >/dev/null; then
  read -rp "   Link direkt oeffnen? [J/n] " OEFFNEN
  [[ "${OEFFNEN:-j}" =~ ^([jJ]|)$ ]] && open "${EINLADUNG}"
fi
echo
read -rp "3. Enter druecken, sobald der Bot im Server steht ... " _

# --- Schritt 3: Server-ID automatisch ----------------------------------------------
echo
echo "Frage Discord, auf welchen Servern der Bot jetzt ist ..."
if ! GUILD_ZEILEN="$(printf '%s' "${BOT_TOKEN}" | python3 "${HIER}/discord_api.py" guilds)"; then
  echo "Tipp: Einladungslink noch einmal oeffnen, Server bestaetigen, Skript neu starten." >&2
  exit 1
fi

# Bewusst kein `mapfile`: macOS liefert bash 3.2, dort fehlt es - und zwar STILL
# (leeres Array statt Fehler, die Guild-ID waere leer geblieben).
GUILD_LISTE=()
while IFS= read -r zeile; do
  [[ -n "${zeile}" ]] && GUILD_LISTE+=("${zeile}")
done <<< "${GUILD_ZEILEN}"
[[ "${#GUILD_LISTE[@]}" -gt 0 ]] || { echo "Keine Server-Liste erhalten." >&2; exit 1; }
if [[ "${#GUILD_LISTE[@]}" -eq 1 ]]; then
  GUILD_ID="${GUILD_LISTE[0]%%$'\t'*}"
  GUILD_NAME="${GUILD_LISTE[0]##*$'\t'}"
  echo "Gefunden: '${GUILD_NAME}' (ID ${GUILD_ID})"
else
  echo "Der Bot ist auf mehreren Servern - welcher ist der Runden-Server?"
  for i in "${!GUILD_LISTE[@]}"; do
    printf '  [%d] %s (ID %s)\n' "$((i + 1))" \
      "${GUILD_LISTE[$i]##*$'\t'}" "${GUILD_LISTE[$i]%%$'\t'*}"
  done
  read -rp "Nummer waehlen: " WAHL
  if ! [[ "${WAHL}" =~ ^[0-9]+$ ]] || (( WAHL < 1 || WAHL > ${#GUILD_LISTE[@]} )); then
    echo "Ungueltige Auswahl - abgebrochen." >&2
    exit 1
  fi
  GUILD_ID="${GUILD_LISTE[$((WAHL - 1))]%%$'\t'*}"
  GUILD_NAME="${GUILD_LISTE[$((WAHL - 1))]##*$'\t'}"
  echo "Gewaehlt: '${GUILD_NAME}' (ID ${GUILD_ID})"
fi

# --- Schritt 4: Zugangsdaten auf den Pi, Dienst starten ----------------------------
LOKALE_DATEI="$(mktemp)"
REMOTE_DATEI="/tmp/foliant-discord-creds.$$"
trap 'rm -f "${LOKALE_DATEI}"' EXIT
umask 077
{
  printf 'DISCORD_BOT_TOKEN=%s\n' "${BOT_TOKEN}"
  printf 'DISCORD_GUILD_ID=%s\n' "${GUILD_ID}"
} > "${LOKALE_DATEI}"

echo
echo "Uebertrage Zugangsdaten nach ${PI} (SSH-verschluesselt) ..."
scp -pq "${LOKALE_DATEI}" "${PI}:${REMOTE_DATEI}"

ssh -o BatchMode=yes "${PI}" "REMOTE_DATEI='${REMOTE_DATEI}' bash -s" <<'REMOTE'
set -euo pipefail
chmod 600 "${REMOTE_DATEI}"
cd ~/foliant

setze_wert() {
  local schluessel="$1" wert="$2" escaped
  escaped=$(printf '%s' "$wert" | sed 's/[&|\]/\\&/g')
  if grep -q "^${schluessel}=" .env 2>/dev/null; then
    sed -i "s|^${schluessel}=.*|${schluessel}=${escaped}|" .env
  else
    printf '%s=%s\n' "$schluessel" "$wert" >> .env
  fi
}

# shellcheck source=/dev/null
source "${REMOTE_DATEI}"
setze_wert DISCORD_BOT_TOKEN "${DISCORD_BOT_TOKEN}"
setze_wert DISCORD_GUILD_ID "${DISCORD_GUILD_ID}"
shred -u "${REMOTE_DATEI}" 2>/dev/null || rm -f "${REMOTE_DATEI}"

echo "Werte in der .env gesetzt (Token nicht angezeigt). Starte discord-Dienst ..."
docker compose up -d discord
sleep 5
echo "--- Letzte Log-Zeilen ---"
docker compose logs --tail 20 discord
REMOTE

echo
echo "=== Fertig ==="
echo "In Discord testen:  /regel Was macht der Zauber Feuerball?"
echo "Logs live:          ssh ${PI} 'cd ~/foliant && docker compose logs -f discord'"
