# Foliant - Test-Gate (SYN-P1-001): EIN Befehl fuer die komplette lokale Pruefung.
# "pytest gruen" heisst ab jetzt: Haupt-Suite UND DDB-Suite (eigene .venv-ddb) - die
# DDB-Tests werden im Haupt-venv uebersprungen und blieben sonst unsichtbar rot.
# Smoke + admin check laufen nur, wenn die lokale Dev-DB existiert (echte Daten).
#
# ACHTUNG Korpus-Luecke (14.07.2026): die lokale Dev-DB ist auf Entwicklungsmaschinen oft
# nur ein SUBSET (z. B. ohne die englischen DDB-Buecher). Korpusabhaengige Regressionen -
# etwa der Deutsch-first-Ranking-Bug 'Reaktionen'/'Counterspell' - bleiben dort UNSICHTBAR
# gruen. Nach jedem Deploy / srd-de-Re-Import daher zusaetzlich `make test-golden-pi` gegen
# den VOLLEN Bestand fahren (CONCEPT.md §8).

.PHONY: test test-haupt test-ddb test-daten test-golden-pi lasttest-pi deploy-pi

test: test-haupt test-ddb test-daten
	@echo "OK: alle Test-Stufen bestanden."

test-haupt:
	.venv/bin/python -m pytest -q

test-ddb:
	@if [ -x .venv-ddb/bin/python ]; then \
		.venv-ddb/bin/python -m pytest -q tests/test_ddb_exporter.py \
			tests/test_ddb_katalog.py tests/test_ddb_sqlcipher_spike.py; \
	else \
		echo "FEHLER: .venv-ddb fehlt (python3 -m venv .venv-ddb && .venv-ddb/bin/pip install -r requirements-ddb.txt pytest)"; \
		exit 1; \
	fi

test-daten:
	@if [ -f data/foliant.sqlite ]; then \
		.venv/bin/python -m app.admin check && .venv/bin/python -m tests.smoke_test; \
	else \
		echo "Hinweis: keine data/foliant.sqlite - Daten-Stufe uebersprungen (Dev ohne Bestand)."; \
	fi

# Das SSH-Ziel des Pi steht EINMAL in .env (gitignored, Vorlage in .env.example) - hier
# stand frueher ein Platzhalter, der bei jedem Aufruf ueberschrieben werden musste. Warum
# nicht in der Doku: das Repository ist oeffentlich und die Betreiber-Angaben sind bewusst
# anonymisiert. Einmalig uebersteuern geht weiter: `make <ziel> PI=pi@<host>`.
# Bewusst NICHT `include .env`: das zoege alle Secrets in jede Make-Umgebung.
PI ?= $(strip $(shell sed -n 's/^[[:space:]]*PI=[[:space:]]*//p' .env 2>/dev/null | tail -1))

.PHONY: _pi-ziel
_pi-ziel:
	@test -n "$(PI)" || { \
	  echo "FEHLER: kein Pi-Ziel gesetzt."; \
	  echo "  Einmalig in .env eintragen:   PI=pi@<host>"; \
	  echo "  oder einmalig mitgeben:       make <ziel> PI=pi@<host>"; \
	  exit 1; }

# Kanonischer Deploy (CONCEPT.md §9) als EIN Befehl - vorher drei Zeilen zum Abtippen,
# von denen die erste zwei Fussangeln hat: kein --delete und kein data/, sonst
# ueberschreibt das Mac-Subset den Pi-Vollbestand und die gitignorierten Privatmodule
# verschwinden. Die Ausschluesse stehen deshalb hier im Code statt als Warnung daneben.
# Der Rebuild ist zwingend (der Code ist ins Image gebacken), und die Golden-Suite gegen
# den Vollbestand ist laut CONCEPT.md §11 Pflicht NACH jedem Deploy - deshalb haengt sie
# hier dran, statt vergessen werden zu koennen.
.PHONY: deploy-pi
deploy-pi: _pi-ziel
	rsync -a --exclude '.git' --exclude '.venv*' --exclude 'data' --exclude 'quellen' \
	      --exclude 'config/foliant.toml' --exclude '.env' --exclude '.claude' \
	      ./ $(PI):~/foliant/
	ssh $(PI) 'cd ~/foliant && docker compose up -d --build foliant'
	@echo "--- Rebuild durch, jetzt die Pflicht-Pruefung am Vollbestand ---"
	$(MAKE) test-golden-pi PI=$(PI)

