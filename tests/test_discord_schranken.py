"""Schranken: Guild-/Kanal-Gate, Ein-Anfrage-Regel, Cooldown, Tagesdeckel-Rollover -
mit injizierter Uhr und injiziertem UTC-Datum."""
from datetime import date

from app.discord_bot import schranken as sch
from app.discord_bot.schranken import Schranken


class Uhr:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def _schranken(**kwargs):
    vorgaben = dict(guild_id=42, tagesdeckel=2, cooldown_s=10.0, uhr=Uhr(),
                    utc_datum=lambda: date(2026, 7, 26))
    vorgaben.update(kwargs)
    return Schranken(**vorgaben), vorgaben["uhr"]


def test_guild_und_kanal_gate():
    s, _ = _schranken(kanal_ids=frozenset({7}))
    assert s.richtiger_ort(42, 7)
    assert not s.richtiger_ort(42, 8)                    # falscher Kanal
    assert not s.richtiger_ort(99, 7)                    # fremde Guild
    offen, _ = _schranken()                              # ohne Kanal-Allowlist
    assert offen.richtiger_ort(42, 12345)


def test_nur_eine_laufende_anfrage_pro_nutzer():
    """beginne() prueft und reserviert atomar: der zweite Aufruf desselben Nutzers
    scheitert, OHNE dass zwischen Pruefung und Reservierung Platz fuer ein await ist."""
    s, _ = _schranken()
    assert s.beginne(1) is None
    assert s.beginne(1) == sch.ABGELEHNT_LAEUFT
    assert s.beginne(2) is None                          # andere Nutzer unberuehrt


def test_cooldown_nach_abschluss():
    s, uhr = _schranken()
    assert s.beginne(1) is None
    uhr.t = 5
    s.beende(1)
    assert s.beginne(1) == sch.ABGELEHNT_COOLDOWN
    uhr.t = 15.1                                         # 10 s nach beende()
    assert s.beginne(1) is None


def test_abgelehnter_beginn_reserviert_nichts():
    """Eine Ablehnung darf weder als 'laufend' haengenbleiben noch den Tagesdeckel
    verbrauchen - sonst sperrte ein Cooldown-Treffer den Nutzer dauerhaft."""
    s, uhr = _schranken(tagesdeckel=2)
    assert s.beginne(1) is None
    s.beende(1)
    assert s.beginne(1) == sch.ABGELEHNT_COOLDOWN        # zaehlt nicht als laufend...
    uhr.t = 15.1
    assert s.beginne(1) is None                          # ...und nicht gegen den Deckel
    s.beende(1)


def test_tagesdeckel_und_utc_rollover():
    heute = {"d": date(2026, 7, 26)}
    s, uhr = _schranken(utc_datum=lambda: heute["d"])
    for nutzer in (1, 2):                                # Deckel 2 ausschoepfen
        assert s.beginne(nutzer) is None
        s.beende(nutzer)
    uhr.t = 100                                          # Cooldowns abklingen lassen
    assert s.beginne(3) == sch.ABGELEHNT_TAGESDECKEL
    heute["d"] = date(2026, 7, 27)                       # UTC-Mitternacht
    assert s.beginne(3) is None


# --- D3: der Tagesdeckel ueberlebt einen Neustart (Review 19.09.2026) ------------------
#
# Der Zaehler war prozesslokal, und der Bot laeuft mit `restart: unless-stopped`. Jeder
# Absturz - und jeder Deploy - schenkte der Runde ein frisches Tagesbudget. Ein
# Kostendeckel, den ein Neustart aufhebt, deckelt nichts.

class Speicher:
    """Stellt die Protokoll-Tabelle nach: {tag: anzahl}. `kaputt` liefert None, also
    'ich weiss es nicht' - ausdruecklich etwas anderes als 0."""

    def __init__(self, stand=None, kaputt=False, schreiben_geht=True):
        self.stand = dict(stand or {})
        self.kaputt = kaputt
        self.schreiben_geht = schreiben_geht
        self.schreibversuche = 0

    def lade(self, tag: str):
        return None if self.kaputt else self.stand.get(tag, 0)

    def speichere(self, tag: str, anzahl: int) -> bool:
        self.schreibversuche += 1
        if not self.schreiben_geht:
            return False
        self.stand[tag] = anzahl
        return True


