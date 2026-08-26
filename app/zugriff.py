"""Zugriffsschutz fuer den oeffentlich erreichbaren MCP-Endpoint (NF3/NF4, Roadmap M3).

Zwei Schichten, beide OHNE Nutzer-Management (Runde <5 Personen; Claude Custom Connectors
koennen weder eigene Header noch Browser-Logins liefern - nur URL eintragen oder OAuth):
 1. GEHEIMPFAD - die URL selbst ist der Schluessel. WER ihn haelt, entscheidet der
    ZUGANGSMODUS (FOLIANT_ZUGANG, s. u. `zugangsmodus`):
      * `geheimpfad`: Foliant selbst. app/server.py haengt den Endpoint unter
        /<FOLIANT_PFAD_TOKEN>/mcp. Rotation = Token in .env aendern, neu deployen, neue
        URL an die Runde schicken.
      * `router`: der vorgelagerte, vertrauenswuerdige mcp-router. Der prueft SEIN Token,
        entfernt es und reicht /mcp weiter - ein zweiter Geheimpfad im Dienst wuerde
        dieselbe Anfrage dann mit 404 beantworten. Foliant serviert hier das nackte /mcp
        und hat KEIN eigenes Token mehr. Der Endpoint ist in diesem Modus nur so gut
        erreichbar wie das Netz `mcp-net`: kein Host-Port, kein Weg von aussen daran vorbei.
 2. IP-ALLOWLIST (dieses Modul): nur Anfragen aus Anthropics veroeffentlichten
    Egress-Ranges erreichen den MCP-Pfad. Eine geleakte URL ist damit nur noch UEBER
    Claude nutzbar - nie direkt per curl/Scanner/Browser. Sie gilt in BEIDEN Modi: die
    Original-IP liefert die Cloudflare-Edge als CF-Connecting-IP, und dieser Header
    ueberlebt die Kette Cloudflare -> mcp-router -> Dienst unveraendert (geprueft
    26.08.2026). Im Router-Modus ist sie die einzige verbleibende Pruefung IM Dienst -
    darum verweigert app/server.py dort den Produktionsstart, wenn sie abgeschaltet ist.

BEWUSST im Server statt als Cloudflare-Dashboard-Regel: versioniert, getestet und ohne
Dashboard-Zugriff deploybar. Die gleichwertige Edge-Regel (blockt schon an der Cloudflare-
Kante) steht als optionales Upgrade in CONCEPT.md §9.

/health bleibt IMMER offen: verraet nur {"status","name"} (keine Inhalte) und traegt
externes Uptime-Monitoring. Ohne CF-Header (lokale Tests, compose-Healthcheck, LAN)
gilt: private/Loopback-Absender duerfen, oeffentliche nicht.

Schalter (Umgebung):
  FOLIANT_ZUGANG        = "geheimpfad" (Standard) oder "router"
  FOLIANT_IP_FILTER     = "aus" deaktiviert den Filter (Debug; Standard: an)
  FOLIANT_ERLAUBTE_IPS  = zusaetzliche CIDRs, kommagetrennt (z. B. Heim-IP fuer
                          Direkt-Tests oder einen externen Uptime-Monitor)
"""
from __future__ import annotations

import ipaddress
import os

from starlette.responses import JSONResponse

# Anthropic-Egress (= Absender der MCP-Connector-Aufrufe aus Anthropics Cloud).
# Quelle: https://platform.claude.com/docs/en/api/ip-addresses (gelesen 11.07.2026;
# "These addresses will not change without notice"). Der IPv6-Block ist Anthropics
# veroeffentlichter Adressraum - mit aufgenommen, damit ein kuenftiger IPv6-Egress
# nicht ploetzlich blockt. Bei Verbindungsproblemen zuerst hier gegen die aktuelle
# Doku-Seite pruefen.
ANTHROPIC_RANGES = ("160.79.104.0/21", "2607:6bc0::/48")

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


def ip_filter_aktiv() -> bool:
    """Ob die IP-Allowlist greift. EINE Lesestelle, weil app/server.py dieselbe Frage
    stellt (Produktionspruefung im Router-Modus) und zwei Kopien auseinanderlaufen."""
    return (os.environ.get("FOLIANT_IP_FILTER", "an") or "").strip().lower() != "aus"


