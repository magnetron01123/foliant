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
    s, _ = _schranken()
    assert s.ablehnungsgrund(1) is None
    s.beginne(1)
    assert s.ablehnungsgrund(1) == sch.ABGELEHNT_LAEUFT
    assert s.ablehnungsgrund(2) is None                  # andere Nutzer unberuehrt


def test_cooldown_nach_abschluss():
    s, uhr = _schranken()
    s.beginne(1)
    uhr.t = 5
    s.beende(1)
    assert s.ablehnungsgrund(1) == sch.ABGELEHNT_COOLDOWN
    uhr.t = 15.1                                         # 10 s nach beende()
    assert s.ablehnungsgrund(1) is None


def test_tagesdeckel_und_utc_rollover():
    heute = {"d": date(2026, 7, 26)}
    s, uhr = _schranken(utc_datum=lambda: heute["d"])
    for nutzer in (1, 2):                                # Deckel 2 ausschoepfen
        s.beginne(nutzer)
        s.beende(nutzer)
    uhr.t = 100                                          # Cooldowns abklingen lassen
    assert s.ablehnungsgrund(3) == sch.ABGELEHNT_TAGESDECKEL
    heute["d"] = date(2026, 7, 27)                       # UTC-Mitternacht
    assert s.ablehnungsgrund(3) is None