def _mit_speicher(speicher, **kwargs):
    vorgaben = dict(guild_id=42, tagesdeckel=2, cooldown_s=0.0, uhr=Uhr(),
                    utc_datum=lambda: date(2026, 7, 26),
                    lade_verbrauch=speicher.lade, speichere_verbrauch=speicher.speichere)
    vorgaben.update(kwargs)
    return Schranken(**vorgaben)


def test_tagesdeckel_ueberlebt_den_neustart():
    """DER Kernfall: Zwei Anfragen, dann stirbt der Prozess. Der neue Bot muss den
    Deckel als erreicht vorfinden - vorher fing er bei null wieder an."""
    speicher = Speicher()
    alt = _mit_speicher(speicher)
    assert alt.beginne(1) is None
    alt.beende(1)
    assert alt.beginne(1) is None
    alt.beende(1)
    assert alt.beginne(1) == sch.ABGELEHNT_TAGESDECKEL

    neu = _mit_speicher(speicher)                      # Neustart
    assert neu.beginne(1) == sch.ABGELEHNT_TAGESDECKEL, \
        "Neustart hat das Tagesbudget zurueckgesetzt"


def test_zaehler_wird_vor_dem_modellaufruf_festgeschrieben():
    """fail-closed (D3): Stuerzt der Bot waehrend der Antwort ab, ist der Aufruf
    trotzdem bezahlt. Gezaehlt wird deshalb beim Reservieren, nicht beim Beenden."""
    speicher = Speicher()
    s = _mit_speicher(speicher)
    s.beginne(1)                                        # kein beende() - Absturz
    assert speicher.stand["2026-07-26"] == 1
    assert _mit_speicher(speicher).beginne(2) is None   # Neustart: 1 von 2 verbraucht
    assert speicher.stand["2026-07-26"] == 2


def test_unbekannter_stand_gilt_als_erreicht_nicht_als_null():
    """Die unbequeme Richtung: Ein kaputtes Protokoll darf nicht der Weg sein, den
    Deckel zu umgehen. 'Ich weiss es nicht' ist etwas anderes als 'heute war nichts'."""
    s = _mit_speicher(Speicher(kaputt=True))
    assert s.beginne(1) == sch.ABGELEHNT_TAGESDECKEL


def test_schreibfehler_sperrt_die_runde_nicht_aus():
    """Gegenrichtung: Der laufende Prozess weiss selbst, was er verbraucht hat. Ein
    fehlgeschlagener Schreibvorgang kostet den persistenten Stand, nicht die Antwort -
    dieselbe Leitplanke wie beim Abfrage-Protokoll."""
    speicher = Speicher(schreiben_geht=False)
    s = _mit_speicher(speicher)
    assert s.beginne(1) is None
    s.beende(1)
    assert s.beginne(1) is None
    s.beende(1)
    assert s.beginne(1) == sch.ABGELEHNT_TAGESDECKEL   # in-memory zaehlt weiter
    assert speicher.schreibversuche == 2


def test_tageswechsel_fragt_den_speicher_erneut():
    """Beim Rollover nicht blind auf 0: Laeuft waehrend eines Deploys kurz ein zweiter
    Prozess, hat der vielleicht schon gezaehlt."""
    speicher = Speicher({"2026-07-27": 2})
    tag = [date(2026, 7, 26)]
    s = _mit_speicher(speicher, utc_datum=lambda: tag[0])
    assert s.beginne(1) is None
    s.beende(1)
    tag[0] = date(2026, 7, 27)
    assert s.beginne(1) == sch.ABGELEHNT_TAGESDECKEL


def test_ohne_speicher_bleibt_es_beim_prozesslokalen_zaehlen():
    """Ohne Persistenz-Funktionen (Tests, Altbestand) verhaelt sich der Deckel wie
    vor dem 19.09.2026 - ein fehlender Speicher ist etwas anderes als ein kaputter."""
    s, _ = _schranken(cooldown_s=0.0)
    assert s.beginne(1) is None
    s.beende(1)
    assert s.beginne(1) is None
    s.beende(1)
    assert s.beginne(1) == sch.ABGELEHNT_TAGESDECKEL
