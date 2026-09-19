#!/usr/bin/env bash
# Holt die Foliant-Artefakte vom Pi auf den Mac und prueft sie (M3/M9, R12-R14).
#
# WARUM: Der naechtliche Cron auf dem Pi legt verifizierte Backups an - aber ALLE Staende
# liegen auf derselben SD-Karte wie der Bestand. Ein Kartenausfall nimmt Bestand UND
# Sicherungen mit. Erst eine Kopie auf einem zweiten Geraet ist eine Sicherung.
#
# ES WIRD GEZOGEN, NIE GESCHOBEN. Der Mac holt sich, was er braucht; auf dem Pi laeuft
# nichts, was hierher schreiben koennte. Ein kompromittierter Pi kann damit die Historie
# auf dem Mac nicht anfassen - und ein Tippfehler hier keine Produktionsdaten.
#
# Vorbild ist Davids HA-Skript (werkzeuge/hole_und_pruefe_backup.sh), BEWUSST OHNE dessen
# O_DIRECT-Wiederholungstanz: Der war die Antwort auf einen HAOS-Kernel-Fehler des
# HA-Pi, der veraltete Puffer statt frischer Daten lieferte. Foliants Pi hat diese
# Geschichte nicht; ein Wiederholungsmechanismus gegen ein Problem, das es hier nicht
# gibt, verdeckt nur echte Fehler.
#
# Aufruf:  deploy/sicherung_holen.sh [zielverzeichnis]
#          make sicherung-holen ZIEL="/Volumes/..."
#
# Das Ziel steht NICHT im Repo: Die Sicherungen tragen private Buchinhalte, und das
# Repository ist oeffentlich. Entweder als Argument, ueber SICHERUNG_ZIEL in der .env
# oder als Umgebungsvariable.

set -uo pipefail

PI="${PI:-}"
if [ -z "$PI" ] && [ -f .env ]; then
    PI=$(sed -n 's/^[[:space:]]*PI=[[:space:]]*//p' .env | tail -1)
fi
[ -n "$PI" ] || { echo "FEHLER: kein Pi-Ziel (PI=pi@<host> in .env)."; exit 1; }

ZIEL="${1:-${SICHERUNG_ZIEL:-}}"
if [ -z "$ZIEL" ] && [ -f .env ]; then
    ZIEL=$(sed -n 's/^[[:space:]]*SICHERUNG_ZIEL=[[:space:]]*//p' .env | tail -1)
fi
if [ -z "$ZIEL" ]; then
    echo "FEHLER: kein Zielverzeichnis."
    echo "  Einmalig in .env:   SICHERUNG_ZIEL=/Volumes/<Platte>/Foliant"
    echo "  oder mitgeben:      make sicherung-holen ZIEL=/Volumes/<Platte>/Foliant"
    echo
    echo "Das Ziel steht bewusst nicht im Repo: Die Sicherungen tragen private"
    echo "Buchinhalte, und dieses Repository ist oeffentlich."
    exit 1
fi

# Ist das Ziel ueberhaupt da? Ein nicht eingehaengtes Volume laesst mkdir -p klaglos ein
# Verzeichnis im MOUNTPOINT anlegen - die Sicherung landet dann auf der Systemplatte und
# sieht aus wie ein Erfolg. Genau diese Klasse Fehler soll ein Off-Site-Spiegel nicht haben.
ELTERN=$(dirname "$ZIEL")
[ -d "$ELTERN" ] || { echo "FEHLER: $ELTERN gibt es nicht - Platte eingehaengt?"; exit 1; }

STEMPEL=$(date +%Y%m%d-%H%M%S)
LAUF="$ZIEL/$STEMPEL"
mkdir -p "$LAUF" || exit 1

echo "Quelle: $PI:~/foliant"
echo "Ziel  : $LAUF"
echo

# --- 1. Ein frisches, verifiziertes Backup auf dem Pi erzeugen ---------------------
# Nicht einfach die juengste vorhandene Datei nehmen: `admin backup` faehrt die
# SQLite-Backup-API (konsistent auch bei laufendem Import) und verifiziert selbst.
echo "== frisches Backup auf dem Pi =="
ssh -o BatchMode=yes "$PI" \
    'cd ~/foliant && docker compose exec -T foliant python -m app.admin backup' \
    || { echo "FEHLER: Backup auf dem Pi fehlgeschlagen."; exit 1; }
echo

