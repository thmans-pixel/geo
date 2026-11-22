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


def entete_utilisateur() -> str:
    """En-tête posé par le reverse proxy (SSO YunoHost) avec l'identifiant de la personne connectée."""
    return os.environ.get("OUSUISJE_ENTETE", "Remote-User")


def secret_proxy() -> str:
    """Si réglé, le reverse proxy doit aussi poser l'en-tête X-Auth-Secret avec cette valeur."""
    return os.environ.get("OUSUISJE_SECRET_PROXY", "")


def compte_essai() -> str:
    """Pour essayer la connexion en local. Ignoré dès que les images sont réelles (production)."""
    if fournisseur_images() == "google":
        return ""
    return os.environ.get("OUSUISJE_COMPTE_ESSAI", "").strip().lower()


def admin() -> str:
    """Identifiant YunoHost de l'administrateur (éditeur de cartes, compteur d'images)."""
    return os.environ.get("OUSUISJE_ADMIN", "").strip().lower()


def url_connexion() -> str:
    return os.environ.get("OUSUISJE_URL_CONNEXION", "/yunohost/sso/")


def chemin_pays() -> Path:
    return Path(os.environ.get("OUSUISJE_PAYS", DONNEES / "pays.geojson"))


def dossier_reserves() -> Path:
    return Path(os.environ.get("OUSUISJE_RESERVES", RACINE / "donnees-locales" / "reserves"))
