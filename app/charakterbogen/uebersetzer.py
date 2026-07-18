"""Übersetzer (LLM-basiert, klar isoliert): füllt `.de` im neutralen Charaktermodell.

Strategie (KONZEPT §6, AUFTRAG §8):
- FESTE Begriffe/Namen (art="term"): deterministisch über `terminologie.aufloesen` (die
  bestehende Foliant-Glossar-Logik). Exakter Treffer -> §5-Form ohne LLM.
- ZWEI LLM-Stufen: erst die unbelegten Begriffe (Stufe 1, kurz), dann die Fließtexte
  (Stufe 2) - MIT den Begriffen aus Stufe 1 als Vorgabe. So heißt derselbe Name im Feld
  und im Fließtext gleich; unbelegte Begriffe tragen '*' (§5).
- Namen (art="name") werden nie übersetzt.
- Zahlen/Würfel/Modifikatoren sind KEINE UeText -> laufen nie durch das Modell.
- Übersetzungsgedächtnis: gleicher englischer String -> überall dieselbe deutsche Fassung
  (ein Aufruf pro EINDEUTIGEM Text).

Der Provider ist ein schmaler Vertrag; der MVP hat einen Anthropic-Adapter (httpx) und
einen Fake für Tests. Kein API-Key -> `ProviderNichtKonfiguriert` (die Website meldet dann
'Übersetzung momentan nicht verfügbar'); der übrige Server startet trotzdem.
"""
from __future__ import annotations

import dataclasses
import json
import os
import re
import sqlite3
from typing import Protocol

from app.charakterbogen import terminologie
from app.charakterbogen.modelle import Charakter, UeText


class ProviderNichtKonfiguriert(RuntimeError):
    """Kein Übersetzungsprovider verfügbar (z.B. fehlender API-Key)."""


class UebersetzungsFehler(RuntimeError):
    """Der Provider lieferte kein gültiges, vollständiges Ergebnis (auch nach Wiederholung)."""


class Uebersetzungsprovider(Protocol):
    def uebersetze(self, felder: dict[str, str],
                   vorgaben: dict[str, str] | None = None) -> dict[str, str]:
        """{id: englischer Text} -> {id: deutscher Text}, IDENTISCHE Schlüsselmenge.
        `vorgaben` = {englischer Begriff: amtlicher deutscher Name} zur konsistenten Nennung
        derselben Begriffe im Fließtext (z.B. Mage Hand -> Magierhand)."""
        ...


# --- Modell-Durchlauf --------------------------------------------------------

