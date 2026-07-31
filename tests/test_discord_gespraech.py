"""GespraechsSpeicher: TTL, LRU-Deckel, Zeichen-Budget - alles mit injizierter Uhr."""
from app.discord_bot import gespraech
from app.discord_bot.gespraech import GespraechsSpeicher


class Uhr:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_verlauf_waechst_paarweise_und_wird_kopiert():
    s = GespraechsSpeicher(uhr=Uhr())
    s.ergaenze(1, "Frage A?", "Antwort A.")
    v = s.verlauf(1)
    assert v == [{"role": "user", "content": "Frage A?"},
                 {"role": "assistant", "content": "Antwort A."}]
    v.append({"role": "user", "content": "Manipulation"})
    assert len(s.verlauf(1)) == 2                        # Kopie, kein Durchgriff


def test_nachrichten_deckel_wirft_aelteste_paare():
    s = GespraechsSpeicher(max_nachrichten=4, uhr=Uhr())
    for i in range(4):
        s.ergaenze(1, f"F{i}", f"A{i}")
    v = s.verlauf(1)
    assert len(v) == 4
    assert v[0]["content"] == "F2"                       # F0/F1-Paare sind raus


def test_zeichen_budget_kappt_aber_juengstes_paar_bleibt():
    s = GespraechsSpeicher(max_zeichen=50, uhr=Uhr())
    s.ergaenze(1, "x" * 100, "y" * 100)                  # allein schon ueber Budget
    assert len(s.verlauf(1)) == 2                        # bleibt trotzdem (juengstes Paar)
    s.ergaenze(1, "kurz", "knapp")
    assert [n["content"] for n in s.verlauf(1)] == ["kurz", "knapp"]


def test_ttl_vergisst_alte_threads():
    uhr = Uhr()
    s = GespraechsSpeicher(ttl_s=100, uhr=uhr)
    s.ergaenze(1, "F", "A")
    uhr.t = 99
    assert s.kennt(1)
    uhr.t = 201
    assert not s.kennt(1) and s.verlauf(1) == []


def test_lru_verdraengt_das_am_laengsten_unbenutzte():
    uhr = Uhr()
    s = GespraechsSpeicher(max_gespraeche=2, uhr=uhr)
    s.ergaenze(1, "F", "A")
    uhr.t = 1
    s.ergaenze(2, "F", "A")
    uhr.t = 2
    assert s.verlauf(1)                                  # 1 anfassen -> juenger als 2
    uhr.t = 3
    s.ergaenze(3, "F", "A")
    assert s.kennt(1) and s.kennt(3) and not s.kennt(2)


class _Kanal:
    """Duck-Typing statt discord.py: Threads tragen `parent_id`, Kanaele nicht."""
    def __init__(self, id_, parent_id=None):
        self.id, self.parent_id = id_, parent_id


def test_verlaufsschluessel_nimmt_im_thread_die_thread_id():
    """Regression 31.07.2026: `/regel` IM Thread legte den Verlauf unter der ELTERN-ID ab.

    `on_message` sucht ihn unter der Thread-ID und fand ihn deshalb nie - der Nutzer bekam
    HINWEIS_VERGESSEN ("nach einem Neustart vergessen"), obwohl kein Neustart stattfand.
    Ursache war eine einzige `kanal_id`, die zwei Bedeutungen trug: die Allowlist braucht
    den Eltern-Kanal, der Verlauf den Thread."""
    thread = _Kanal(555, parent_id=111)          # /regel wurde IM Thread gefahren
    assert gespraech.verlaufsschluessel(thread) == 555, \
        "im Thread muss die THREAD-ID der Verlaufsschluessel sein, nicht die Eltern-ID"


def test_verlaufsschluessel_nimmt_den_neuen_thread():
    """Im Kanal gefahren: die Antwort eroeffnet einen Thread - dessen ID gilt."""
    kanal = _Kanal(111)
    neuer = _Kanal(999, parent_id=111)
    assert gespraech.verlaufsschluessel(kanal, neuer) == 999


def test_verlauf_ist_unter_dem_schluessel_wiederfindbar():
    """Der Rundlauf, um den es geht: ablegen wie `_slash_regel`, finden wie `on_message`."""
    speicher = gespraech.GespraechsSpeicher()
    thread = _Kanal(555, parent_id=111)
    speicher.ergaenze(gespraech.verlaufsschluessel(thread), "Was ist ein Gelegenheitsangriff?", "…")
    assert speicher.kennt(thread.id), \
        "Folgefrage im selben Thread findet den Verlauf nicht"
