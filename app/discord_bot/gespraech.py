"""Thread-Verlaeufe in-memory (Eigentuemer-Entscheidung 26.07.2026): ein Pi-Neustart
vergisst laufende Gespraeche - der Bot sagt das im Thread ehrlich, statt still ohne
Kontext weiterzureden. Persistenz waere neuer State ohne Not; die Discord-Historie
bleibt als spaetere Rebuild-Quelle vorgemerkt (BACKLOG §4).

Gespeichert werden NUR finale Texte (Frage/Antwort-Paare), keine Tool-Runden: jede
Folgefrage faehrt ihre eigene Tool-Schleife - identisch zum Eval-Verhalten pro Frage,
und der Verlauf bleibt klein."""
from __future__ import annotations

import time


class GespraechsSpeicher:
    """thread_id -> Verlauf, mit drei Deckeln gegen unbegrenztes Wachstum:
    TTL (Discord archiviert Threads ohnehin nach 24 h Default), LRU-Anzahl und ein
    Zeichen-Budget je Gespraech (aelteste Paare fliegen zuerst - das Modell braucht
    den juengsten Kontext, nicht den Anfang)."""

    def __init__(self, max_gespraeche: int = 200, ttl_s: float = 24 * 3600,
                 max_nachrichten: int = 12, max_zeichen: int = 24_000,
                 uhr=time.monotonic):
        self._max_gespraeche = max_gespraeche
        self._ttl_s = ttl_s
        self._max_nachrichten = max_nachrichten
        self._max_zeichen = max_zeichen
        self._uhr = uhr                     # injizierbar fuer Tests
        self._gespraeche: dict[int, dict] = {}

    def kennt(self, thread_id: int) -> bool:
        self._raeume_auf()
        return thread_id in self._gespraeche

    def verlauf(self, thread_id: int) -> list[dict]:
        """Kopie der messages-Liste ([{'role','content'}, ...]); leer bei unbekannt."""
        self._raeume_auf()
        eintrag = self._gespraeche.get(thread_id)
        if eintrag is None:
            return []
        eintrag["zuletzt"] = self._uhr()
        return list(eintrag["verlauf"])

    def ergaenze(self, thread_id: int, frage: str, antwort: str) -> None:
        self._raeume_auf()
        eintrag = self._gespraeche.setdefault(
            thread_id, {"zuletzt": self._uhr(), "verlauf": []})
        eintrag["zuletzt"] = self._uhr()
        eintrag["verlauf"] += [{"role": "user", "content": frage},
                               {"role": "assistant", "content": antwort}]
        self._kappe(eintrag)
        self._verdraenge()

    def _kappe(self, eintrag: dict) -> None:
        """Aelteste PAARE entfernen, bis Anzahl- und Zeichen-Budget passen. Immer
        paarweise: ein verwaister assistant-Turn am Anfang waere ein kaputter Verlauf."""
        verlauf = eintrag["verlauf"]
        while (len(verlauf) > self._max_nachrichten
               or sum(len(n["content"]) for n in verlauf) > self._max_zeichen):
            if len(verlauf) <= 2:           # das juengste Paar bleibt immer
                break
            del verlauf[:2]

    def _raeume_auf(self) -> None:
        jetzt = self._uhr()
        tot = [tid for tid, e in self._gespraeche.items()
               if jetzt - e["zuletzt"] > self._ttl_s]
        for tid in tot:
            del self._gespraeche[tid]

    def _verdraenge(self) -> None:
        while len(self._gespraeche) > self._max_gespraeche:
            aeltester = min(self._gespraeche, key=lambda t: self._gespraeche[t]["zuletzt"])
            del self._gespraeche[aeltester]
