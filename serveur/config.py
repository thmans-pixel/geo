"""Réglages lus dans l'environnement à chaque appel (pratique pour les tests)."""
import os
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
DONNEES = Path(__file__).resolve().parent / "donnees"


def chemin_base() -> Path:
    return Path(os.environ.get("OUSUISJE_BASE", RACINE / "donnees-locales" / "jeu.sqlite3"))


def fournisseur_images() -> str:
    """« factice » (essai, aucune image réelle, aucun coût) ou « google » (Street View)."""
    return os.environ.get("OUSUISJE_IMAGES", "factice")


def cle_google() -> str:
    return os.environ.get("OUSUISJE_GOOGLE_KEY", "")


def cle_google_outil() -> str:
    """Clé réservée à outils/generer_reserve.py (API Metadata, appelée depuis thnas, jamais montrée au navigateur)."""
    return os.environ.get("OUSUISJE_GOOGLE_KEY_OUTIL", "")


def chemin_pays() -> Path:
    return Path(os.environ.get("OUSUISJE_PAYS", DONNEES / "pays.geojson"))


def dossier_reserves() -> Path:
    return Path(os.environ.get("OUSUISJE_RESERVES", RACINE / "donnees-locales" / "reserves"))