def _alle_uetexte(obj, out: list[UeText]) -> None:
    """Sammelt jedes UeText im Modellbaum (Datenklassen, Listen, Dicts). Zahlen/Strings/
    RohFeld enthalten kein UeText und werden übersprungen."""
    if isinstance(obj, UeText):
        out.append(obj)
    elif dataclasses.is_dataclass(obj):
        for f in dataclasses.fields(obj):
            _alle_uetexte(getattr(obj, f.name), out)
    elif isinstance(obj, dict):
        for v in obj.values():
            _alle_uetexte(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _alle_uetexte(v, out)


def _anwenden(ue: UeText, en: str, de_roh: str) -> str:
    """LLM-Ergebnis in die §5-Endform bringen (Listen kommen hier nie an - sie werden
    deterministisch über `_liste_deterministisch` gebildet)."""
    if ue.art == "term":
        return terminologie.markiere_fallback(en, de_roh)   # "de* (en)"
    return de_roh                                            # freier Text unverändert


def _de_klar(anzeige: str) -> str:
    """§5-Anzeige -> reiner deutscher Begriff: 'Magierhand (Mage Hand)' -> 'Magierhand'."""
    return anzeige.split(" (")[0].rstrip("*").strip()


# --- Orchestrierung ----------------------------------------------------------

def _glossar_vorgaben(con: sqlite3.Connection, texte: list[str],
                      vorgaben: dict[str, str]) -> None:
    """Amtliche Begriffe für die FREITEXTE erzwingen (Befund 16.07.2026: das LLM erfand
    'ergriffen' statt 'Gepackt' und 'Heldenhafte' statt 'Heldische Inspiration', weil nur
    art='term'-Felder das Glossar sahen). Zwei Kanäle:
    (a) `glossar.begriffe_im_text` - der bewährte Inline-Scanner des MCP-Servers - findet
        Glossar-Lemmata in den englischen Texten (Wortgrenzen, Homonym-Stoppliste aktiv);
    (b) die 2024-Aktionsnamen (Attack/Magic/... sind bewusst Homonym-gestoppt) kommen
        direkt aus ihren Glossar-Zeilen (Quelle 'SRD 5.2.1 (Aktionen)', srd-de-verifiziert)."""
    from app import glossar
    gesamt = "\n".join(texte)
    for z in glossar.begriffe_im_text(con, gesamt, max_treffer=80):
        vorgaben.setdefault(z["term_en"], z["term_de"])
    try:
        zeilen = con.execute("SELECT term_en, term_de FROM glossar WHERE quelle = ?",
                             ("SRD 5.2.1 (Aktionen)",)).fetchall()
    except sqlite3.OperationalError:       # Test-Minimalschema ohne quelle-Spalte
        zeilen = []
    for z in zeilen:
        vorgaben.setdefault(z["term_en"], z["term_de"])


def _listen_items(s: str) -> list[str]:
    return [t.strip() for t in (s or "").split(",") if t.strip()]


def _liste_deterministisch(con: sqlite3.Connection, en: str, nachschlager,
                           vorgaben: dict[str, str]) -> str:
    """Listen (Waffen-/Werkzeug-/Sprachlisten) KOMPLETT ohne Sprachmodell: jedes Item
    einzeln ueber Glossar bzw. Nachschlager aufloesen; Unbelegtes bleibt unveraendert
    englisch. Der Komma-Split ist sicher, weil invertierte SRD-Namen ('Crossbow, Hand')
    schon im Extractor normalisiert wurden. Grund (Befund 17.07.2026): das LLM uebersetzte
    unbelegte Eigennamen ('Wargong') bei jedem Lauf anders ('Kriegsgong'/'Trommel'/
    unveraendert) - deterministisch heisst hier: belegte Items IMMER amtlich, unbelegte
    IMMER original. §5 bleibt auf Listenebene gewahrt ('de1, de2, en3 (en1, en2, en3)');
    ist KEIN Item belegt, bleibt die Liste ehrlich englisch ohne redundante Klammer."""
    items = _listen_items(en)
    des: list[str] = []
    uebersetzt = False
    for item in items:
        aufl = terminologie.aufloesen(con, item)
        if aufl is None and nachschlager is not None:
            aufl = nachschlager(con, item)
        if aufl is not None:
            de_item = _de_klar(aufl)
            vorgaben.setdefault(item, de_item)      # Konsistenz im Fliesstext (Stufe 2)
            des.append(de_item)
            uebersetzt = True
        else:
            des.append(item)
    if not uebersetzt:
        return en
    return f"{', '.join(des)} ({en})"


class DnddeutschNachschlager:
    """Nachfragegetriebenes Glossar-Nachschlagen (16.07.2026): Der BOGEN - nicht der
    Foliant-Bestand - bestimmt, welche Begriffe gebraucht werden. Unbelegte Begriffe werden
    vor der LLM-Stufe bei dnddeutsch nachgeschlagen (Datei-Cache + Drossel wie beim
    Glossar-Seeding); Treffer werden Best-Effort ins Glossar geschrieben (die Web-DB ist
    read-only+immutable - dann bleibt es beim Direktergebnis) und OHNE Stern gerendert.
    Offline, kein Treffer oder Zeitbudget erschöpft -> None: der Begriff geht wie bisher
    an das Sprachmodell und trägt den ehrlichen Stern.

    Das Zeitbudget deckelt den Erstkontakt (nur Cache-MISSES kosten die Drossel-Pause);
    ab dem zweiten Bogen sind die Begriffe gecacht und gratis."""

    def __init__(self, zeitbudget_s: float = 30.0, pause_s: float = 0.5):
        self._budget = zeitbudget_s
        self._pause = pause_s
        self._frist: float | None = None
        self._client = None

    def _hole(self, begriff: str) -> dict:
        from app import dnddeutsch
        import httpx
        if self._client is None:
            self._client = httpx.Client(timeout=10.0,
                                        headers={"User-Agent": dnddeutsch.USER_AGENT})
        return dnddeutsch.hole(self._client, begriff, pause_s=self._pause)

    def __call__(self, con: sqlite3.Connection, begriff: str) -> str | None:
        import time
        from app import dnddeutsch, glossar
        if self._frist is None:
            self._frist = time.monotonic() + self._budget
        if time.monotonic() > self._frist:
            return None                    # Budget erschöpft -> Rest wie bisher (LLM + '*')
        try:
            zeilen = dnddeutsch.zeilen_aus_antwort(self._hole(begriff))
        except Exception:                  # offline/API-Fehler -> sauber degradieren
            return None
        if not zeilen:
            return None
        treffer = [z for z in zeilen if z.term_en.casefold() == begriff.casefold()]
        if not treffer:
            return None
        best = sorted(treffer, key=lambda z: (-z.offiziell,
                                              not z.quelle.startswith("Ulisses")))[0]
        try:                               # Best-Effort: Glossar dauerhaft verbessern
            dnddeutsch.schreibe_zeilen(con, zeilen)
            con.commit()
            glossar._GLOSSAR_CACHE.clear()
        except sqlite3.Error:
            pass                           # read-only (Web-Container) -> Direktergebnis reicht
        return glossar.markiere(best.term_de, begriff, bool(best.offiziell))


_MEHRKLASSEN_TEIL = re.compile(r"\s*([^\d/]+?)\s+(\d+)\s*$")


def _mehrklassen_aufbereiten(charakter: Charakter, con: sqlite3.Connection) -> None:
    """Mehrklassig ('Fighter 3 / Wizard 2'): Der Extractor laesst klasse/stufe bewusst
    leer (nicht eindeutig einklassig, §7.4) - auf dem Bogen standen dadurch STUMM leere
    Felder, was wie ein Konvertierungsfehler aussah (Befund 17.07.2026). Deterministische
    Aufbereitung OHNE Raten: jede Teil-Klasse nur bei EXAKTEM Glossar-Treffer uebersetzt
    (sonst bleibt sie englisch), die Charakterstufe ist regeldefiniert die SUMME der
    Klassenstufen (srd-de 'Klassenkombinationen', S. 28)."""
    ident = charakter.identitaet
    roh = (ident.klasse_stufe_roh or "").strip()
    if ident.klasse is not None or not roh or "/" not in roh:
        return
    teile = [_MEHRKLASSEN_TEIL.fullmatch(t) for t in roh.split("/")]
    if not all(teile):
        return                                       # unbekanntes Format - nichts raten
    namen_de: list[str] = []
    uebersetzt = False
    summe = 0
    for m in teile:
        en, stufe = m.group(1).strip(), int(m.group(2))
        summe += stufe
        aufl = terminologie.aufloesen(con, en)
        if aufl is not None:
            namen_de.append(f"{_de_klar(aufl)} {stufe}")
            uebersetzt = True
        else:
            namen_de.append(f"{en} {stufe}")
    anzeige = " / ".join(namen_de)
    ident.mehrklassen_anzeige = f"{anzeige} ({roh})" if uebersetzt else roh
    ident.stufe = summe


def uebersetze(charakter: Charakter, con: sqlite3.Connection,
               provider: Uebersetzungsprovider,
               nachschlager=None) -> Charakter:
    """Füllt `.de` aller übersetzbaren Felder in-place und gibt `charakter` zurück.

    ZWEISTUFIG (Befund 16.07.2026): Erst werden die unbelegten BEGRIFFE/Eigennamen übersetzt
    (Stufe 1), dann laufen sie als `vorgaben` in den Fließtext-Aufruf (Stufe 2). Vorher
    übersetzte ein einziger Aufruf beides unabhängig voneinander - derselbe Name hieß dann
    im Feld "Krieger des Schattens" und im Fließtext "Kämpfer des Schattens". Belegte
    Begriffe brauchen die Stufe nicht: sie kommen deterministisch aus dem Glossar.

    `nachschlager` (optional, z.B. `DnddeutschNachschlager()`): wird VOR Stufe 1 je
    unbelegtem Begriff gefragt - Treffer gelten als belegt (ohne Stern, ohne LLM).
    Default None hält Tests und Bibliotheksnutzung netzfrei; der Web-Produktionspfad
    aktiviert ihn explizit.
    """
    uetexte: list[UeText] = []
    _alle_uetexte(charakter, uetexte)

    vorgaben: dict[str, str] = {}                  # EN-Begriff -> dt. Name (Konsistenz im Fließtext)
    begriffe: dict[str, list[UeText]] = {}         # art="term" OHNE Glossar-Treffer -> Stufe 1
    texte: dict[str, list[UeText]] = {}            # Fließtext/Listen -> Stufe 2
    for ue in uetexte:
        en = (ue.en or "").strip()
        if not en:
            ue.de = ""
            continue
        if ue.art == "name":
            ue.de = ue.en
            continue
        if ue.art == "term":
            aufl = terminologie.aufloesen(con, en)
            if aufl is not None:
                ue.de = aufl                        # exakter Glossar-Treffer -> ohne LLM
                vorgaben[en] = _de_klar(aufl)       # denselben Namen im Fließtext erzwingen (Bug: Zauber
                continue                            # hieß in Tabelle "Magierhand", in Merkmal "Zauberhand")
            begriffe.setdefault(en, []).append(ue)
            continue
        if ue.art == "liste":
            # Listen KOMPLETT deterministisch - item-weise Glossar/Nachschlager, nie LLM
            # (Befund 17.07.2026: 'Wargong' hiess sonst bei jedem Lauf anders).
            ue.de = _liste_deterministisch(con, en, nachschlager, vorgaben)
            continue
        texte.setdefault(en, []).append(ue)

    # Stufe 0: nachfragegetriebenes Nachschlagen (dnddeutsch) - Treffer sind BELEGT
    if begriffe and nachschlager is not None:
        offen: dict[str, list[UeText]] = {}
        for en, ues in begriffe.items():
            aufl = nachschlager(con, en)
            if aufl:
                for ue in ues:
                    ue.de = aufl
                vorgaben[en] = _de_klar(aufl)
            else:
                offen[en] = ues
        begriffe = offen

    # Stufe 1: unbelegte Begriffe/Eigennamen -> §5-Form mit '*' UND feste Vorgabe für Stufe 2
    if begriffe:
        eindeutig = list(begriffe.keys())
        ids = {str(i): en for i, en in enumerate(eindeutig)}
        ergebnis, _ = _mit_wiederholung(provider, ids, vorgaben)
        for i, en in enumerate(eindeutig):
            de = ergebnis[str(i)]
            for ue in begriffe[en]:
                ue.de = terminologie.markiere_fallback(en, de)
            vorgaben[en] = _de_klar(de)

    # Stufe 2: Fließtexte - mit allen Namen aus Glossar + Stufe 1 + Listen als Vorgabe
    # (Listen selbst laufen seit 17.07.2026 deterministisch, nie durchs Modell).
    if texte:
        eindeutig = list(texte.keys())
        _glossar_vorgaben(con, eindeutig, vorgaben)
        ids = {str(i): en for i, en in enumerate(eindeutig)}
        ergebnis, _ = _mit_wiederholung(provider, ids, vorgaben)
        for i, en in enumerate(eindeutig):
            for ue in texte[en]:
                ue.de = _anwenden(ue, en, ergebnis[str(i)])

    _mehrklassen_aufbereiten(charakter, con)
    return charakter


def _mit_wiederholung(provider: Uebersetzungsprovider, ids: dict[str, str],
                      vorgaben: dict[str, str] | None = None,
                      ) -> tuple[dict[str, str], set[str]]:
    """Ein gebündelter Aufruf; bei ungültigem/unvollständigem Ergebnis genau EINMAL erneut,
    danach kontrolliert scheitern (AUFTRAG §8.3). (Der frühere Listen-Anzahl-Guard ist
    obsolet: Listen laufen seit 17.07.2026 gar nicht mehr durchs Sprachmodell.)"""
    letzter: Exception | None = None
    for versuch in range(2):
        try:
            ergebnis = provider.uebersetze(dict(ids), vorgaben)
            _pruefe_schluessel(ids, ergebnis)
        except Exception as e:  # noqa: BLE001 - Provider-/Format-Fehler bewusst gefangen
            letzter = e
            continue
        return ergebnis, set()
    raise UebersetzungsFehler(f"Übersetzung fehlgeschlagen: {letzter}")


def _pruefe_schluessel(ein: dict, aus) -> None:
    if not isinstance(aus, dict):
        raise UebersetzungsFehler("Provider-Antwort ist kein Objekt")
    if set(aus.keys()) != set(ein.keys()):
        raise UebersetzungsFehler("Provider-Antwort hat abweichende Schlüssel")
    for k, v in aus.items():
        if not isinstance(v, str):
            raise UebersetzungsFehler(f"Wert zu Schlüssel {k} ist kein String")


# --- Anthropic-Adapter (MVP) -------------------------------------------------

_SYSTEM = (
    "Du übersetzt Felder eines D&D-5e-Charakterbogens (Fassung 2024) ins Deutsche. "
    "Eingabe ist ein JSON-Objekt {id: englischer Text}. Gib AUSSCHLIESSLICH ein JSON-Objekt "
    "mit GENAU denselben Schlüsseln zurück, Werte = deutsche Übersetzung. "
    "STIL: knappe Regel-Kurzform - Stichwort- und Telegrammstil ist der STANDARD, keine "
    "vollständigen Sätze nötig (Beispiel: 'Bonusaktion: zwei waffenlose Schläge. Kosten: "
    "1 Fokuspunkt.'). Aber INHALTLICH VOLLSTÄNDIG: keine Regelangabe weglassen "
    "(Voraussetzungen, Kosten, Reichweiten, Dauern, Bedingungen, Ausnahmen), nichts sinngemäß "
    "zusammenfassen, nichts hinzuerfinden. Struktur und Hierarchie des Originals beibehalten "
    "(Absätze, Aufzählungen, 'Name. Wirkung'-Muster). Listen behalten EXAKT dieselbe Anzahl "
    "Einträge - nie einen Eintrag aufspalten oder ergänzen. "
    "NOTATION: alle Zahlen, Modifikatoren (+7), SG-Werte und Eigennamen unverändert; Würfel "
    "deutsch (1d8+4 -> 1W8+4, d20 -> W20); Entfernungen in Metern (1,5 m je 5 Fuß: 5 ft -> "
    "1,5 m, 10 ft -> 3 m, 30 ft -> 9 m, 60 ft -> 18 m). "
    "ABKÜRZUNGEN (verbindlich, nie eigene erfinden): Attribute STÄ, GES, KON, INT, WEI, CHA "
    "(z.B. 'WEI-Modifikator', nie 'Wei.' oder 'Gsch.'); SG (Schwierigkeitsgrad), "
    "RK (Rüstungsklasse), TP (Trefferpunkte); 'Übungsbonus' ausschreiben. "
    "SPRACHE: offizielle deutsche D&D-Begriffe; korrektes Genus und Kongruenz ('ein Talent', "
    "nicht 'einen Talent'); zusammengesetzte Namen durchkoppeln ('Nebelwanderer-"
    "Attributswerterhöhung'); 'Vorteil/Nachteil BEI' Würfen. Negationen exakt erhalten - die "
    "Verneinung gilt für beide Glieder: 'you aren't wearing armor or wielding a Shield' = "
    "'du trägst keine Rüstung und führst keinen Schild' (nie '... oder einen Schild'). "
    "Schreibe normal - übernimm KEINE Grossschreibung aus diesen Anweisungen in die "
    "Übersetzung. Keine Erklärungen, nur JSON."
)


class AnthropicProvider:
    """MVP-Adapter über die Anthropic Messages API (httpx). Key/Modell kommen vom Aufrufer
    (aus .env), werden NIE hart kodiert. Es wird nur der nötige Text gesendet, kein PDF."""

    def __init__(self, api_key: str, modell: str, timeout: float = 90.0,
                 max_tokens: int = 16000, basis_url: str = "https://api.anthropic.com/v1/messages"):
        if not api_key or not modell:
            raise ProviderNichtKonfiguriert("ANTHROPIC_API_KEY/ANTHROPIC_MODEL fehlen")
        self._key = api_key
        self._modell = modell
        self._timeout = timeout
        self._max_tokens = max_tokens
        self._url = basis_url

    def uebersetze(self, felder: dict[str, str],
                   vorgaben: dict[str, str] | None = None) -> dict[str, str]:
        import httpx
        system = _SYSTEM
        if vorgaben:
            paare = "; ".join(f"{en} = {de}" for en, de in sorted(vorgaben.items()))
            system += (" Verwende für diese Spielbegriffe im Fließtext KONSISTENT genau diese "
                       "deutschen Namen (ohne Klammerzusatz; gebeugt, wo die Grammatik es "
                       f"verlangt): {paare}.")
        rumpf = {
            "model": self._modell,
            "max_tokens": self._max_tokens,
            # Übersetzen ist keine Reasoning-Aufgabe: Extended Thinking macht den Aufruf nur
            # langsam (>3 min, sprengt Timeouts/Cloudflare) ohne Qualitätsgewinn -> aus.
            "thinking": {"type": "disabled"},
            "system": system,
            "messages": [{"role": "user", "content": json.dumps(felder, ensure_ascii=False)}],
        }
        kopf = {"x-api-key": self._key, "anthropic-version": "2023-06-01",
                "content-type": "application/json"}
        with httpx.Client(timeout=self._timeout) as client:
            antwort = client.post(self._url, headers=kopf, json=rumpf)
            if antwort.status_code in (429, 500, 502, 503, 529):
                # Überlast (529/429) ist transient: kurzer Backoff, genau EIN neuer Versuch -
                # der sofortige Retry von _mit_wiederholung trifft sonst dieselbe Überlast.
                import time
                time.sleep(8)
                antwort = client.post(self._url, headers=kopf, json=rumpf)
            antwort.raise_for_status()
            daten = antwort.json()
        text = "".join(b.get("text", "") for b in daten.get("content", []) if b.get("type") == "text")
        return _json_aus_text(text)


def _json_aus_text(text: str) -> dict:
    """Extrahiert das JSON-Objekt aus einer Modellantwort (toleriert umschließenden Text)."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):]
    anfang, ende = text.find("{"), text.rfind("}")
    if anfang == -1 or ende == -1:
        raise UebersetzungsFehler("Keine JSON-Antwort erhalten")
    return json.loads(text[anfang:ende + 1])


def provider_aus_env() -> AnthropicProvider:
    """Baut den Provider aus .env-Variablen. Fehlt etwas -> ProviderNichtKonfiguriert."""
    return AnthropicProvider(os.environ.get("ANTHROPIC_API_KEY", ""),
                             os.environ.get("ANTHROPIC_MODEL", ""))


# --- Fake-Provider (Tests, deterministisch) ----------------------------------

class FakeProvider:
    """Deterministischer Test-Provider. `mapping` liefert feste Übersetzungen; sonst wird
    "de:<text>" zurückgegeben. Zählt Aufrufe (Übersetzungsgedächtnis-Nachweis)."""

    def __init__(self, mapping: dict[str, str] | None = None):
        self.mapping = mapping or {}
        self.aufrufe = 0
        self.gesehene_ids: list[dict] = []
        self.letzte_vorgaben: dict[str, str] = {}

    def uebersetze(self, felder: dict[str, str],
                   vorgaben: dict[str, str] | None = None) -> dict[str, str]:
        self.aufrufe += 1
        self.gesehene_ids.append(dict(felder))
        self.letzte_vorgaben = dict(vorgaben or {})
        return {k: self.mapping.get(v, f"de:{v}") for k, v in felder.items()}
