"""Übersetzer (LLM-basiert, klar isoliert): füllt `.de` im neutralen Charaktermodell.

Strategie (KONZEPT §6, AUFTRAG §8):
- FESTE Begriffe/Namen (art="term"): deterministisch über `terminologie.aufloesen` (die
  bestehende Foliant-Glossar-Logik). Exakter Treffer -> §5-Form ohne LLM.
- FREIER Text (art="text") und unbelegte Begriffe -> EIN gebündelter LLM-Aufruf.
  Unbelegte Begriffe werden anschließend mit '*' markiert (§5).
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

def uebersetze(charakter: Charakter, con: sqlite3.Connection,
               provider: Uebersetzungsprovider) -> Charakter:
    """Füllt `.de` aller übersetzbaren Felder in-place und gibt `charakter` zurück."""
    uetexte: list[UeText] = []
    _alle_uetexte(charakter, uetexte)

    vorgaben: dict[str, str] = {}                  # EN-Begriff -> amtl. dt. Name (Konsistenz im Fließtext)
    zu_uebersetzen: dict[str, list[UeText]] = {}   # eindeutiger EN -> alle Vorkommen (Gedächtnis)
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
        zu_uebersetzen.setdefault(en, []).append(ue)

    if zu_uebersetzen:
        eindeutig = list(zu_uebersetzen.keys())
        ids = {str(i): en for i, en in enumerate(eindeutig)}
        ergebnis = _mit_wiederholung(provider, ids, vorgaben)
        for i, en in enumerate(eindeutig):
            de = ergebnis[str(i)]
            for ue in zu_uebersetzen[en]:
                ue.de = _anwenden(ue, en, de)
    return charakter


def _mit_wiederholung(provider: Uebersetzungsprovider, ids: dict[str, str],
                      vorgaben: dict[str, str] | None = None) -> dict[str, str]:
    """Ein gebündelter Aufruf; bei ungültigem/unvollständigem Ergebnis genau EINMAL erneut,
    danach kontrolliert scheitern (AUFTRAG §8.3)."""
    letzter: Exception | None = None
    for _ in range(2):
        try:
            ergebnis = provider.uebersetze(dict(ids), vorgaben)
            _pruefe_schluessel(ids, ergebnis)
            return ergebnis
        except Exception as e:  # noqa: BLE001 - Provider-/Format-Fehler bewusst gefangen
            letzter = e
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
    "mit GENAU denselben Schlüsseln zurück, Werte = deutsche Übersetzung. Stil: KOMPAKT wie "
    "ein Regel-Nachschlagetext (D&D Beyond): knappe, dichte Formulierungen, Telegrammstil ist "
    "erlaubt (keine Pflicht zu vollständigen Sätzen) - aber INHALTLICH VOLLSTÄNDIG: keine "
    "Regelangabe weglassen (Voraussetzungen, Kosten, Reichweiten, Dauern, Bedingungen, "
    "Ausnahmen); nichts sinngemäß zusammenfassen, nichts ergänzen. Behalte Struktur und "
    "Hierarchie des Originals bei (Absätze, Aufzählungen, 'Name. Wirkung'-Muster). Regeln: "
    "übernimm ALLE Zahlen, Modifikatoren (+7), Schwierigkeitsgrade und Eigennamen unverändert; "
    "Würfelnotation deutsch (1d8+4 -> 1W8+4); Entfernungen in Metern (dt. D&D 2024: 1,5 m je 5 Fuß, "
    "z.B. 30 ft -> 9 m); nutze offizielle deutsche D&D-Begriffe. Keine Erklärungen, nur JSON."
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
                       f"deutschen Namen (ohne Klammerzusatz): {paare}.")
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
