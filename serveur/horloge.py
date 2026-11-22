"""Horloge du jeu : un seul endroit à remplacer dans les tests."""
import time
from datetime import datetime
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")


def maintenant() -> float:
    return time.time()


def jour_paris(ts: float | None = None) -> str:
    """Date AAAA-MM-JJ à Paris (le défi du jour change à minuit, heure de Paris)."""
    return datetime.fromtimestamp(maintenant() if ts is None else ts, PARIS).strftime("%Y-%m-%d")
