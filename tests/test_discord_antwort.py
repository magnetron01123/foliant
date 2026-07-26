"""Discord-Antwortaufbereitung: Splitting an Absatzgrenzen, Codeblock-Zaeune ueber
Splitgrenzen, Belegzeile nie als Waise, Thread-Titel-Limit."""
from app.discord_bot import antwort


def test_kurze_antwort_bleibt_eine_nachricht():
    assert antwort.teile("Ja - Gelegenheitsangriff ist erlaubt.") == \
        ["Ja - Gelegenheitsangriff ist erlaubt."]
    assert antwort.teile("   ") == []


def test_split_an_absatzgrenzen():
    a = "A" * 1000
    b = "B" * 1000
    c = "C" * 500
    teile = antwort.teile(f"{a}\n\n{b}\n\n{c}", limit=1900)
    assert len(teile) == 2
    assert teile[0] == a and teile[1] == f"{b}\n\n{c}"
    assert all(len(t) <= 1900 for t in teile)


def test_belegzeile_wandert_mit_ihrem_absatz():
    """Die Belegzeile haengt am Inhalt, den sie belegt - sie darf nie allein am Anfang
    einer Folge-Nachricht stehen (weder beim Absatz- noch beim Zeilen-Split)."""
    inhalt = "\n".join(f"Merkmalszeile {i:02d}: Beschreibung des Effekts." for i in range(60))
    beleg = "📖 Quelle: SRD 5.2.1 (Deutsch) · S. 241 · Regelversion: 2024"
    teile = antwort.teile(f"Kurzer Einstieg.\n\n{inhalt}\n\n{beleg}", limit=900)
    assert len(teile) >= 3
    assert all(not t.lstrip().startswith("📖") for t in teile)
    assert teile[-1].rstrip().endswith(beleg)            # Beleg unter Inhalt, am Ende
    assert "Merkmalszeile" in teile[-1]                  # nicht allein


def test_belege_anheften_zieht_inhaltszeile_nach():
    """Restfall des harten Splits: steht der Beleg doch allein, wandert die letzte
    Inhaltszeile des Vorgaengers zu ihm - Zaunzeilen werden nie bewegt."""
    beleg = "📖 Quelle: X · Regelversion: 2024"
    saniert = antwort._belege_anheften(["Zeile A\nZeile B", beleg], limit=200)
    assert saniert == ["Zeile A", f"Zeile B\n{beleg}"]
    mit_zaun = antwort._belege_anheften(["Kopf\n```", beleg], limit=200)
    assert mit_zaun == ["Kopf\n```", beleg]              # Zaun bleibt, wo er ist


def test_offener_codeblock_wird_geschlossen_und_wieder_geoeffnet():
    zeilen = "\n".join(f"Zeile {i:03d} | Wert {i}" for i in range(80))
    text = f"Der Statblock:\n\n```text\n{zeilen}\n```\n\nDanach normaler Text."
    teile = antwort.teile(text, limit=800)
    assert len(teile) >= 2
    for t in teile:
        assert t.count("```") % 2 == 0, f"unausgeglichene Zaeune in: {t[:80]}..."
    assert teile[1].startswith("```text\n")             # Zaun im Folgeteil wieder auf


def test_pathologisch_lange_zeile_wird_hart_geschnitten():
    teile = antwort.teile("W" * 5000, limit=1900)
    assert [len(t) for t in teile] == [1900, 1900, 1200]


def test_thread_titel_kollabiert_und_kappt():
    assert antwort.thread_titel("  Was   macht\nFeuerball? ") == "Was macht Feuerball?"
    lang = antwort.thread_titel("F" * 300)
    assert len(lang) == 100 and lang.endswith("…")
    assert antwort.thread_titel("   ") == "Regelfrage"


def test_fehlertexte_je_stop_grund():
    assert antwort.fehlertext("end_turn") is None
    assert "enger stellen" in antwort.fehlertext("runden_cap")
    assert antwort.fehlertext("max_tokens").startswith("⚠️")
    assert antwort.fehlertext("refusal").startswith("🚫")
