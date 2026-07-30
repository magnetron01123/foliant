"""Verlaufs-Rebuild aus der Discord-Historie: Paarbildung, zusammengesetzte Antworten,
Ersatzfrage aus dem Thread-Titel, Meldungen als Nicht-Antworten. Die Negativfaelle sind
hier die eigentliche Absicherung - ein verwaister Turn im Verlauf waere ein kaputter
Kontext, den die Messages-API zurueckweist."""
from app.discord_bot import antwort, rebuild, schranken

BOT, NUTZER = True, False


def test_einfaches_paar():
    verlauf = rebuild.baue_verlauf([(NUTZER, "Was macht Feuerball?"),
                                    (BOT, "Feuerball macht 8W6 Schaden.")])
    assert verlauf == [{"role": "user", "content": "Was macht Feuerball?"},
                       {"role": "assistant", "content": "Feuerball macht 8W6 Schaden."}]


def test_geteilte_antwort_wird_wieder_zusammengefuegt():
    """Aufeinanderfolgende Bot-Nachrichten sind die Teile EINER Antwort."""
    verlauf = rebuild.baue_verlauf([(NUTZER, "Frage?"), (BOT, "Teil eins."),
                                    (BOT, "Teil zwei."), (BOT, "📖 Quelle: SRD")])
    assert len(verlauf) == 2
    assert verlauf[1]["content"] == "Teil eins.\n\nTeil zwei.\n\n📖 Quelle: SRD"


def test_rollen_wechseln_sich_streng_ab():
    verlauf = rebuild.baue_verlauf([(NUTZER, "F1"), (BOT, "A1"),
                                    (NUTZER, "F2"), (BOT, "A2")])
    assert [n["role"] for n in verlauf] == ["user", "assistant", "user", "assistant"]


def test_unbeantwortete_frage_faellt_raus():
    """Im vergessenen Thread reden Leute weiter - ein user-Turn ohne Antwort wuerde
    die Abwechslung brechen. Es zaehlt die letzte Frage vor der Antwort."""
    verlauf = rebuild.baue_verlauf([(NUTZER, "Zwischenruf"), (NUTZER, "Echte Frage?"),
                                    (BOT, "Antwort.")])
    assert [n["content"] for n in verlauf] == ["Echte Frage?", "Antwort."]
    # ... und ganz am Ende steht die NEUE Frage, die gerade beantwortet werden soll:
    assert rebuild.baue_verlauf([(NUTZER, "F"), (BOT, "A"), (NUTZER, "neu")]) == \
        [{"role": "user", "content": "F"}, {"role": "assistant", "content": "A"}]


def test_herrenlose_antwort_ohne_ersatzfrage_wird_verworfen():
    assert rebuild.baue_verlauf([(BOT, "Antwort ohne Frage.")]) == []


def test_ersatzfrage_traegt_den_regel_fall():
    """/regel: die Frage steht nirgends im Kanal, der Startbeitrag ist Teil 1 der
    Antwort - der Thread-Titel springt ein."""
    verlauf = rebuild.baue_verlauf([(BOT, "Antwort Teil 1."), (BOT, "Teil 2."),
                                    (NUTZER, "Nachfrage?"), (BOT, "Antwort 2.")],
                                   ersatzfrage="Was macht Feuerball?")
    assert verlauf[0] == {"role": "user", "content": "Was macht Feuerball?"}
    assert verlauf[1]["content"] == "Antwort Teil 1.\n\nTeil 2."
    assert [n["content"] for n in verlauf[2:]] == ["Nachfrage?", "Antwort 2."]


def test_ersatzfrage_gilt_nur_am_anfang():
    """Spaeter im Thread ist eine herrenlose Bot-Nachricht kein /regel-Start mehr -
    sie an den Titel zu haengen, erfaende einen Gespraechsschritt."""
    verlauf = rebuild.baue_verlauf([(NUTZER, "F"), (BOT, "A"), (BOT, "Nachtrag")],
                                   ersatzfrage="Titel")
    assert verlauf == [{"role": "user", "content": "F"},
                       {"role": "assistant", "content": "A\n\nNachtrag"}]


def test_meldungen_sind_keine_antworten():
    for meldung in (antwort.FEHLER_API, antwort.FEHLER_RUNDEN_CAP,
                    antwort.FEHLER_REFUSAL, antwort.HINWEIS_VERGESSEN,
                    schranken.ABGELEHNT_COOLDOWN, schranken.ABGELEHNT_TAGESDECKEL,
                    schranken.ABGELEHNT_LAEUFT):
        assert rebuild.baue_verlauf([(NUTZER, "Frage?"), (BOT, meldung)]) == [], meldung


def test_teiltext_mit_max_tokens_hinweis_bleibt_erhalten():
    """Der max_tokens-Hinweis haengt an einer echten Antwort - nur die ALLEIN stehende
    Meldung faellt raus, nicht der Teiltext davor."""
    text = f"Der halbe Statblock.\n\n{antwort.FEHLER_MAX_TOKENS}"
    verlauf = rebuild.baue_verlauf([(NUTZER, "Frage?"), (BOT, text)])
    assert verlauf[1]["content"] == text


def test_leere_nachrichten_werden_uebersprungen():
    verlauf = rebuild.baue_verlauf([(NUTZER, "  "), (NUTZER, "Frage?"),
                                    (BOT, ""), (BOT, "Antwort.")])
    assert [n["content"] for n in verlauf] == ["Frage?", "Antwort."]
