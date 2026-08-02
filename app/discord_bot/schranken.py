"""Zugangs- und Kostenschranken des Bots - reine Logik, ohne discord.py.

Die Guild-Sperre IST die Zugangskontrolle (SPEC §12: Vollbestand inkl. DDB nur fuer
die private Runde): der Bot laeuft ohne HTTP-Flaeche, die Tools in-process - was ihn
begrenzt, steht hier. Alles in-memory: ein Neustart resettet Zaehler und Cooldowns
(bewusst akzeptiert, der harte Deckel ist das Spend-Limit des API-Workspace)."""
from __future__ import annotations

import time
from datetime import datetime, timezone

ABGELEHNT_ORT = None            # falscher Ort: still ignorieren, keine Antwort
ABGELEHNT_LAEUFT = ("🚫 Deine letzte Frage laeuft noch - bitte warten, bis die "
                    "Antwort da ist.")
ABGELEHNT_COOLDOWN = "🚫 Kurz durchatmen - die naechste Frage geht gleich wieder."
ABGELEHNT_TAGESDECKEL = ("🚫 Das Tageslimit der Runde ist erreicht - morgen geht es "
                         "weiter. (Kostendeckel)")


class Schranken:
    def __init__(self, guild_id: int, kanal_ids: frozenset[int] = frozenset(),
                 tagesdeckel: int = 100, cooldown_s: float = 10.0,
                 uhr=time.monotonic, utc_datum=None):
        self._guild_id = guild_id
        self._kanal_ids = kanal_ids          # leer = alle Kanaele der Guild
        self._tagesdeckel = tagesdeckel
        self._cooldown_s = cooldown_s
        self._uhr = uhr                      # injizierbar fuer Tests
        self._utc_datum = utc_datum or (lambda: datetime.now(timezone.utc).date())
        self._laufend: set[int] = set()
        self._zuletzt_fertig: dict[int, float] = {}
        self._tag = self._utc_datum()
        self._tageszaehler = 0

    def richtiger_ort(self, guild_id: int | None, kanal_id: int | None) -> bool:
        """Fremde Guild oder gesperrter Kanal -> still ignorieren (kein Orakel, welche
        Orte 'fast richtig' waeren). Threads reicht der Bot als Eltern-Kanal herein."""
        if guild_id != self._guild_id:
            return False
        return not self._kanal_ids or kanal_id in self._kanal_ids

    def beginne(self, nutzer_id: int) -> str | None:
        """Pruefen und reservieren in EINEM Schritt: None = darf laufen und gilt ab
        sofort als laufend. Getrennt (erst pruefen, spaeter reservieren) waren beide
        Schritte in bot.py durch awaits getrennt - zwei schnelle Nachrichten desselben
        Nutzers passierten die Pruefung gemeinsam und liefen doch parallel.
        Reihenfolge: laufende Anfrage vor Cooldown vor Deckel - die spezifischste
        Meldung zuerst. Eine Ablehnung reserviert nichts und zaehlt nicht."""
        self._rolle_tag()
        if nutzer_id in self._laufend:
            return ABGELEHNT_LAEUFT
        zuletzt = self._zuletzt_fertig.get(nutzer_id)
        if zuletzt is not None and self._uhr() - zuletzt < self._cooldown_s:
            return ABGELEHNT_COOLDOWN
        if self._tageszaehler >= self._tagesdeckel:
            return ABGELEHNT_TAGESDECKEL
        self._laufend.add(nutzer_id)
        self._tageszaehler += 1
        return None

    def beende(self, nutzer_id: int) -> None:
        self._laufend.discard(nutzer_id)
        self._zuletzt_fertig[nutzer_id] = self._uhr()

    def _rolle_tag(self) -> None:
        heute = self._utc_datum()
        if heute != self._tag:
            self._tag = heute
            self._tageszaehler = 0
