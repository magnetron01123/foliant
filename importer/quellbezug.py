"""Quellbezug: eine FEHLENDE Quelldatei aus ihrer `quell_url` holen (O2 - Inhalte aktuell
halten, ohne Handarbeit an drei Browser-Tabs).

Wofuer das gebaut wurde: Die drei Errata-PDFs (PHB 2024, DMG 2024, MM 2025) liegen als
fertige `[[quelle]]`-Bloecke in der Config, inklusive `quell_url` - es fehlten nur die
Dateien. Der Revisions-Layer stand damit monatelang mit NULL Eintraegen da, weil zwischen
"gebaut" und "nutzbar" drei manuelle Downloads lagen. Diese Luecke schliesst der Schritt:
`admin import --quelle errata-phb-2024-en` holt die Datei selbst, wenn sie fehlt.

Netz ist hier erlaubt und nichts Neues: Der Import IST die Netz-Ebene (CONCEPT.md par. 1),
`glossar` und `open5e` rufen dort seit jeher APIs. Die Laufzeit bleibt offline (Q7).

DIE TRAGENDE REGEL: Eine VORHANDENE Datei wird NIE angefasst. Nicht ueberschrieben, nicht
verglichen, nicht "aktualisiert". Unter `quellen/` liegen kuratierte und reparierte PDFs
(die Browser-Druck-Ausdrucke, CONCEPT.md par. 4) - ein Bezug, der die Originaldatei
ersetzt, macht stundenlange Handarbeit lautlos zunichte, und zwar genau dann, wenn jemand
routiniert einen Re-Import fahren will. Wer eine neue Auflage will, loescht die Datei
bewusst oder legt sie unter neuem Namen mit eigenem `kuerzel` ab.

Was eine Antwort passieren muss, um als Quelldatei zu gelten:
- HTTPS. Ueber http kaeme der Inhalt ungeprueft ueber die Leitung.
- Groessen-Deckel. Ohne ihn wuerde eine falsch konfigurierte URL den Datentraeger fuellen.
- MAGISCHE BYTES, nicht der Content-Type. Ein Portal, das eine Anmeldeseite oder eine
  Cloudflare-Fehlerseite mit HTTP 200 ausliefert, ist der Normalfall, nicht die Ausnahme -
  und ein HTML-Dokument namens `PHB-2024_v1.pdf` faellt sonst erst Minuten spaeter im
  PDF-Parser auf, mit einer Fehlermeldung, die auf die falsche Ursache zeigt.
- Der Hash-Pin, falls die Config einen fuehrt (V10). Stimmt er nicht, ist an derselben URL
  ein ANDERER Inhalt erschienen - dann ist `versions_stand = "Errata Version 1.0"` eine
  falsche Aussage ueber den Bestand, und der Import bricht ab, statt sie zu schreiben.
"""
from __future__ import annotations

import hashlib
import os
import pathlib

# 100 MB: die Errata-PDFs liegen bei ein bis drei, das groesste bekannte Regelwerk-PDF
# deutlich darunter. Der Deckel ist keine Feinjustage, sondern eine Notbremse.
MAX_BYTES = 100 * 1024 * 1024

# Erste Bytes je Endung. Bewusst knapp: nur, was ein Format zweifelsfrei ausweist.
_MAGISCHE_BYTES = {".pdf": b"%PDF-"}


class BezugFehler(RuntimeError):
    """Der Bezug ist gescheitert - der Aufrufer bricht den Import ab, statt eine
    Rumpf-Quelle zu schreiben (Q3: kein Inhalt ohne belegte Herkunft)."""


