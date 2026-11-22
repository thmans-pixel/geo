from pathlib import Path

import pytest

from serveur import horloge

DONNEES = Path(__file__).parent / "donnees"


@pytest.fixture(autouse=True)
def environnement(tmp_path, monkeypatch):
    monkeypatch.setenv("OUSUISJE_BASE", str(tmp_path / "jeu.sqlite3"))
    monkeypatch.setenv("OUSUISJE_IMAGES", "factice")
    monkeypatch.setenv("OUSUISJE_PAYS", str(DONNEES / "pays_test.geojson"))


@pytest.fixture
def temps(monkeypatch):
    """Horloge réglable : temps.t est l'heure courante (secondes)."""
    class H:
        t = 1_800_000_000.0
    monkeypatch.setattr(horloge, "maintenant", lambda: H.t)
    return H
