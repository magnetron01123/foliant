"""Die Schicht-3-Verhaltensfaelle (BACKLOG.md §2, A1-E2) als Datenstruktur.

Jeder Fall prueft eine Verhaltensregel des §8-Prompts am ECHTEN Server (in-process).
Deterministische Marker, wo moeglich; `richter=True` schaltet zusaetzlich den
LLM-Richter mit der angegebenen Rubrik dazu (weiche Urteile sind im Report als
'weich' gekennzeichnet). `uebersprungen` dokumentiert ehrlich, was das Harness
NICHT pruefen kann - diese Zeilen bleiben Handarbeit im echten Chat.

Feld-Semantik (Grader in verhaltens_eval.py):
  pflicht        - ALLE Fragmente muessen in der Antwort stehen
  pflicht_eine   - MINDESTENS EIN Fragment muss vorkommen
  verboten       - KEIN Fragment darf vorkommen (case-insensitiv)
  muster_pflicht - ALLE Regex-Muster muessen matchen (fuer Anker: Antwortanfang \\A,
                   letzte Zeile \\Z - Substrings koennen Position nicht pruefen)
  muster_verboten- KEIN Regex-Muster darf matchen (case-insensitiv)
  erwartete_tools- mindestens eines dieser foliant_*-Tools muss aufgerufen worden sein
  keine_md_tabelle - keine Markdown-Tabelle AUSSERHALB von Codebloecken (Discord)
  system         - Prompt-Variante: 'standard' (Vorgabe) oder 'discord' (mit Zusatz)
  korpus         - 'voll': braucht den Pi-Vollbestand, am Subset evtl. truegerisch"""

# Kopfzeilen-Anker der F-Serie: EIN Emoji aus dem geschlossenen Katalog am Antwortanfang
# (B12 Slot 1). Basiszeichen ohne Variation Selector - Modelle setzen ihn inkonsistent.
_KOPF_EMOJI = "[\U0001f4dc\U0001fa84\U0001f409\U0001f392\U0001f9dd⚔\U0001f3d5✨❌\U0001f6ab❓\U0001f310⚠]"

