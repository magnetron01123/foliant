"""Zugangsmodus fuer den oeffentlich erreichbaren MCP-Endpoint (NF3/NF4, Roadmap M3).

KEIN Nutzer-Management (Runde <5 Personen; Claude Custom Connectors koennen weder eigene
Header noch Browser-Logins liefern - nur URL eintragen oder OAuth). Der Schutz ist ein
GEHEIMPFAD: die URL selbst ist der Schluessel. WER ihn haelt, entscheidet der
ZUGANGSMODUS (FOLIANT_ZUGANG, s. u. `zugangsmodus`):
  * `geheimpfad`: Foliant selbst. app/server.py haengt den Endpoint unter
    /<FOLIANT_PFAD_TOKEN>/mcp. Rotation = Token in .env aendern, neu deployen, neue URL
    an die Runde schicken.
  * `router`: der vorgelagerte, vertrauenswuerdige mcp-router. Der prueft SEIN Token,
    entfernt es und reicht /mcp weiter - ein zweiter Geheimpfad im Dienst wuerde dieselbe
    Anfrage dann mit 404 beantworten. Foliant serviert hier das nackte /mcp und hat KEIN
    eigenes Token mehr. Der Endpoint ist in diesem Modus nur so gut erreichbar wie das
    Netz `mcp-net`: kein Host-Port, kein Weg von aussen daran vorbei.

Bis zum 02.09.2026 stand hier zusaetzlich eine IP-ALLOWLIST auf Anthropics Egress-Bereiche
- ein ASGI-Wrapper `ZugriffsFilter`, der `CF-Connecting-IP` prueft. Sie ist entfallen, weil
dieselbe Pruefung seither als WAF-Regel an der Cloudflare-Kante haengt: einmal gesetzt fuer
ALLE MCP-Dienste des Geraets, und sie greift, bevor eine Anfrage den Pi ueberhaupt
erreicht. Zwei Kopien haetten bei jeder Aenderung an Anthropics Bereichen zweimal
nachgezogen werden muessen.

Der Preis ist real und steht in CONCEPT.md §9: Der gesamte Zugangsschutz liegt jetzt
ausserhalb dieses Repos. Er ist von hier aus nicht testbar, kein Start bemerkt sein Fehlen,
und wer die Regel im Cloudflare-Dashboard loescht, macht den MCP still oeffentlich.
`.claude/ablaeufe/egress-abgleich.md` haelt wenigstens den Abgleich der Bereiche am Leben.

Schalter (Umgebung):
  FOLIANT_ZUGANG = "geheimpfad" (Standard) oder "router"
"""
from __future__ import annotations

import os

# Die beiden Zugangsmodi. Standard ist der STRENGERE: wer nichts setzt, bekommt den
# eigenen Geheimpfad - der Router-Betrieb ist eine bewusste Ansage, kein Rueckfallwert.
MODUS_GEHEIMPFAD = "geheimpfad"
MODUS_ROUTER = "router"


def zugangsmodus() -> str:
    """Liest FOLIANT_ZUGANG. Unbekannter Wert -> Abbruch statt stiller Rueckfall.

    Ein Tippfehler wuerde sonst lautlos den anderen Modus einschalten, und beide sehen
    im Log gleich gesund aus - der eine antwortet nur auf /mcp mit 404, der andere haengt
    den Endpoint hinter ein Token, das niemand kennt."""
    roh = (os.environ.get("FOLIANT_ZUGANG") or "").strip().lower()
    if not roh:
        return MODUS_GEHEIMPFAD
    if roh not in (MODUS_GEHEIMPFAD, MODUS_ROUTER):
        raise RuntimeError(
            f"FOLIANT_ZUGANG={roh!r} ist kein gueltiger Zugangsmodus - erlaubt sind "
            f"{MODUS_GEHEIMPFAD!r} (eigener Geheimpfad) und {MODUS_ROUTER!r} (hinter dem "
            f"geteilten mcp-router). Start abgebrochen statt still den falschen Modus zu "
            f"fahren.")
    return roh