def _lade_https(url: str, zeitlimit: float) -> bytes:
    """Der Standard-Lader. Streamt mit Deckel, statt die Antwort blind in den RAM zu
    ziehen - der Pi hat 8 GB und traegt daneben MCP, Website und Bot."""
    import httpx  # Import hier: nur der Importer braucht Netz (Q7: Laufzeit offline)

    kopf = {"User-Agent": "Foliant (privat, einmaliger Import)"}
    stuecke, gesamt = [], 0
    with httpx.Client(timeout=zeitlimit, headers=kopf, follow_redirects=True) as client:
        with client.stream("GET", url) as antwort:
            antwort.raise_for_status()
            for stueck in antwort.iter_bytes():
                gesamt += len(stueck)
                if gesamt > MAX_BYTES:
                    raise BezugFehler(
                        f"Antwort ueberschreitet {MAX_BYTES // 1024 // 1024} MB - "
                        f"zeigt die URL wirklich auf die Quelldatei?")
                stuecke.append(stueck)
    return b"".join(stuecke)


def hole_wenn_fehlt(ziel: pathlib.Path, url: str | None, *,
                    erwarteter_hash: str | None = None,
                    zeitlimit: float = 60.0, lader=None) -> str | None:
    """Holt `ziel` aus `url`, WENN die Datei fehlt und eine URL da ist.

    Liefert eine Meldung fuer die Import-Ausgabe - oder None, wenn nichts zu tun war
    (Datei liegt schon da, oder die Quelle fuehrt keine URL). None ist bewusst kein
    Fehler: Quellen ohne `quell_url` sind der Normalfall (gekaufte PDFs, Scans), und der
    Aufrufer laeuft danach in seine gewohnte "dateipfad fehlt"-Meldung.

    Wirft BezugFehler, wenn der Bezug versucht wurde und schiefging.
    """
    if ziel.exists():
        return None                       # tragende Regel: nie anfassen (Modul-Docstring)
    if not url:
        return None
    if not url.lower().startswith("https://"):
        raise BezugFehler(f"quell_url ist nicht https, Bezug abgelehnt: {url}")

    roh = (lader or _lade_https)(url, zeitlimit)
    if not roh:
        raise BezugFehler(f"leere Antwort von {url}")

    magie = _MAGISCHE_BYTES.get(ziel.suffix.lower())
    if magie and not roh.startswith(magie):
        # Der haeufigste Fall hinter diesem Abbruch ist eine HTML-Seite mit Status 200.
        raise BezugFehler(
            f"Antwort von {url} beginnt nicht mit {magie!r} - das ist kein "
            f"{ziel.suffix}-Dokument (Anmelde- oder Fehlerseite?). Nichts geschrieben.")

    tatsaechlich = hashlib.sha256(roh).hexdigest()
    if erwarteter_hash and tatsaechlich != erwarteter_hash:
        raise BezugFehler(
            f"quell_hash passt nicht: config sagt {erwarteter_hash[:16]}…, geladen wurde "
            f"{tatsaechlich[:16]}…\nAn derselben URL liegt ein anderer Inhalt. Pruefe, ob "
            f"eine neue Auflage erschienen ist - dann gehoeren `versions_stand` UND "
            f"`quell_hash` in der config nachgezogen, bewusst und im Diff sichtbar.")

    # Atomar schreiben wie der Rest des Projekts (Kandidat -> os.replace): ein Abbruch
    # mitten im Schreiben darf keine halbe PDF hinterlassen, die beim naechsten Lauf als
    # "Datei ist ja da" durchgeht und dann im Parser scheitert.
    ziel.parent.mkdir(parents=True, exist_ok=True)
    kandidat = ziel.with_suffix(ziel.suffix + ".teil")
    kandidat.write_bytes(roh)
    os.replace(kandidat, ziel)

    meldung = (f"Quelldatei bezogen: {ziel.name} ({len(roh) / 1024 / 1024:.1f} MB) "
               f"von {url}\n  sha256: {tatsaechlich}")
    if not erwarteter_hash:
        # Der Pin ist optional - aber ohne diesen Hinweis erfaehrt niemand, dass es ihn
        # gibt, und die Integritaetszusage aus V10 bliebe ungenutzt.
        meldung += (f"\n  Tipp: als `quell_hash = \"{tatsaechlich}\"` in den "
                    f"[[quelle]]-Block, dann faellt ein Inhaltswechsel an der URL auf.")
    return meldung
