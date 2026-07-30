"""B9 unter Sessionlast: Antwortzeiten bei MEHREREN gleichzeitigen Spielern.

Die Einzelaufruf-Messung (BACKLOG §2) sagt, wie schnell ein Aufruf ist, wenn er allein
laeuft. B9 verlangt aber "schnell und verfuegbar im SPIELBETRIEB" - und da sitzen vier bis
sechs Leute an einem Tisch, die alle gleichzeitig etwas nachschlagen.

Warum Threads das richtige Modell sind: FastMCP fuehrt die sync-Tools im Threadpool aus,
und jeder Aufruf oeffnet seine EIGENE SQLite-Verbindung (app/db.py, Review-Fund). Genau das
bildet dieser Test nach - er misst also den Serving-Pfad unter echter Nebenlaeufigkeit,
nicht den HTTP-Mantel darum.

Aufruf auf dem Pi:
    docker compose exec -T -w /app foliant python -m evals.lasttest
    docker compose exec -T -w /app foliant python -m evals.lasttest --stufen 1,4,8 --runden 6

Der Test ist REIN LESEND (connect_readonly-Pfad der Tools) und kann gefahrlos gegen den
Live-Bestand laufen.
"""
from __future__ import annotations

import argparse
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor


def _mix() -> list[tuple[str, callable]]:
    """Ein realistischer Sessionschnitt statt einer einzelnen Abfrage: In der Runde wird
    gesucht, nachgeschlagen, uebersetzt und ein Build geprueft - die Mischung entscheidet
    ueber die Last, nicht der guenstigste Fall."""
    from app.tools import charakter as ch
    from app.tools import nachschlagen as ns
    return [
        ("suche_regel", lambda: ns.foliant_suche_bestand("Gelegenheitsangriff")),
        ("suche_zauber", lambda: ns.foliant_suche_bestand("Feuerball")),
        ("detail_zauber", lambda: ns.foliant_hol_eintrag("zauber", "Feuerball")),
        ("detail_monster", lambda: ns.foliant_hol_eintrag("monster", "Vampirbrut")),
        ("uebersetzung", lambda: ns.foliant_uebersetze_begriff("Fireball")),
        ("facettenfilter", lambda: ns.foliant_suche_bestand(kategorie="zauber", grad=3)),
        ("klasse", lambda: ns.foliant_hol_eintrag("klasse", "Kämpfer")),
    ]


def _runde(mix, runden: int) -> list[float]:
    """Ein simulierter Spieler: `runden` mal den kompletten Mix, Zeit je Aufruf."""
    zeiten = []
    for _ in range(runden):
        for _name, fn in mix:
            t0 = time.perf_counter()
            fn()
            zeiten.append((time.perf_counter() - t0) * 1000)
    return zeiten


def messe(stufen: list[int], runden: int) -> list[dict]:
    mix = _mix()
    for _name, fn in mix:                      # Warmlauf: Caches fuellen (Phase 2)
        fn()
    ergebnisse = []
    for gleichzeitig in stufen:
        start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=gleichzeitig) as pool:
            alle = [z for teil in pool.map(lambda _: _runde(mix, runden),
                                           range(gleichzeitig)) for z in teil]
        dauer = time.perf_counter() - start
        alle.sort()
        ergebnisse.append({
            "gleichzeitig": gleichzeitig,
            "aufrufe": len(alle),
            "p50": statistics.median(alle),
            "p95": alle[min(int(len(alle) * 0.95), len(alle) - 1)],
            "max": alle[-1],
            "durchsatz": len(alle) / dauer,
        })
    return ergebnisse


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="B9: Antwortzeiten unter Sessionlast")
    p.add_argument("--stufen", default="1,2,4,8",
                   help="Nebenlaeufigkeitsstufen (gleichzeitige Spieler), Komma-getrennt")
    p.add_argument("--runden", type=int, default=5,
                   help="Wie oft jeder Spieler den kompletten Aufruf-Mix durchlaeuft")
    # B9 nennt keine Zahl; 1000 ms ist die Schwelle, ab der eine Nachfrage am Tisch
    # spuerbar stockt (drei bis fuenf Tool-Aufrufe je Antwort).
    p.add_argument("--grenze-p95", type=float, default=1000.0,
                   help="p95-Grenze in ms, ab der der Lauf als Befund gilt")
    args = p.parse_args(argv)

    stufen = [int(s) for s in args.stufen.split(",") if s.strip()]
    ergebnisse = messe(stufen, args.runden)

    print(f"{'gleichzeitig':>13}{'Aufrufe':>9}{'p50 ms':>9}{'p95 ms':>9}{'max ms':>9}"
          f"{'Aufrufe/s':>11}")
    for e in ergebnisse:
        print(f"{e['gleichzeitig']:>13}{e['aufrufe']:>9}{e['p50']:>9.1f}{e['p95']:>9.1f}"
              f"{e['max']:>9.1f}{e['durchsatz']:>11.1f}")

    einzeln = ergebnisse[0]["p50"] if ergebnisse else 0.0
    schlimmster = max((e["p95"] for e in ergebnisse), default=0.0)
    print()
    if einzeln:
        faktor = max(e["p50"] for e in ergebnisse) / einzeln
        print(f"p50 waechst um Faktor {faktor:.1f} von {stufen[0]} auf {stufen[-1]} "
              f"gleichzeitige Spieler.")
    if schlimmster > args.grenze_p95:
        print(f"BEFUND: p95 {schlimmster:.0f} ms ueber der Grenze von "
              f"{args.grenze_p95:.0f} ms - B9 unter Last nicht erfuellt.")
        return 1
    print(f"OK: p95 bleibt unter {args.grenze_p95:.0f} ms - B9 auch unter Last erfuellt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
