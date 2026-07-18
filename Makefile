# Foliant - Test-Gate (SYN-P1-001): EIN Befehl fuer die komplette lokale Pruefung.
# "pytest gruen" heisst ab jetzt: Haupt-Suite UND DDB-Suite (eigene .venv-ddb) - die
# DDB-Tests werden im Haupt-venv uebersprungen und blieben sonst unsichtbar rot.
# Smoke + admin check laufen nur, wenn die lokale Dev-DB existiert (echte Daten).
#
# ACHTUNG Korpus-Luecke (14.07.2026): die lokale Dev-DB ist auf Entwicklungsmaschinen oft
# nur ein SUBSET (z. B. ohne die englischen DDB-Buecher). Korpusabhaengige Regressionen -
# etwa der Deutsch-first-Ranking-Bug 'Reaktionen'/'Counterspell' - bleiben dort UNSICHTBAR
# gruen. Nach jedem Deploy / srd-de-Re-Import daher zusaetzlich `make test-golden-pi` gegen
# den VOLLEN Bestand fahren (RUNBOOK §2).

.PHONY: test test-haupt test-ddb test-daten test-golden-pi

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

# Golden-Suite gegen den VOLLEN Bestand im Pi-Container (Regel-Semantik am echten Korpus,
# nicht am Mac-Subset). PI = SSH-Ziel des Pi (Default-Platzhalter; mit der echten LAN-Adresse
# ueberschreiben: `make test-golden-pi PI=pi@<host>`). Pflicht nach Deploy / srd-de-Re-Import.
PI ?= pi@raspberrypi.local
test-golden-pi:
	ssh $(PI) 'cd ~/foliant && docker compose exec -T -w /app foliant python -m pytest -q tests/test_golden_bestand.py'

# Glossar-Tabelle vom Pi (voller Bestand) in die lokale Dev-DB uebernehmen: macht lokale
# Abnahmen belastbar - die Mac-DB ist nur ein Subset, ihre '*'-Sterne sind sonst nicht
# aussagekraeftig (Korpus-Luecke, s. CLAUDE.md). Ersetzt die LOKALE glossar-Tabelle komplett.
.PHONY: glossar-vom-pi
# DB komplett ziehen und nur die glossar-Tabelle uebernehmen (ATTACH): der fruehere Weg
# ueber die sqlite3-CLI scheiterte, weil sie auf dem Pi-HOST nicht installiert ist
# (nur im Container). Der Download (~10 MB) laeuft gegen die Online-DB - fuer die reine
# glossar-Uebernahme unkritisch (Tabelle aendert sich nur bei admin-glossar-Laeufen).
glossar-vom-pi:
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