def _parse_netze(cidrs) -> list:
    netze = []
    for c in cidrs:
        c = str(c).strip()
        if c:
            netze.append(ipaddress.ip_network(c, strict=False))
    return netze


def _extra_netze_aus_env() -> list:
    return _parse_netze((os.environ.get("FOLIANT_ERLAUBTE_IPS") or "").split(","))


class ZugriffsFilter:
    """Reiner ASGI-Wrapper (KEIN BaseHTTPMiddleware - das puffert und wuerde die
    gestreamten MCP-Antworten brechen). Nicht-HTTP-Scopes (lifespan!) laufen durch."""

    def __init__(self, app, aktiv: bool | None = None, extra_ranges: list | None = None):
        self.app = app
        self.aktiv = ip_filter_aktiv() if aktiv is None else aktiv
        self.netze = _parse_netze(ANTHROPIC_RANGES) + (
            _extra_netze_aus_env() if extra_ranges is None else _parse_netze(extra_ranges))

    @staticmethod
    def _redigiere_pfad(pfad: str) -> str:
        """SYN-P1-004: Der Pfad IST das Secret (Geheimpfad-Token als erstes Segment) -
        Blockier-Logzeilen kuerzen es wie der Startup-Print auf 4 Zeichen."""
        teile = (pfad or "/").split("/")
        if len(teile) > 1 and len(teile[1]) > 8:
            teile[1] = teile[1][:4] + "…"
        return "/".join(teile)

    def _erlaubt(self, ip_text: str) -> bool:
        try:
            ip = ipaddress.ip_address(ip_text.strip())
        except ValueError:
            return False
        return any(ip in netz for netz in self.netze)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not self.aktiv or scope.get("path") == "/health":
            await self.app(scope, receive, send)
            return

        cf_ip = next((wert.decode("latin-1") for name, wert in scope.get("headers", [])
                      if name == b"cf-connecting-ip"), None)
        if cf_ip is not None:
            # Edge-Anfrage: die Original-IP MUSS in den erlaubten Ranges liegen.
            if self._erlaubt(cf_ip):
                await self.app(scope, receive, send)
                return
            print(f"zugriff: blockiert {cf_ip} -> {self._redigiere_pfad(scope.get('path'))}")
            await JSONResponse({"fehler": "kein Zugriff"}, status_code=403)(scope, receive, send)
            return

        # Ohne CF-Header: lokale/interne Aufrufe (curl im Container, compose-Healthcheck,
        # LAN-Tests, Test-Harness ohne echte Peer-IP) duerfen; oeffentliche Absender nicht.
        peer = (scope.get("client") or ("", 0))[0]
        try:
            ip = ipaddress.ip_address(peer)
            privat = ip.is_loopback or ip.is_private
        except ValueError:
            # Ein unparsbarer Absender gilt als PRIVAT und wird durchgelassen (fail-open).
            # Das ist nur zulaessig, WEIL der Dienst UEBERHAUPT KEINEN Host-Port mehr
            # veroeffentlicht (docker-compose.yml, seit 26.08.2026) und ausschliesslich im
            # Netz `mcp-net` haengt: von aussen kommt allein die Kette Cloudflare ->
            # web-/mcp-tunnel -> mcp-router herein, und die setzt CF-Connecting-IP, nimmt
            # also den Zweig darueber. Wer hier landet, sitzt schon im Container, ist ein
            # Nachbar auf mcp-net (der Router selbst, `make smoke-pi`) oder das
            # Test-Harness ('testclient').
            #
            # Faellt diese Annahme (Host-Port wieder veroeffentlicht, Reverse-Proxy ohne
            # CF-Header davor), wird diese Zeile zum offenen Zugang - und
            # tests/test_zugriff.py bleibt dabei GRUEN, weil er genau dieses Verhalten
            # festhaelt statt es zu hinterfragen. Die fehlende Portbindung ist die
            # Sicherung, nicht der Test. Im Router-Modus wiegt das schwerer als frueher:
            # dort gibt es kein Token mehr, das einen Direktaufruf zusaetzlich abfinge.
            privat = True
        if privat:
            await self.app(scope, receive, send)
            return
        print(f"zugriff: blockiert direkten Absender {peer} -> "
              f"{self._redigiere_pfad(scope.get('path'))}")
        await JSONResponse({"fehler": "kein Zugriff"}, status_code=403)(scope, receive, send)
