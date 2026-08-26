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
# ALLE drei Dienste, die Code aus dem Repo backen (build: .) - foliant, web, discord.
# Bis zum 03.08.2026 stand hier nur `foliant`: Nach einem Deploy liefen Bot und Website
# still mit dem ALTEN Image weiter, obwohl das Image den Code per COPY einbackt. Real
# passiert: der /regel-Absturz war im Repo behoben, deployt - und in Discord trotzdem
# noch da, weil der discord-Container nie neu gebaut wurde. `--no-deps`, damit
# depends_on nicht gateway/cloudflared mit durchstartet (Gotcha in CONCEPT.md par. 12).
# Eval-Reports VOR dem Rebuild aus dem Container ziehen (CONCEPT.md par. 12): Sie leben
# in /app und sterben mit dem alten Image - dabei sind sie die Kalibriergrundlage fuer
# jedes neue Pruefmuster. Zweimal in einer Woche (07./08.08.2026) waeren sie ohne den
# Handgriff verloren gewesen; jetzt macht ihn der Deploy selbst.
#
# Nicht blockierend, aber LAUT: Bis zum 14.08.2026 waren beide Schritte `-`-praefigiert
# und die Schlusszeile zaehlte nur, was ohnehin schon lokal lag - ein gescheiterter
# Rettungslauf meldete denselben Erfolg wie ein geglueckter. Ein Rettungsschritt, dessen
# Scheitern man nicht sieht, ist keiner. Ein frischer Container ohne Reports bricht
# weiterhin keinen Deploy ab, sagt es jetzt aber.
.PHONY: sichere-eval-reports-pi
sichere-eval-reports-pi: _pi-ziel
	@mkdir -p evals/ergebnisse/pi
	@vorher=$$(ls evals/ergebnisse/pi/*.json 2>/dev/null | wc -l | tr -d ' '); \
	if ssh $(PI) 'cd ~/foliant && rm -rf /tmp/eval-reports && docker compose cp foliant:/app/evals/ergebnisse /tmp/eval-reports' >/dev/null 2>&1 \
	   && scp -q '$(PI):/tmp/eval-reports/*.json' evals/ergebnisse/pi/ 2>/dev/null; then \
		nachher=$$(ls evals/ergebnisse/pi/*.json 2>/dev/null | wc -l | tr -d ' '); \
		echo "Eval-Reports gesichert: $$((nachher - vorher)) neu, lokal gesamt $$nachher."; \
	else \
		echo "WARNUNG: Eval-Reports NICHT gesichert (lokal unveraendert: $$vorher)."; \
		echo "         Der folgende Rebuild verwirft alles, was seit dem letzten"; \
		echo "         Rettungslauf im Container entstanden ist. Abbrechen mit Strg-C."; \
		sleep 5; \
	fi

# `test` als Vorbedingung (seit 14.08.2026): Bis dahin pruefte der Deploy erst NACH dem
# Live-Schalten - die Golden-Suite braucht den Vollbestand und kann nicht vorher laufen,
# aber die 1.220 lokalen Tests koennen es sehr wohl. Ein Umbau, den schon der Mac
# durchfallen laesst, hat auf dem Pi nichts verloren.
deploy-pi: _pi-ziel test sichere-eval-reports-pi tag-vorher-pi
	rsync -a --exclude '.git' --exclude '.venv*' --exclude 'data' --exclude 'quellen' \
	      --exclude 'config/foliant.toml' --exclude '.env' --exclude '.claude' \
	      ./ $(PI):~/foliant/
	ssh $(PI) 'cd ~/foliant && docker compose up -d --build --no-deps foliant web discord'
	@echo "--- Rebuild durch, jetzt die Pflicht-Pruefung am Vollbestand ---"
	$(MAKE) test-golden-pi PI=$(PI)
	@echo "--- Regel-Semantik ok, jetzt die DATENQUALITAET am Vollbestand ---"
	$(MAKE) check-pi PI=$(PI)

# Der Rueckweg. Bis zum 14.08.2026 gab es keinen: Auf dem Pi lagen ausschliesslich
# `:latest`-Tags, der alte Stand war nach dem Build ueberschrieben. Die Gates laufen nach
# dem Live-Schalten (die Golden-Suite braucht den Vollbestand) - genau deshalb muss es
# einen Weg zurueck geben, wenn eines von ihnen rot wird.
#
# `-` bei den Tags: Beim allerersten Deploy existiert noch kein Image, das man sichern
# koennte. Das ist kein Fehler, sondern der Normalfall genau einmal.
.PHONY: tag-vorher-pi
tag-vorher-pi: _pi-ziel
	@for d in foliant web discord; do \
		ssh $(PI) "docker image tag foliant-$$d:latest foliant-$$d:vorher" 2>/dev/null \
			&& echo "gesichert: foliant-$$d:vorher" \
			|| echo "Hinweis: foliant-$$d:latest gibt es noch nicht - nichts zu sichern."; \
	done

# Zurueck auf den Stand VOR dem letzten `make deploy-pi`. Kein Build, kein rsync: Es
# werden nur die gesicherten Images zurueckgetauscht und die Container neu erzeugt.
# Der Arbeitsbaum auf dem Pi bleibt, wie der letzte rsync ihn hinterlassen hat - fuer
# das laufende Image ist das egal, weil der Code ins Image gebacken ist (CONCEPT.md
# par. 12). Nach einem Rollback gehoert der Repo-Stand von Hand nachgezogen.
.PHONY: rollback-pi
rollback-pi: _pi-ziel
	@ssh $(PI) 'for d in foliant web discord; do \
		docker image inspect "foliant-$$d:vorher" >/dev/null 2>&1 \
			|| { echo "ABBRUCH: foliant-$$d:vorher fehlt - es gibt keinen gesicherten Stand."; exit 1; }; \
	done'
	ssh $(PI) 'for d in foliant web discord; do docker image tag "foliant-$$d:vorher" "foliant-$$d:latest"; done'
	ssh $(PI) 'cd ~/foliant && docker compose up -d --no-deps --force-recreate foliant web discord'
	@echo "--- Rollback durch, jetzt dieselben Gates wie nach einem Deploy ---"
	$(MAKE) test-golden-pi PI=$(PI)
	$(MAKE) check-pi PI=$(PI)

# Golden-Suite gegen den VOLLEN Bestand im Pi-Container (Regel-Semantik am echten Korpus,
# nicht am Mac-Subset). Pflicht nach Deploy / srd-de-Re-Import.
test-golden-pi: _pi-ziel
	ssh $(PI) 'cd ~/foliant && docker compose exec -T -w /app foliant python -m pytest -q tests/test_golden_bestand.py'

# Datenqualitaet am VOLLBESTAND - Teil jedes Deploys, nicht nur auf Zuruf.
#
# Warum am Pi und nicht lokal: `make test` faehrt `admin check` gegen die Dev-DB, und die
# ist ein SUBSET (4 von 15 Quellen). Alles, was nur am Vollbestand sichtbar wird, faellt
# dort nicht auf - am 01.08.2026 ist genau so eine falsche Prioritaetsband-Tabelle
# durchgegangen: Sie war an einer Config kalibriert, die drei der betroffenen Buecher
# gar nicht enthaelt.
#
# `admin check` beendet bei Problemen mit Exitcode != 0 und bricht damit den Deploy ab.
# Das ist der Punkt: Ein Import, der neue Datenmaengel einschleppt, soll nicht still
# live gehen (die Basiswerte in config/qualitaet_basis.json sagen, was bekannt ist).
check-pi: _pi-ziel
	ssh $(PI) 'cd ~/foliant && docker compose exec -T foliant python -m app.admin check --vollbestand'

# Den Korpus-Sollstand nach einem BEABSICHTIGTEN Import neu erheben. Rein lesend auf dem
# Pi, schreibt lokal `config/korpus_soll.json` - die Datei gehoert in den Commit, sonst
# meldet der naechste `check-pi` die neue Quelle als Abweichung.
#
# Buchtitel bleiben bewusst draussen, solange offen ist, ob DDB-Titel oeffentlich stehen
# duerfen (BACKLOG M9). Die Kuerzel stehen ohnehin schon im Repo.
# Platz auf der SD-Karte zurueckholen. Gemessen am 14.08.2026: 396 Build-Cache-Eintraege,
# 13,48 GB, davon 11,66 GB freigebbar - auf derselben Karte, die Bestand UND alle
# Sicherungen traegt.
#
# BEWUSST NICHT im Deploy: Das Ziel loescht etwas. Ein Aufraeumschritt, der bei jedem
# Deploy ungefragt mitlaeuft, ist genau die Sorte Automatik, die irgendwann das Falsche
# erwischt - und der naechste Build wird ohne Cache spuerbar langsamer. Erst zeigen, was
# ginge; loeschen nur mit `LOESCHEN=ja`.
.PHONY: pflege-pi
pflege-pi: _pi-ziel
	@echo "--- Belegung jetzt ---"
	@ssh $(PI) 'docker system df; echo; df -h / | tail -1'
ifeq ($(LOESCHEN),ja)
	@echo "--- Build-Cache aelter als 7 Tage wird freigegeben ---"
	ssh $(PI) 'docker builder prune --force --filter until=168h'
	@ssh $(PI) 'docker system df'
else
	@echo ""
	@echo "Nichts geloescht. Zum Freigeben des Build-Caches aelter als 7 Tage:"
	@echo "    make pflege-pi LOESCHEN=ja"
endif

.PHONY: soll-vom-pi
soll-vom-pi: _pi-ziel
	@ssh $(PI) 'cd ~/foliant && docker compose exec -T foliant python -m app.admin manifest' \
		| .venv/bin/python deploy/korpus_soll.py
	@git diff --stat config/korpus_soll.json || true

# Das Quellen-Register neu erzeugen (K-01). Wie `soll-vom-pi` ein Wiederherstellungs-
# Artefakt: `config/foliant.toml` ist gitignored und in keinem Backup, die DATENBANK weiss
# es aber besser - sie fuehrt alle 18 Quellen mit Edition, Lizenz, Prioritaet und
# inhaltsart. Buchtitel bleiben draussen (Entscheidung 14.08.2026).
#
# Braucht `admin quellen-register` IM Image, also einen Deploy nach dem 14.08.2026.
# Die eingecheckte Fassung ist bis dahin aus denselben DB-Zeilen erzeugt.
#
# Erst in eine Nebendatei, dann pruefen, dann verschieben. Ein direktes
# `> config/quellen-register.toml` leert die Datei, BEVOR das Kommando laeuft - ein
# Fehlschlag haette also genau das Artefakt vernichtet, das gegen Verlust schuetzen soll
# (beim Bauen am 14.08.2026 einmal passiert und behoben).
.PHONY: register-vom-pi
register-vom-pi: _pi-ziel
	@ssh $(PI) 'cd ~/foliant && docker compose exec -T foliant python -m app.admin quellen-register' \
		> config/quellen-register.toml.neu || true
	@if grep -q '^\[\[quelle\]\]' config/quellen-register.toml.neu 2>/dev/null; then \
		mv config/quellen-register.toml.neu config/quellen-register.toml; \
		echo "Register erneuert: $$(grep -c '^\[\[quelle\]\]' config/quellen-register.toml) Quellen."; \
		git diff --stat config/quellen-register.toml || true; \
	else \
		rm -f config/quellen-register.toml.neu; \
		echo "ABBRUCH: kein Register erhalten - das bestehende bleibt unangetastet."; \
		echo "  Kennt das Pi-Image 'admin quellen-register' schon? Sonst erst deployen."; \
		exit 1; \
	fi

# Der Suchbericht vom VOLLBESTAND, maschinenlesbar - Einstieg in den
# Rueckmeldungs-Durchgang (O4/M5, .claude/ablaeufe/rueckmeldungen.md). Rein lesend.
# Bis 04.08.2026 stand dieser Aufruf nur als Copy-Paste-Zeile in der Doku, und eine Zeile,
# die man abtippt, wird seltener gefahren als eine, die man aufruft.
TAGE ?= 30
.PHONY: bericht-pi
bericht-pi: _pi-ziel
	@ssh $(PI) 'cd ~/foliant && docker compose exec -T foliant python -m app.admin suchbericht --tage $(TAGE) --json'

# Die zweite Haelfte desselben Durchgangs: was der Bericht NICHT weiss, weil es im Repo
# steht und nicht auf dem Pi - Wiederholungszaehler je Regel-ID, offene `spaeter`-Posten,
# frueher abgelehnte Vorschlaege. Lokal, rein lesend, kein SSH.
# Als Ziel und nicht als Handarbeit, weil am Zaehler eine Entscheidung haengt: Ab dem
# dritten Bruch sitzt die Regel im falschen Kanal, und diese Grenze loest die
# `Achtung`-Zeile der Freigabekarte aus.
.PHONY: gedaechtnis
gedaechtnis:
	@.venv/bin/python deploy/rueckmeldungs_gedaechtnis.py

# Der Gespraechskontext um EINE markierte Antwort, live aus Discord. Der Bot-Token liegt
# nur in der Umgebung des discord-Containers und verlaesst den Pi nicht.
# Die Ausgabe gehoert in die Auswertungs-Sitzung und in KEINE Datei: Der Antworttext steht
# bewusst nicht im Protokoll (CONCEPT.md par. 13), ihn beim Auswerten wegzuschreiben waere
# derselbe Schritt durch die Hintertuer.
.PHONY: kontext-pi
kontext-pi: _pi-ziel
	@test -n "$(KANAL)" -a -n "$(NACHRICHT)" || { \
	  echo "FEHLER: KANAL= und NACHRICHT= noetig (aus dem Discord-Link der Markierung)."; \
	  echo "  make kontext-pi KANAL=<kanal-id> NACHRICHT=<nachricht-id>"; \
	  exit 1; }
	@ssh $(PI) 'cd ~/foliant && docker compose exec -T discord python deploy/discord_api.py nachrichten $(KANAL) $(NACHRICHT)'

# Steht ein gekauftes DDB-Buch noch nicht im Bestand? Rein lesend: `--dry-run` zeigt nur,
# was einliefe. Beide Teile in EINEM Ziel, weil die Frage nur aus beiden zusammen zu
# beantworten ist - was liegt drin, und was laege drin.
# Ein gekauftes, nie importiertes Buch ist im Betrieb unsichtbar: Foliant sagt ehrlich
# "nicht im Bestand", und das sieht wie eine korrekte Auskunft aus.
#
# Das fuehrende `-` beim Trockenlauf ist Absicht: "Keine DDB-Artefakte vorhanden" ist ein
# NORMALER Zustand (die Artefakte entstehen erst mit `ddb-exporter sync`) und endet
# trotzdem mit Exitcode 1. Ohne das `-` meldete der monatliche Lauf jedes Mal einen
# Fehler, obwohl nichts kaputt ist - und ein Waechter, der grundlos schreit, wird
# abgeschaltet. Bewertet wird die AUSGABE, nicht der Exitcode: ein echter Fehler (etwa
# ein abgelaufener Cobalt-Cookie) steht dort im Klartext.
.PHONY: ddb-abgleich-pi
ddb-abgleich-pi: _pi-ziel
	@ssh $(PI) 'cd ~/foliant && docker compose exec -T foliant python -m app.admin status'
	@echo
	-@ssh $(PI) 'cd ~/foliant && docker compose exec -T foliant python -m app.admin ddb-import-all --dry-run'

# B9 unter Sessionlast: Antwortzeiten bei mehreren gleichzeitigen Spielern, gegen den
# VOLLEN Pi-Korpus. Rein lesend, gefahrlos neben dem Live-Betrieb. Exitcode != 0, wenn
# p95 die Grenze reisst - der Lauf ist damit auch als Regressionswaechter brauchbar.
lasttest-pi: _pi-ziel
	ssh $(PI) 'cd ~/foliant && docker compose exec -T -w /app foliant python -m evals.lasttest'

# Schicht-3-Verhaltens-Evals gegen den VOLLEN Pi-Korpus (BACKLOG.md par. 2). Kostet echte
# API-Tokens (~15 Faelle x 3-5 Runden). Der Key wird NUR fuer den Einmal-Exec injiziert -
# der Serving-Container traegt dauerhaft keinen (bewusst, docker-compose.yml). Aufruf:
#   ANTHROPIC_API_KEY=sk-... make eval-verhalten-pi
#
# Der Key geht ueber STDIN, nicht ueber die Kommandozeile (Befund 30.07.2026): vorher
# stand er als '-e ANTHROPIC_API_KEY=sk-...' im ssh-Aufruf, damit im lokalen `ps`, in der
# Shell-History UND im `ps` des Pi. Das ist dieselbe Regel, die evals/verhaltens_eval.py
# selbst formuliert und die Cobalt und der Discord-Token bereits einhalten.
# 'docker compose exec -e VAR' OHNE '=wert' reicht die Variable aus der Remote-Shell
# durch - sie taucht in keiner Prozessliste auf.
.PHONY: eval-verhalten-pi
eval-verhalten-pi: _pi-ziel
	@test -n "$$ANTHROPIC_API_KEY" || { echo "FEHLER: ANTHROPIC_API_KEY fehlt."; exit 1; }
	@printf '%s\n' "$$ANTHROPIC_API_KEY" | ssh $(PI) 'read -r ANTHROPIC_API_KEY && export ANTHROPIC_API_KEY && cd ~/foliant && docker compose exec -T -e ANTHROPIC_API_KEY -w /app foliant python -m evals.verhaltens_eval $(EVAL_ARGS)'

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