# --- 2. Holen ----------------------------------------------------------------------
# Die Liste ist die Antwort auf die Frage "was ueberlebt einen Kartenausfall NICHT?".
# `config/foliant.toml` ist gitignored, `quellen/` sind die Roh-PDFs, die privaten
# DDB-Artefakte gibt es nirgends sonst - und die Protokoll-DB stand bis heute in KEINEM
# Backup-Pfad, obwohl sie die Kurationsgrundlage ist (BACKLOG M9).
#
# `--append-verify` waere hier falsch: Wir holen jedes Mal in ein NEUES
# Stempel-Verzeichnis, damit ein beschaedigter Lauf den vorherigen nicht anfasst.
hole() {
    local was="$1" ziel="$2"
    echo -n "  $was ... "
    if rsync -a --timeout=120 "$PI:~/foliant/$was" "$LAUF/$ziel" 2>/dev/null; then
        echo "ok"
    else
        echo "FEHLT (nicht vorhanden oder nicht lesbar)"
        return 1
    fi
}

echo "== holen =="
FEHLER=0
hole "data/backups/"            "backups/"        || FEHLER=1
hole "data/foliant-protokoll.sqlite" "."          || FEHLER=1
hole "config/foliant.toml"      "."               || FEHLER=1
# Die beiden grossen, aber selten geaenderten Posten. Kein Abbruch, wenn sie fehlen:
# Ein Serve-only-Pi fuehrt keine Rohquellen.
hole "quellen/"                 "quellen/"        || true
hole "data/private/"            "private/"        || true
echo

# --- 3. Pruefen --------------------------------------------------------------------
# Eine Kopie, die niemand geprueft hat, ist eine Vermutung. Geprueft wird das JUENGSTE
# Korpus-Backup - integrity_check plus die Zusage, die `admin backup` selbst gibt
# (nicht leer, FTS-Zeilen passen zur Eintragszahl).
echo "== pruefen =="
JUENGSTES=$(ls -t "$LAUF/backups"/foliant-*.sqlite 2>/dev/null | head -1)
if [ -z "$JUENGSTES" ]; then
    echo "  FEHLER: kein Korpus-Backup im geholten Stand."
    exit 1
fi
python3 - "$JUENGSTES" <<'PY' || FEHLER=1
import sqlite3, sys, pathlib
pfad = pathlib.Path(sys.argv[1])
con = sqlite3.connect(f"file:{pfad}?mode=ro", uri=True)
try:
    integ = con.execute("PRAGMA integrity_check").fetchone()[0]
    n = con.execute("SELECT count(*) FROM eintraege").fetchone()[0]
    fts = con.execute("SELECT count(*) FROM eintraege_fts").fetchone()[0]
    quellen = con.execute("SELECT count(*) FROM quellen").fetchone()[0]
finally:
    con.close()
mib = pfad.stat().st_size / 1024 / 1024
print(f"  {pfad.name}: {mib:.0f} MiB, {n} Eintraege, {quellen} Quellen, "
      f"integrity={integ}, FTS={fts}")
if integ != "ok" or n == 0 or n != fts:
    print("  FEHLER: Verifikation fehlgeschlagen.")
    raise SystemExit(1)
print("  INTAKT")
PY

# Pruefsumme notieren - so faellt ein spaeter beschaedigter Stand auf, und zwei Laeufe
# lassen sich vergleichen, ohne die Dateien zu oeffnen.
shasum -a 256 "$JUENGSTES" | sed "s| .*/| |" >> "$ZIEL/PRUEFSUMMEN.txt"
echo

# --- 4. Generationen begrenzen ------------------------------------------------------
# Ein Spiegel, der nur den letzten Stand haelt, gibt Schaden weiter: Wird der Bestand
# heute beschaedigt und morgen gespiegelt, ist die heile Fassung weg. Deshalb mehrere
# Generationen - das ist der Unterschied zwischen Spiegel und Sicherung.
BEHALTEN="${BEHALTEN:-6}"
echo "== Generationen =="
ls -dt "$ZIEL"/*/ 2>/dev/null | tail -n +$((BEHALTEN + 1)) | while read -r alt; do
    echo "  entferne $alt"
    rm -rf "$alt"
done
echo "  $(ls -d "$ZIEL"/*/ 2>/dev/null | wc -l | tr -d ' ') Stand/Staende in $ZIEL"
echo

if [ "$FEHLER" -ne 0 ]; then
    echo "MIT FEHLERN beendet - der Stand in $LAUF ist UNVOLLSTAENDIG."
    exit 1
fi
echo "FERTIG: $LAUF"
echo
echo "Restore-Probe (CONCEPT.md §8) - sie ist der Teil, der die Sicherung erst zu einer"
echo "macht; eine Sicherung, aus der nie jemand zurueckgespielt hat, ist eine Vermutung:"
echo "  cp '$JUENGSTES' /tmp/restore-probe.sqlite"
echo "  FOLIANT_DB=/tmp/restore-probe.sqlite .venv/bin/python -m app.admin check"
