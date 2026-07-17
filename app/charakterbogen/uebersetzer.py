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
    """LLM-Ergebnis in die §5-Endform bringen."""
    if ue.art == "term":
        return terminologie.markiere_fallback(en, de_roh)   # "de* (en)"
    if ue.art == "liste":
        return f"{de_roh} ({en})"                            # §5 auf Listenebene, kein per-Item-*
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


def uebersetze(charakter: Charakter, con: sqlite3.Connection,
               provider: Uebersetzungsprovider) -> Charakter:
    """Füllt `.de` aller übersetzbaren Felder in-place und gibt `charakter` zurück.

    ZWEISTUFIG (Befund 16.07.2026): Erst werden die unbelegten BEGRIFFE/Eigennamen übersetzt
    (Stufe 1), dann laufen sie als `vorgaben` in den Fließtext-Aufruf (Stufe 2). Vorher
    übersetzte ein einziger Aufruf beides unabhängig voneinander - derselbe Name hieß dann
    im Feld "Krieger des Schattens" und im Fließtext "Kämpfer des Schattens". Belegte
    Begriffe brauchen die Stufe nicht: sie kommen deterministisch aus dem Glossar.
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
        texte.setdefault(en, []).append(ue)

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

    # Stufe 2: Fließtexte/Listen - mit allen Namen aus Glossar + Stufe 1 als Vorgabe
    if texte:
        eindeutig = list(texte.keys())
        _glossar_vorgaben(con, eindeutig, vorgaben)
        ids = {str(i): en for i, en in enumerate(eindeutig)}
        listen_ids = {str(i) for i, en in enumerate(eindeutig)
                      if any(ue.art == "liste" for ue in texte[en])}
        ergebnis, kaputte = _mit_wiederholung(provider, ids, vorgaben, listen_ids)
        for i, en in enumerate(eindeutig):
            k = str(i)
            for ue in texte[en]:
                if k in kaputte and ue.art == "liste":
                    ue.de = en          # Item-Anzahl weicht auch nach Retry ab -> ehrlich
                else:                   # englisch lassen statt erfundene Einträge rendern
                    ue.de = _anwenden(ue, en, ergebnis[k])
    return charakter


def _mit_wiederholung(provider: Uebersetzungsprovider, ids: dict[str, str],
                      vorgaben: dict[str, str] | None = None,
                      listen_ids: frozenset[str] | set[str] = frozenset(),
                      ) -> tuple[dict[str, str], set[str]]:
    """Ein gebündelter Aufruf; bei ungültigem/unvollständigem Ergebnis genau EINMAL erneut,
    danach kontrolliert scheitern (AUFTRAG §8.3). Listenfelder (art='liste') müssen dieselbe
    Item-Anzahl behalten (Befund 16.07.2026: 'Crossbow, Hand' wurde zu ZWEI Waffen) - eine
    Abweichung erzwingt den Retry; bleibt sie, meldet die Rückgabe die betroffenen ids."""
    letzter: Exception | None = None
    for versuch in range(2):
        try:
            ergebnis = provider.uebersetze(dict(ids), vorgaben)
            _pruefe_schluessel(ids, ergebnis)
        except Exception as e:  # noqa: BLE001 - Provider-/Format-Fehler bewusst gefangen
            letzter = e
            continue
        kaputte = {k for k in listen_ids
                   if len(_listen_items(ergebnis[k])) != len(_listen_items(ids[k]))}
        if kaputte and versuch == 0:
            letzter = UebersetzungsFehler(f"Listen-Item-Anzahl abweichend: {sorted(kaputte)}")
            continue
        return ergebnis, kaputte
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
