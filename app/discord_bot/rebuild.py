"""Verlauf aus der Discord-Historie rekonstruieren, wenn der Bot ihn vergessen hat.

Der GespraechsSpeicher ist bewusst in-memory (gespraech.py); ein Pi-Neustart loescht
ihn. Statt das Gespraech aufzugeben, liest der Bot den Thread zurueck: die
Discord-Historie IST die Persistenz, neuer State entsteht nicht.

Diese Datei ist discord-frei und arbeitet auf (ist_bot, inhalt)-Paaren in
chronologischer Reihenfolge - damit vollstaendig ohne Discord testbar. Das Uebersetzen
echter Nachrichten in diese Paare macht bot.py."""
from __future__ import annotations

from app.discord_bot import antwort, schranken

# Bot-Nachrichten, die KEINE Antwort sind: sie duerfen nicht als Assistant-Turn in den
# Verlauf wandern. Verglichen wird auf Gleichheit - der max_tokens-Hinweis haengt an
# einem Teiltext ("<Antwort>\n\n⚠️ ..."), und der bleibt als echte Antwort erhalten.
_MELDUNGEN = frozenset({
    antwort.FEHLER_API,
    antwort.FEHLER_RUNDEN_CAP,
    antwort.FEHLER_REFUSAL,
    antwort.HINWEIS_VERGESSEN,
    schranken.ABGELEHNT_LAEUFT,
    schranken.ABGELEHNT_COOLDOWN,
    schranken.ABGELEHNT_TAGESDECKEL,
})


def baue_verlauf(nachrichten: list[tuple[bool, str]],
                 ersatzfrage: str | None = None) -> list[dict]:
    """(ist_bot, inhalt) chronologisch -> messages-Liste wie im GespraechsSpeicher.

    Regeln, jede aus dem echten Nachrichtenbild begruendet:
    - Aufeinanderfolgende Bot-Nachrichten sind die Teile EINER Antwort (antwort.teile
      schneidet an Absatzgrenzen) und werden wieder zusammengefuegt.
    - Nur vollstaendige Paare kommen in den Verlauf: eine unbeantwortete Frage (jemand
      hat im vergessenen Thread weitergeredet) wuerde die Rollen-Abwechslung brechen,
      die die Messages-API verlangt.
    - `ersatzfrage` faengt den /regel-Fall: dort steht die Frage nirgends im Thread
      (Slash-Parameter, kein Kanal-Beitrag), und der Startbeitrag ist bereits Teil 1
      der Antwort. Der Thread-TITEL ist die Frage - ggf. auf 100 Zeichen gekappt, was
      das angehaengte '…' sichtbar macht. Sie gilt nur ganz am Anfang.
    """
    verlauf: list[dict] = []
    offene_frage: str | None = None
    teile: list[str] = []

    def schliesse() -> None:
        if offene_frage is not None and teile:
            verlauf.append({"role": "user", "content": offene_frage})
            # "\n\n" ist die Naht, an der antwort.teile geschnitten hat. Ueber eine
            # Codeblock-Grenze hinweg bleiben die dort ergaenzten Zaeune stehen -
            # kosmetisch, inhaltlich folgenlos, und den Aufwand einer echten
            # Umkehrfunktion nicht wert.
            verlauf.append({"role": "assistant", "content": "\n\n".join(teile)})

    for ist_bot, inhalt in nachrichten:
        text = (inhalt or "").strip()
        if not text:
            continue                         # System-/Anhangs-Nachrichten
        if ist_bot:
            if text in _MELDUNGEN:
                continue
            if offene_frage is None:
                if verlauf or not ersatzfrage:
                    continue                 # herrenlose Antwort: verwerfen
                offene_frage = ersatzfrage
            teile.append(text)
        else:
            schliesse()
            offene_frage, teile = text, []
    schliesse()
    return verlauf
