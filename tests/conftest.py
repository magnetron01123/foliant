"""Gemeinsame Test-Leitplanken."""
import pytest

from app import protokoll as _protokoll


@pytest.fixture(autouse=True)
def _protokoll_isolieren(tmp_path, monkeypatch):
    """Das Abfrage-Protokoll schreibt sonst bei JEDEM Tool-Aufruf in data/ des
    Arbeitskopie-Checkouts - Tests duerfen den Dev-Bestand nicht anfassen.
    Tests, die das Protokoll selbst pruefen, ueberschreiben den Pfad erneut."""
    monkeypatch.setattr(_protokoll, "protokoll_pfad",
                        lambda: tmp_path / "protokoll-test.sqlite")