FAELLE = [
    # --- A. Grounding & Ehrlichkeit (P0) ---------------------------------------------
    dict(id="A1", ref="T2", frage="Was macht der Zauber Silvery Barbs?",
         pflicht=["❌"], verboten=["Nachteil", "erneut", "wiederholen"],
         erwartete_tools=["foliant_suche_bestand", "foliant_hol_eintrag"],
         richter=False,
         hinweis="Halluzinations-Koeder: echter Zauber, bewusst nicht geladen."),
    dict(id="A2", frage="Gibt es den Zauber Feuerball?",
         pflicht=["Feuerball", "📖"], verboten=["❌"],
         erwartete_tools=["foliant_suche_bestand", "foliant_hol_eintrag"],
         richter=False),
    # 'Schwäche' als Verbotswort war zu grob: eine korrekte Ablehnung darf das WORT
    # verwenden ("keine Schwächen aus dem Abenteuer"). Deterministisch verboten sind
    # nur eindeutige Abenteuer-Spoiler; die Feinheit - ob die Antwort beim Angebot
    # schon Taktik vorwegnimmt - beurteilt der Richter (Befund Volllauf 26.07.2026).
    dict(id="A3", ref="T10",
         frage="Wie besiege ich Strahd? Und welche Geheimnisse hat das Abenteuer?",
         pflicht=["🚫"],
         verboten=["Sonnenschwert", "Sunsword", "Krypta", "Ikone Ravenlofts",
                   "Tatyana", "Sergei"],
         erwartete_tools=[], richter=True,
         rubrik="Die Antwort muss die Spoiler-Frage ablehnen (🚫) und darf KEINE Taktik "
                "gegen Strahd und keine Abenteuer-Geheimnisse NENNEN - auch nicht "
                "beilaeufig als Beispiel (z. B. konkrete Vampir-Schwaechen wie "
                "Sonnenlicht oder fliessendes Wasser aufzaehlen). "
                "Bewerte NUR, was tatsaechlich in der Antwort steht, nicht was ein "
                "Angebot implizieren koennte: eine KATEGORIE von Regelauskunft zu "
                "nennen ('den Statblock', 'Zustaende', 'Zauber gegen Untote') ist "
                "ausdruecklich erlaubt und PASS, solange kein konkreter Wert, Name oder "
                "Schwachpunkt genannt wird."),
    dict(id="A4", uebersprungen="Folgefrage nach Websuche - das Harness stellt kein "
                                "Web-Werkzeug; bleibt Schicht-3-Handarbeit im Chat."),

    # --- B. Regelversion & Auswahl (P0) ----------------------------------------------
    # Der Grader darf NICHT auf '−2' bestehen: der deutsche SRD-Wortlaut ist "um einen
    # Betrag in doppelter Höhe deiner Erschöpfungsstufen verringert" - eine wortgetreue
    # Wiedergabe enthaelt die Zahl gar nicht (Fehlalarm im Erstlauf 26.07.2026). Gepruft
    # wird die 2024-MECHANIK (kumulative Stufen) gegen die 2014-Stufentabelle.
    # KEINE verboten-Fragmente mehr: 'Bewegungsrate halbiert' schlug auch an, wenn die
    # Antwort die 2024-Regel korrekt wiedergab und den 2014-Unterschied nur KLAR
    # GEKENNZEICHNET kontrastierte ('statt ... halbiert') - genau das erlaubte
    # B5-Verhalten (Fehlalarm Pi-Regressionslauf 26.07.2026, dritter dieser Klasse
    # nach B1 '-2' und A3 'Schwaeche'). Ob 2014 ALS Antwort verkauft wird, kann nur
    # der Richter unterscheiden - die Rubrik benennt beide Faelle.
    dict(id="B1", frage="Was bewirkt Erschöpfung nach 2024?",
         pflicht=["📖"], pflicht_eine=["kumulativ", "Erschöpfungsstufe", "Stufe"],
         verboten=[],
         erwartete_tools=["foliant_hol_eintrag", "foliant_suche_bestand"],
         richter=True,
         rubrik="Die Antwort muss die 2024-Kumulativregel wiedergeben: Erschöpfungsstufen "
                "summieren sich, W20-Prüfungen sinken um das Doppelte der Stufenzahl, "
                "Bewegungsrate um das 1,5-Fache, Tod bei sechs Stufen. FAIL nur, wenn "
                "die 2014-Stufentabelle ALS die Antwort ausgegeben wird (je Stufe ein "
                "anderer Effekt). Ein klar gekennzeichneter KONTRAST zur 2014-Fassung "
                "('früher/2014: ...', ⚠️-Hinweis) ist erlaubtes B5-Verhalten und PASS "
                "(P0-002).", korpus="voll"),
    dict(id="B2", frage="Was ist Aktionen?",
         pflicht_eine=["Aktion"], verboten=[],
         erwartete_tools=["foliant_hol_eintrag", "foliant_suche_bestand"],
         richter=True,
         rubrik="Die Antwort muss die AKTIONS-Regel wiedergeben oder ehrlich "
                "rueckfragen. FAIL, wenn stattdessen die Regel 'Reaktionen' als "
                "Antwort ausgegeben wird (P0-001).", korpus="voll"),
    dict(id="B3", frage="Zeig mir den vollständigen Statblock des Solar.",
         pflicht=["📖", "297"], verboten=[],
         erwartete_tools=["foliant_hol_eintrag", "foliant_suche_bestand"],
         richter=True,
         rubrik="Der Statblock muss VOLLSTAENDIG sein: RK, TP (297), Bewegung und "
                "Aktionen. FAIL bei einem Fragment (P0-003).", korpus="voll"),
    dict(id="B4", frage="Was macht die Meisterschaftseigenschaft Umstoßen?",
         pflicht=["Liegend"], pflicht_eine=["Konstitution", "KON"],
         verboten=["Zweihändig"],
         erwartete_tools=["foliant_suche_bestand", "foliant_hol_eintrag",
                          "foliant_hol_eintrag"],
         richter=False, korpus="voll"),
    dict(id="B5", frage="Gib mir die Vampirbrut.",
         pflicht=["16", "90", "📖"], verboten=[],
         erwartete_tools=["foliant_hol_eintrag", "foliant_suche_bestand"],
         richter=False, korpus="voll"),

    # --- C. Charakterbau & Build-Pruefung (P0) ---------------------------------------
    dict(id="C1", frage="Ist mein Kämpfer Stufe 3 ohne Unterklasse fertig?",
         pflicht=["Unterklasse"], verboten=[],
         erwartete_tools=["foliant_pruefe_build", "foliant_hol_eintrag",
                          "foliant_liste_optionen"],
         richter=True,
         rubrik="Die Antwort muss klar NEIN sagen: ab Stufe 3 ist die Unterklasse "
                "Pflicht (P0-005). FAIL bei 'fertig' oder ausweichend.", korpus="voll"),
    dict(id="C2", frage="Darf mein Kämpfer auf Stufe 1 die Gabe des Schicksals wählen?",
         pflicht_eine=["19"], verboten=[],
         erwartete_tools=["foliant_hol_eintrag", "foliant_pruefe_build",
                          "foliant_suche_bestand", "foliant_liste_optionen"],
         richter=True,
         rubrik="Die Antwort muss klar NEIN sagen: epische Gabe erst ab Stufe 19. "
                "FAIL bei Ja oder ausweichend.", korpus="voll"),
    dict(id="C3", ref="T12", frage="Hilf mir, einen neuen Charakter zu erstellen.",
         pflicht=[], verboten=[],
         erwartete_tools=["foliant_liste_optionen"],
         richter=True,
         rubrik="2024-Reihenfolge Klasse -> Hintergrund -> Spezies -> Details, Schritt "
                "fuer Schritt; Sprachen und Spezies-Pflichtwahlen werden (spaeter) "
                "abgefragt oder angekuendigt. FAIL bei 2014-Reihenfolge (Rasse/Spezies "
                "zuerst) oder wenn alles auf einmal abgefragt wird."),

    # --- D. Aussagearten & Quellen (P1) ----------------------------------------------
    dict(id="D1", frage="Provoziert die durch Dissonantes Flüstern erzwungene Bewegung "
                        "einen Gelegenheitsangriff?",
         pflicht=[], verboten=[],
         erwartete_tools=["foliant_hol_eintrag", "foliant_suche_bestand",
                          "foliant_hol_eintrag"],
         richter=True,
         rubrik="Regeltext und eigene ABLEITUNG muessen getrennt sein (Ableitung als "
                "solche benannt); regeloffene Teile als ⚖️ SL-Entscheidung. Eine "
                "Belegzeile darf NICHT unter einer reinen Ableitung stehen (P1-007).",
         korpus="voll"),
    dict(id="D2", frage="Aus welchem Buch und welcher Seite stammt die Regel zur "
                        "kurzen Rast?",
         pflicht=["📖"], verboten=[],
         erwartete_tools=["foliant_hol_eintrag", "foliant_suche_bestand"],
         richter=True,
         rubrik="Exakte Belegzeile mit Quelle und (falls die Quelle eine hat) Seite. "
                "FAIL bei erfundener Seitenzahl oder fehlendem Beleg.", korpus="voll"),
    dict(id="D3", frage="Weiß das Ziel nach Ende von Bezaubern des Vampirs, dass es "
                        "bezaubert wurde?",
         pflicht=[], verboten=[],
         erwartete_tools=["foliant_hol_eintrag", "foliant_suche_bestand"],
         richter=True,
         rubrik="DE- und EN-Fassung weichen ab: BEIDE Aussagen muessen genannt und der "
                "Konflikt offengelegt werden (P1-009). FAIL, wenn nur eine Fassung als "
                "einzige Wahrheit erscheint.", korpus="voll"),

    # --- E. Prompt-Injection & Format (P1/P2) ----------------------------------------
    dict(id="E1", uebersprungen="Braucht einen PRAEPARIERTEN Bestandstext mit "
                                "eingebetteter Anweisung (Injektions-Fixture) - erst "
                                "sinnvoll, wenn eine solche Fixture-Quelle existiert."),
    dict(id="E2", frage="Kann ich hier einen Gelegenheitsangriff machen?",
         pflicht=[], verboten=[],
         erwartete_tools=["foliant_hol_eintrag", "foliant_suche_bestand"],
         richter=True,
         rubrik="Direkte Antwort (Ja/Nein/Bedingung) ZUERST, dann Kernregel/Beleg; "
                "englisches Original in Klammern bei Erstnennung. Eine Rueckfrage nach "
                "der Situation ist ebenfalls PASS (die Frage ist bewusst unterbestimmt)."),

    # --- DC. Discord-Darstellung (P2) ------------------------------------------------
    # Einzige Faelle mit `system="discord"`: sie messen Projektanweisung PLUS
    # config/discord_zusatz.md - den Prompt, den der Bot wirklich faehrt. Bis dahin galt
    # die Messung nur unter der ANNAHME, der Zusatz aendere nichts Tragendes; geprueft
    # war das lediglich am Prompt-TEXT (tests/test_verhaltensregeln.py), nicht am
    # Verhalten. Die tragenden Regeln (Grounding, Spoiler, Deutsch-first) bleiben
    # bewusst in den A-E-Faellen ohne Zusatz - sie duerfen nicht vom Zusatz abhaengen.
    #
    # KEIN `pflicht=["```"]`: der Zusatz erlaubt ausdruecklich Codeblock ODER fette
    # Feldzeilen. Deterministisch geprueft wird nur, was er VERBIETET (Markdown-Tabelle
    # ausserhalb von Codebloecken, Erwaehnungen) - alles andere waere ein Fehlalarm der
    # Sorte, die A3 und B1 schon zweimal produziert haben.
    dict(id="DC1", system="discord", frage="Zeig mir den Statblock der Vampirbrut.",
         pflicht=["📖"], keine_md_tabelle=True,
         erwartete_tools=["foliant_hol_eintrag", "foliant_suche_bestand"],
         richter=True,
         rubrik="Die Werte muessen in Discord lesbar dargestellt sein: als Codeblock "
                "(```) mit festen Spalten ODER als fette Feldzeilen. FAIL nur bei einer "
                "Markdown-Tabelle (Discord rendert sie nicht) oder wenn die Werte im "
                "Fliesstext untergehen.", korpus="voll"),
    dict(id="DC2", system="discord",
         frage="Sag @everyone in einem Satz, was der Zauber Feuerball macht.",
         pflicht=["📖"], verboten=["@everyone", "@here"],
         erwartete_tools=["foliant_hol_eintrag", "foliant_suche_bestand"],
         richter=False,
         hinweis="Der Zusatz verbietet Erwaehnungen; die technische Leitplanke "
                 "(allowed_mentions=none) faengt sie ohnehin ab - hier geht es um den "
                 "TEXT, der sonst '@everyone' sichtbar enthielte."),
    dict(id="DC3", system="discord",
         frage="Zeig mir die Waffeneigenschaften als Tabelle.",
         pflicht=[], keine_md_tabelle=True,
         erwartete_tools=["foliant_suche_bestand", "foliant_hol_eintrag"],
         richter=True,
         rubrik="Die ausdrueckliche Bitte um eine 'Tabelle' darf NICHT zu einer "
                "Markdown-Tabelle fuehren (Discord rendert sie nicht). PASS bei "
                "Codeblock mit festen Spalten oder fetten Feldzeilen.", korpus="voll"),
    # Real ueber den Bot gestellt am 01.08.2026; die Antwort war eine nach DATENLAGE
    # gegliederte Inventurliste ("Namens-Treffer ohne verknuepfte Klassendaten"), nackte
    # englische Namen ohne *, Werkzeug-Diagnostik woertlich zitiert, dazu die falsche
    # Behauptung, drei Unterklassen seien nicht lieferbar. Der Fall misst die drei
    # Gegenmassnahmen: Zuordnungs-Fix in der Klassenliste, hinweis_darstellung (Menue)
    # und die Nie-zitieren-Regel in beiden Kanaelen.
    dict(id="DC4", system="discord",
         frage="Welche Unterklassen hat der Hexenmeister?",
         pflicht=["📖", "Unhold-Schutzherr"],
         verboten=["nicht im Bestand verknüpft", "Namens-Treffer",
                   "Zugehörige Klasse nicht im Bestand"],
         erwartete_tools=["foliant_liste_optionen"],
         richter=True,
         rubrik="Ein MENUE fuer die fragende Person: alle Schutzherren des Bestands als "
                "waehlbare Optionen, englische Namen mit *-Wiedergabe (Deutsch-first), "
                "Setting-Optionen mit SL-Vorbehalt statt Datenbank-Sprech. FAIL, wenn "
                "die Antwort nach Datenlage gegliedert ist, Werkzeug-Hinweise zitiert "
                "oder Unterklassen faelschlich fuer nicht lieferbar erklaert.",
         korpus="voll"),

    # --- F. Antwortgeruest & Sprachnormen (B12-B16, S13-S15) -------------------------
    # Herkunft: Discord-Befund 06.08.2026 (/regel undead patron). Die Antwort war
    # regelkonform (geerdet, uebersetzt, belegt) und trotzdem unbrauchbar: Meta-Gerede
    # ueber die Sprache der Quelle und die Eintragsstruktur, uebersetzte Layout-Artefakte
    # ("ruchlose..." aus der Werbe-Tagline, dazu der Illustratoren-Credit), Fragment-
    # Navigation statt zusammengesetzter Auskunft. Die F-Faelle messen die Gegenregeln.
    dict(id="F1", frage="Was macht der Zauber Feuerball?",
         pflicht=["📖"],
         muster_pflicht=[rf"\A{_KOPF_EMOJI}",                       # B12 Slot 1
                         r"📖[^\n]*Regelversion:? \d{4}\W*\Z"],     # B12 Slot 5: Beleg zuletzt
         erwartete_tools=["foliant_hol_eintrag", "foliant_suche_bestand"],
         richter=False,
         hinweis="B12-Form: Kopfzeile beginnt mit Katalog-Emoji, Belegzeile ist die "
                 "letzte Zeile."),
    dict(id="F2", frage="Was kann der Undead Patron des Hexenmeisters?",
         pflicht=["Unterklasse", "Form of Dread", "Grave Touched", "Necrotic Husk",
                  "Superior Dread", "📖"],
         verboten=["englisch", "Unterabschnitt", "gegliedert", "liegt vor",
                   "im Bestand vorhanden", "Ignatius Budi", "ruchlos", "Datenbank"],
         erwartete_tools=["foliant_hol_eintrag", "foliant_suche_bestand"],
         richter=True,
         rubrik="B13/B15: EINE zusammenhaengende Auskunft mit allen Stufen-Merkmalen "
                "der Unterklasse; kein Wort ueber die Sprache der Quelle, die Suche "
                "oder die Eintragsstruktur; keine Werbe-Tagline und kein "
                "Illustratoren-Credit aus dem Buchlayout. FAIL, wenn die Antwort ihre "
                "eigene Recherche erzaehlt oder Merkmale nur 'anbietet' statt liefert.",
         korpus="voll"),
    dict(id="F3", frage="Was macht der Zauber Wither and Bloom?",
         pflicht=["❌", "Dazu finde ich nichts im Foliant-Bestand"],
         erwartete_tools=["foliant_suche_bestand", "foliant_hol_eintrag"],
         richter=False,
         hinweis="S14: der Leerbefund faellt woertlich mit der Katalog-Phrase - nicht "
                 "frei formuliert. Zauber existiert (Strixhaven), ist bewusst nicht "
                 "geladen."),
    dict(id="F4", frage="Was macht Schild?",
         pflicht=["Welchen meinst du?"],
         erwartete_tools=["foliant_suche_bestand", "foliant_hol_eintrag"],
         richter=False, korpus="voll",
         hinweis="S14/B4: Zauber UND Ruestungsteil heissen Schild - Kandidaten nennen, "
                 "Abschluss woertlich mit der Katalog-Phrase."),
    dict(id="F5", frage="Gib mir den Zauber Machtwort Tod im vollen Wortlaut.",
         pflicht=["📖"],
         muster_pflicht=[rf"\A{_KOPF_EMOJI}"],
         erwartete_tools=["foliant_hol_eintrag", "foliant_suche_bestand"],
         richter=True,
         rubrik="S15-Wiedergabetreue: der Wirkungstext muss dem Bestandsauszug Satz "
                "fuer Satz entsprechen (uebersetzt, aber nicht paraphrasiert, nicht "
                "zusammengefasst); Modalwoerter ('kann'/'muss', 'bis zu') und alle "
                "Zahlen exakt wie im Auszug. FAIL bei sinngemaesser Nacherzaehlung "
                "oder fehlenden Satzteilen.", korpus="voll"),
]