# Golden-Suite gegen den VOLLEN Bestand im Pi-Container (Regel-Semantik am echten Korpus,
# nicht am Mac-Subset). Pflicht nach Deploy / srd-de-Re-Import.
test-golden-pi: _pi-ziel
	ssh $(PI) 'cd ~/foliant && docker compose exec -T -w /app foliant python -m pytest -q tests/test_golden_bestand.py'

# B9 unter Sessionlast: Antwortzeiten bei mehreren gleichzeitigen Spielern, gegen den
# VOLLEN Pi-Korpus. Rein lesend, gefahrlos neben dem Live-Betrieb. Exitcode != 0, wenn
# p95 die Grenze reisst - der Lauf ist damit auch als Regressionswaechter brauchbar.
lasttest-pi: _pi-ziel
	ssh $(PI) 'cd ~/foliant && docker compose exec -T -w /app foliant python -m evals.lasttest'

# Schicht-3-Verhaltens-Evals gegen den VOLLEN Pi-Korpus (BACKLOG.md par. 2). Kostet echte
# API-Tokens (~15 Faelle x 3-5 Runden). Der Key wird NUR fuer den Einmal-Exec injiziert -
# der Serving-Container traegt dauerhaft keinen (bewusst, docker-compose.yml). Aufruf:
#   ANTHROPIC_API_KEY=sk-... make eval-verhalten-pi
.PHONY: eval-verhalten-pi
eval-verhalten-pi: _pi-ziel
	@test -n "$$ANTHROPIC_API_KEY" || { echo "FEHLER: ANTHROPIC_API_KEY fehlt."; exit 1; }
	ssh $(PI) "cd ~/foliant && docker compose exec -T -e ANTHROPIC_API_KEY=$$ANTHROPIC_API_KEY -w /app foliant python -m evals.verhaltens_eval $(EVAL_ARGS)"

# Glossar-Tabelle vom Pi (voller Bestand) in die lokale Dev-DB uebernehmen: macht lokale
# Abnahmen belastbar - die Mac-DB ist nur ein Subset, ihre '*'-Sterne sind sonst nicht
# aussagekraeftig (Korpus-Luecke, s. CLAUDE.md). Ersetzt die LOKALE glossar-Tabelle komplett.
.PHONY: glossar-vom-pi
# DB komplett ziehen und nur die glossar-Tabelle uebernehmen (ATTACH): der fruehere Weg
# ueber die sqlite3-CLI scheiterte, weil sie auf dem Pi-HOST nicht installiert ist
# (nur im Container). Der Download (~10 MB) laeuft gegen die Online-DB - fuer die reine
# glossar-Uebernahme unkritisch (Tabelle aendert sich nur bei admin-glossar-Laeufen).
glossar-vom-pi: _pi-ziel
	@test -f data/foliant.sqlite || (echo "FEHLER: keine data/foliant.sqlite"; exit 1)
	scp $(PI):foliant/data/foliant.sqlite .glossar_pi.sqlite
	@test -s .glossar_pi.sqlite || (echo "FEHLER: leerer Download vom Pi"; rm -f .glossar_pi.sqlite; exit 1)
	.venv/bin/python -c "import sqlite3; con = sqlite3.connect('data/foliant.sqlite'); \
		con.execute(\"ATTACH '.glossar_pi.sqlite' AS pi\"); \
		con.execute('DELETE FROM glossar'); \
		con.execute('INSERT INTO glossar (term_en, term_de, offiziell, quelle, edition_quelle, seite) \
			SELECT term_en, term_de, offiziell, quelle, edition_quelle, seite FROM pi.glossar'); \
		con.commit(); \
		print('Glossar:', con.execute('SELECT count(*) FROM glossar').fetchone()[0], 'Zeilen vom Pi uebernommen')"
	@rm -f .glossar_pi.sqlite
