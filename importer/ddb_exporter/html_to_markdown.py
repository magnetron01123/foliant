"""DDB-HTML -> bereinigtes GFM-Markdown (Vorschlag §11).

Zweistufig: (1) BEREINIGUNG entfernt aktive Inhalte (script/style/iframe/Formulare,
on*-Eventhandler, javascript:-Links) und ersetzt Bilder durch ihren Alt-Text -
Bilder werden in Version 1 nicht geladen; (2) markdownify konvertiert den Rest,
Tabellen bleiben als GFM erhalten. DDB-Links werden auf absolute dndbeyond-URLs
normalisiert (Provenienz), der Linktext bleibt."""
from __future__ import annotations

import re

from bs4 import BeautifulSoup
from markdownify import markdownify

_AKTIV = ("script", "style", "iframe", "form", "input", "button", "object", "embed")
_DDB_BASIS = "https://www.dndbeyond.com"


def bereinige_html(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup.find_all(_AKTIV):
        tag.decompose()
    for tag in soup.find_all(True):
        for attr in [a for a in tag.attrs if a.lower().startswith("on")]:
            del tag[attr]
    for img in soup.find_all("img"):
        alt = (img.get("alt") or "").strip()
        img.replace_with(f"[Bild: {alt}]" if alt else "")
    for a in soup.find_all("a"):
        href = (a.get("href") or "").strip()
        niedrig = href.lower()
        if niedrig.startswith(("http://", "https://")):
            pass                                    # externe Links bleiben
        elif href.startswith("/"):
            a["href"] = _DDB_BASIS + href           # DDB-Pfad-Links normalisieren (Provenienz)
        else:
            # ddb://…, javascript:, mailto:, Anker etc. sind interne/nutzlose Verweise
            # -> nur den sichtbaren Text behalten (Namen wie 'Priest of Osybus' bleiben sauber).
            a.replace_with(a.get_text())
    return str(soup)


_DDB_LINK_MD = re.compile(r"\[([^\]]*)\]\(ddb://[^)]*\)")   # [Text](ddb://...) -> Text
_DDB_BARE = re.compile(r"<?ddb://\S+>?")                     # nackte ddb://-URL -> weg


def html_zu_markdown(html: str) -> str:
    md = markdownify(bereinige_html(html), heading_style="ATX", bullets="-")
    md = _DDB_LINK_MD.sub(r"\1", md)                # interne Markdown-Links -> nur Text
    md = _DDB_BARE.sub("", md)                      # nackte ddb://-URLs entfernen
    md = re.sub(r"\n{3,}", "\n\n", md)              # Leerzeilen-Wildwuchs eindampfen
    return md.strip()
