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


def plafond_images() -> int:
    """Nombre maximal d'images (manches × personnes qui regardent) servies par jour ; 0 = pas de plafond côté jeu."""
    try:
        return max(0, int(os.environ.get("OUSUISJE_PLAFOND_IMAGES", "0")))
    except ValueError:
        return 0


def cookie_secure() -> bool:
    """Cookie réservé à HTTPS. Vrai par défaut en mode « google » (production) ; OUSUISJE_COOKIE_SECURE=0/1 pour forcer."""
    v = os.environ.get("OUSUISJE_COOKIE_SECURE")
    return (fournisseur_images() == "google") if v is None else v == "1"


def duree_garde_invites_jours() -> int:
    return int(os.environ.get("OUSUISJE_GARDE_INVITES_JOURS", "90"))


def duree_garde_comptes_jours() -> int:
    return int(os.environ.get("OUSUISJE_GARDE_COMPTES_JOURS", "365"))


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
