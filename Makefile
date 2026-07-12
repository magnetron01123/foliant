# Foliant - Test-Gate (SYN-P1-001): EIN Befehl fuer die komplette lokale Pruefung.
# "pytest gruen" heisst ab jetzt: Haupt-Suite UND DDB-Suite (eigene .venv-ddb) - die
# DDB-Tests werden im Haupt-venv uebersprungen und blieben sonst unsichtbar rot.
# Smoke + admin check laufen nur, wenn die lokale Dev-DB existiert (echte Daten).

.PHONY: test test-haupt test-ddb test-daten

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
