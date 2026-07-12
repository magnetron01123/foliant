"""Gekapselter DDB-Zugriff - das EINZIGE Modul im Projekt, das DDB-URLs kennt
(Vorschlag §5: Adaptermodul; Endpunkte sind undokumentiert und koennen brechen).

Belegte Ablaufkette (Referenz: MrPrimate Adventure Muncher, munch/data/ddb.js -
Strukturdetails am 11.07.2026 gegen den Referenzcode verifiziert, nachdem der erste
echte Dry-run die Annahmen korrigierte):
  1. POST user-data                 - Token pruefen ({status:"success", data:{...}})
  2. POST available-user-content    - Lizenzen VERSCHACHTELT: Licenses[] ->
                                      {EntityTypeID, Entities: [{id, isOwned, ...}]}
  3. Filter: EntityTypeID == BUCH_ENTITY_TYPE und Entities[].isOwned (KEIN Bypass)
  4. POST get-book-url/{id}         - signierte Download-URL (data als String/objekt.url)
  5. POST book-codes                - FORM-encoded (token + sources-JSON-String);
                                      Antwort: [{sourceID, data: <Base64-Schluessel>}]

SECRETS: Cobalt, Buchschluessel und signierte URLs gelten als geheim - sie erscheinen
nie in Logs, Exceptions oder Rueckgaben ausser als redigierte Form (_redigiere_url);
Struktur-Diagnosen nennen nur KEY-NAMEN und Typen, nie Werte.
RETRY: begrenzt mit Backoff nur fuer 429/5xx; 401/403 NIE wiederholen (O5: Token
erneuern ist Nutzersache). Transport ist injizierbar (Tests: Mock, kein Netz)."""
from __future__ import annotations

import base64
import json as _json
import time
from urllib.parse import urlsplit

_MOBILE_API = "https://www.dndbeyond.com/mobile/api/v6"
BUCH_ENTITY_TYPE = 496802664          # Sourcebook-Lizenzen (Referenz: Adventure Muncher)
_MAX_VERSUCHE = 3
_BACKOFF_S = 2.0


class DdbFehler(RuntimeError):
    """Fehler an der DDB-Grenze - Meldungen sind IMMER secret-frei."""


def _redigiere_url(url: str) -> str:
    """Signierte URLs nur als Schema+Host+redigiertem Pfad ausgeben (Vorschlag §9)."""
    teile = urlsplit(str(url))
    return f"{teile.scheme}://{teile.netloc}/…(redigiert)"


