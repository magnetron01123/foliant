"""Zugriffsschutz fuer den oeffentlichen Tunnel-Endpoint (NF3/NF4, Roadmap M3).

Zwei Schichten, beide OHNE Nutzer-Management (Runde <5 Personen; Claude Custom Connectors
koennen weder eigene Header noch Browser-Logins liefern - nur URL eintragen oder OAuth):
 1. GEHEIMPFAD (app/server.py): der MCP-Endpoint liegt unter /<FOLIANT_PFAD_TOKEN>/mcp -
    die URL selbst ist der Schluessel. Rotation = Token in .env aendern, neu deployen,
    neue URL an die Runde schicken.
 2. IP-ALLOWLIST (dieses Modul): nur Anfragen aus Anthropics veroeffentlichten
    Egress-Ranges erreichen den MCP-Pfad. Eine geleakte URL ist damit nur noch UEBER
    Claude nutzbar - nie direkt per curl/Scanner/Browser. Die Original-IP liefert die
    Cloudflare-Edge als CF-Connecting-IP; der Client kann sie nicht faelschen, weil der
    einzige Weg zum Server der ausgehende cloudflared-Tunnel ist (Port 8000 ist an
    127.0.0.1 gebunden).

BEWUSST im Server statt als Cloudflare-Dashboard-Regel: versioniert, getestet und ohne
Dashboard-Zugriff deploybar. Die gleichwertige Edge-Regel (blockt schon an der Cloudflare-
Kante) steht als optionales Upgrade in docs/DEPLOY-raspberry-pi.md.

/health bleibt IMMER offen: verraet nur {"status","name"} (keine Inhalte) und traegt
externes Uptime-Monitoring. Ohne CF-Header (lokale Tests, compose-Healthcheck, LAN)
gilt: private/Loopback-Absender duerfen, oeffentliche nicht.

Schalter (Umgebung):
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
        self.aktiv = (os.environ.get("FOLIANT_IP_FILTER", "an").strip().lower() != "aus") \
            if aktiv is None else aktiv
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
            privat = True                     # Test-Harness ('testclient') o. ae.
        if privat:
            await self.app(scope, receive, send)
            return
        print(f"zugriff: blockiert direkten Absender {peer} -> "
              f"{self._redigiere_pfad(scope.get('path'))}")
        await JSONResponse({"fehler": "kein Zugriff"}, status_code=403)(scope, receive, send)
