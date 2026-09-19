"""Zugangs- und Kostenschranken des Bots - reine Logik, ohne discord.py.

Die Guild-Sperre IST die Zugangskontrolle (SPEC §12: Vollbestand inkl. DDB nur fuer
die private Runde): der Bot laeuft ohne HTTP-Flaeche, die Tools in-process - was ihn
begrenzt, steht hier.

Cooldowns und laufende Anfragen bleiben in-memory - sie gelten fuer Sekunden, ein
Neustart dauert laenger. Der TAGESDECKEL dagegen ist seit dem 19.09.2026 persistent
(D3): Er zaehlte prozesslokal, und der Bot laeuft mit `restart: unless-stopped` - jeder
Absturz und jeder Deploy schenkte der Runde ein frisches Tagesbudget. Ein Kostendeckel,
den ein Neustart aufhebt, deckelt nichts."""
from __future__ import annotations

import time
from datetime import datetime, timezone

ABGELEHNT_LAEUFT = ("🚫 Deine letzte Frage laeuft noch - bitte warten, bis die "
                    "Antwort da ist.")
ABGELEHNT_COOLDOWN = "🚫 Kurz durchatmen - die naechste Frage geht gleich wieder."
ABGELEHNT_TAGESDECKEL = ("🚫 Das Tageslimit der Runde ist erreicht - morgen geht es "
                         "weiter. (Kostendeckel)")


class Schranken:
    def __init__(self, guild_id: int, kanal_ids: frozenset[int] = frozenset(),
                 tagesdeckel: int = 100, cooldown_s: float = 10.0,
                 uhr=time.monotonic, utc_datum=None,
                 lade_verbrauch=None, speichere_verbrauch=None):
        self._guild_id = guild_id
        self._kanal_ids = kanal_ids          # leer = alle Kanaele der Guild
        self._tagesdeckel = tagesdeckel
        self._cooldown_s = cooldown_s
        self._uhr = uhr                      # injizierbar fuer Tests
        self._utc_datum = utc_datum or (lambda: datetime.now(timezone.utc).date())
        # Persistenz als zwei Funktionen statt eines Imports: Diese Datei bleibt damit
        # frei von Protokoll- und Datenbankwissen (sie ist reine Logik), und die Tests
        # koennen den Speicher ohne Datei nachstellen. Beide duerfen None sein - dann
        # verhaelt sich der Deckel wie vor dem 19.09.2026.
        self._lade_verbrauch = lade_verbrauch
        self._speichere_verbrauch = speichere_verbrauch
        self._laufend: set[int] = set()
        self._zuletzt_fertig: dict[int, float] = {}
        self._tag = self._utc_datum()
        self._tageszaehler = self._hole_stand(self._tag)

    def _hole_stand(self, tag) -> int:
        """Den Tagesstand aus dem Speicher holen - beim Start und bei jedem Tageswechsel.

        Ein UNBEKANNTER Stand (None) zaehlt als DECKEL ERREICHT, nicht als null. Das ist
        die unbequeme, aber richtige Richtung: Wer nicht weiss, wie viel heute schon
        verbraucht wurde, darf nicht so tun, als waere es nichts - sonst waere ein
        beschaedigtes Protokoll genau der Weg, den Deckel zu umgehen. Ein fehlender
        Speicher (beide Funktionen None) ist etwas anderes als ein kaputter: Dort ist gar
        keine Persistenz gewollt, und es bleibt beim prozesslokalen Zaehlen."""
        if self._lade_verbrauch is None:
            return 0
        stand = self._lade_verbrauch(tag.isoformat())
        return self._tagesdeckel if stand is None else int(stand)

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
        # VOR dem Modellaufruf festschreiben (D3 fail-closed): Stuerzt der Bot waehrend
        # der Antwort ab, ist der Aufruf trotzdem bezahlt - und muss gezaehlt bleiben.
        # Ein Schreibfehler laesst die Anfrage durch: Der Prozess weiss selbst, was er
        # heute verbraucht hat, und ein kaputtes Protokoll soll die Runde nicht
        # aussperren. Verloren geht der Stand nur, wenn Schreibfehler UND Neustart
        # zusammenkommen.
        if self._speichere_verbrauch is not None:
            self._speichere_verbrauch(self._tag.isoformat(), self._tageszaehler)
        return None

    def beende(self, nutzer_id: int) -> None:
        self._laufend.discard(nutzer_id)
        self._zuletzt_fertig[nutzer_id] = self._uhr()

    def _rolle_tag(self) -> None:
        heute = self._utc_datum()
        if heute != self._tag:
            self._tag = heute
            # Auch am neuen Tag den Speicher fragen: Laeuft ein zweiter Prozess (Deploy
            # mit Ueberlappung), hat der vielleicht schon gezaehlt.
            self._tageszaehler = self._hole_stand(heute)