class DdbClient:
    """transport: httpx.Client-kompatibel (post(url, json=..., headers=...) -> Response).
    cobalt wird NUR im Speicher gehalten und ausschliesslich als Cookie-Header gesendet."""

    def __init__(self, transport, cobalt: str):
        if not cobalt or not cobalt.strip():
            raise DdbFehler("Leerer Cobalt-Wert - Abbruch vor jedem Netzzugriff.")
        self._transport = transport
        self._cobalt = cobalt.strip()

    # ------------------------------ HTTP-Kern ------------------------------

    def _post(self, url: str, extra_form: dict | None = None) -> dict:
        """Die DDB-Mobile-API erwartet den Cobalt-Wert bei ALLEN Endpunkten als
        `token`-Feld im URL-codierten Formular-Body (Referenz Adventure Muncher,
        verifiziert 11.07.2026) - NICHT als Cookie-Header und ohne separaten
        Bearer-Token-Tausch. Der Token steht damit nur im Body, nie in der URL."""
        form = {"token": self._cobalt, **(extra_form or {})}
        headers = {"Content-Type": "application/x-www-form-urlencoded",
                   "User-Agent": "Foliant (privater Einmal-Import eigener Buecher)"}
        letzte = None
        for versuch in range(1, _MAX_VERSUCHE + 1):
            antwort = self._transport.post(url, data=form, headers=headers)
            status = antwort.status_code
            if status in (401, 403):
                raise DdbFehler(f"DDB-Authentifizierung abgelehnt (HTTP {status}) - "
                                f"Cobalt abgelaufen/ungueltig? Kein automatischer Retry.")
            if status == 429 or 500 <= status < 600:
                letzte = status
                if versuch < _MAX_VERSUCHE:
                    time.sleep(_BACKOFF_S * versuch)
                continue
            if status != 200:
                raise DdbFehler(f"DDB-Antwort HTTP {status} fuer "
                                f"{_redigiere_url(url)} - Abbruch.")
            try:
                daten = antwort.json()
            except Exception as fehler:
                raise DdbFehler(f"DDB lieferte kein gueltiges JSON fuer "
                                f"{_redigiere_url(url)}: {type(fehler).__name__}.") from None
            if not isinstance(daten, dict):
                raise DdbFehler("DDB-JSON hat unerwartete Form (kein Objekt).")
            return daten
        raise DdbFehler(f"DDB nach {_MAX_VERSUCHE} Versuchen nicht erreichbar "
                        f"(zuletzt HTTP {letzte}).")

    @staticmethod
    def _daten(antwort: dict) -> dict | list:
        if antwort.get("status") not in (None, "success") or "data" not in antwort:
            raise DdbFehler(f"DDB-Antwort ohne Erfolgsstatus/data-Feld "
                            f"(status={antwort.get('status')!r}).")
        return antwort["data"]

    # ---------------------------- Fachliche Calls ----------------------------

    def pruefe_token(self) -> str:
        """user-data MUSS eine echte Nutzeridentitaet liefern (Referenz: data.userId/
        userDisplayName). WICHTIG (Fund 11.07.2026): DDB lehnt ungueltige Tokens NICHT
        mit 401 ab, sondern antwortet anonym - und available-user-content liefert dann
        nur die Gratis-Inhalte. Ohne userId gilt der Token deshalb als ungueltig.
        Rueckgabe: Anzeigename (kein Secret) zur Bestaetigung."""
        antwort = self._post(f"{_MOBILE_API}/user-data")
        if not isinstance(antwort, dict) or antwort.get("status") != "success":
            raise DdbFehler("Anmeldepruefung fehlgeschlagen (kein status=success) - der "
                            "Cobalt-Wert ist sehr wahrscheinlich ungueltig, abgelaufen "
                            "oder unvollstaendig (er ist ~180+ Zeichen lang, beginnt mit "
                            "'eyJ...').")
        # user-data legt die Identitaet DIREKT oben ab (kein data-Wrapper); ohne userId
        # ist die Sitzung anonym und gekaufte Inhalte blieben unsichtbar.
        user_id = antwort.get("userId") or (antwort.get("data") or {}).get("userId")
        if not user_id:
            raise DdbFehler("DDB behandelt diese Sitzung als ANONYM (kein userId) - "
                            "gekaufte Inhalte waeren unsichtbar; Abbruch.")
        return str(antwort.get("userDisplayName")
                   or (antwort.get("data") or {}).get("userDisplayName") or user_id)

    @staticmethod
    def _struktur(objekt, tiefe: int = 0) -> str:
        """Secret-freie Diagnose: NUR Key-Namen und Typen, nie Werte - damit ein
        Struktur-Fehlschlag beim echten Dry-run sofort verwertbar ist."""
        if isinstance(objekt, dict):
            teile = [f"{k}:{DdbClient._struktur(v, tiefe + 1)}" for k, v in
                     list(objekt.items())[:12]]
            return "{" + ", ".join(teile) + "}"
        if isinstance(objekt, list):
            inhalt = DdbClient._struktur(objekt[0], tiefe + 1) if objekt else ""
            return f"list[{len(objekt)}]({inhalt})"
        return type(objekt).__name__

    def eigene_buecher(self) -> list[dict]:
        """available-user-content, STRIKT gefiltert auf eigene Sourcebooks. Struktur
        laut Referenz (Adventure Muncher, verifiziert 11.07.2026): Licenses[] ->
        {EntityTypeID, Entities: [{id, isOwned, ...}]} - die Buecher liegen also einen
        Level TIEFER in Entities; nur isOwned==true zaehlt, es gibt keinen Bypass."""
        antwort = self._post(f"{_MOBILE_API}/available-user-content")
        wurzel = antwort.get("data", antwort) if isinstance(antwort, dict) else antwort
        lizenzen = None
        if isinstance(wurzel, dict):
            lizenzen = wurzel.get("Licenses", wurzel.get("licenses"))
        elif isinstance(wurzel, list):
            lizenzen = wurzel
        if not isinstance(lizenzen, list):
            raise DdbFehler(f"available-user-content: unerwartete Struktur - "
                            f"{self._struktur(antwort)}")
        eigene: list[dict] = []
        for block in lizenzen:
            if not isinstance(block, dict):
                continue
            typ = block.get("EntityTypeID", block.get("entityTypeID", 0)) or 0
            if int(typ) != BUCH_ENTITY_TYPE:
                continue
            for buch in block.get("Entities", block.get("entities")) or []:
                if not isinstance(buch, dict):
                    continue
                if not bool(buch.get("isOwned", buch.get("IsOwned", False))):
                    continue
                buch_id = buch.get("id", buch.get("ID", buch.get("entityID")))
                if buch_id is None:
                    continue
                name = buch.get("name", buch.get("Name", buch.get("title")))
                eigene.append({"id": int(buch_id), "name": str(name or buch_id)})
        return eigene

    def lizenz_uebersicht(self) -> dict:
        """Diagnose (secret-frei): welche Lizenz-Bloecke liefert available-user-content,
        mit welchen EntityTypeIDs, wie vielen Eintraegen und welchen owned-IDs? Noetig,
        wenn erwartete Kaeufe nicht in eigene_buecher() auftauchen - IDs und Zaehler
        sind unkritisch, Werte/Titel werden nicht ausgegeben."""
        antwort = self._post(f"{_MOBILE_API}/available-user-content")
        wurzel = antwort.get("data", antwort) if isinstance(antwort, dict) else antwort
        uebersicht: dict = {"top_level": self._struktur(antwort), "bloecke": []}
        lizenzen = (wurzel.get("Licenses", wurzel.get("licenses"))
                    if isinstance(wurzel, dict) else wurzel)
        for block in lizenzen or []:
            if not isinstance(block, dict):
                continue
            entities = block.get("Entities", block.get("entities")) or []
            owned = [e for e in entities if isinstance(e, dict)
                     and bool(e.get("isOwned", e.get("IsOwned", False)))]
            uebersicht["bloecke"].append({
                "entity_type_id": block.get("EntityTypeID", block.get("entityTypeID")),
                "eintraege": len(entities),
                "owned": len(owned),
                "owned_ids": sorted(e.get("id", e.get("ID", 0)) or 0 for e in owned)[:60],
            })
        return uebersicht

    def buch_url(self, buch_id: int) -> str:
        """Signierte Download-URL - GEHEIM, nie loggen; nur zurueckgeben."""
        daten = self._daten(self._post(f"{_MOBILE_API}/get-book-url/{int(buch_id)}"))
        url = daten if isinstance(daten, str) else (daten or {}).get("url")
        if not url or not str(url).startswith("https://"):
            raise DdbFehler("get-book-url: keine https-Download-URL erhalten.")
        return str(url)

    def buch_schluessel(self, buch_id: int) -> str:
        """book-codes fuer GENAU diese Source-ID - GEHEIM, nur im Speicher halten.
        Referenzgetreu (Muncher): FORM-encoded mit token + sources-JSON-String;
        der Schluessel kommt Base64-codiert im data-Feld und wird hier dekodiert."""
        antwort = self._post(
            f"{_MOBILE_API}/book-codes",
            extra_form={"sources": _json.dumps([{"sourceID": int(buch_id),
                                                 "versionID": None}])})
        wurzel = antwort.get("data", antwort) if isinstance(antwort, dict) else antwort
        eintraege = wurzel if isinstance(wurzel, list) \
            else (wurzel or {}).get("bookCodes", [])
        for e in eintraege or []:
            if not isinstance(e, dict):
                continue
            if int(e.get("sourceID", e.get("sourceId", 0) or 0)) == int(buch_id):
                code = e.get("data") or e.get("code")
                if code:
                    try:
                        return base64.b64decode(str(code)).decode("utf-8")
                    except Exception:
                        raise DdbFehler("book-codes: Schluessel nicht Base64-dekodierbar "
                                        "- Formatannahme verletzt.") from None
        raise DdbFehler(f"book-codes: kein Schluessel fuer Source-ID {int(buch_id)} - "
                        f"gehoert das Buch wirklich zum Account? Struktur: "
                        f"{self._struktur(antwort)}")
