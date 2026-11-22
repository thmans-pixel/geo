"""Qui est connecté ? L'identité vient du SSO de YunoHost : le reverse proxy pose l'identifiant dans un en-tête.

Le jeu ne voit jamais de mot de passe et n'en stocke aucun. L'application doit n'écouter que sur 127.0.0.1,
derrière nginx, et nginx doit remplacer cet en-tête (jamais le laisser venir du visiteur).
"""
import hmac
import re
import secrets

from . import base, config, horloge

IDENTIFIANT = re.compile(r"^[a-z0-9][a-z0-9._-]{0,31}$")


def _vient_du_proxy(request) -> bool:
    """L'en-tête n'est cru que s'il arrive du reverse proxy local (et, si réglé, avec le secret partagé)."""
    hote = request.client.host if request.client else ""
    if hote not in ("127.0.0.1", "::1"):
        return False
    secret = config.secret_proxy()
    return not secret or hmac.compare_digest(request.headers.get("X-Auth-Secret", ""), secret)


def identifiant(request) -> str | None:
    if not _vient_du_proxy(request):
        return None
    brut = (request.headers.get(config.entete_utilisateur()) or config.compte_essai()).strip().lower()
    return brut if IDENTIFIANT.match(brut) else None


def compte(request) -> dict | None:
    """Le compte de la personne connectée (créé à la première connexion), ou None pour un invité."""
    ident = identifiant(request)
    if ident is None:
        return None
    with base.connexion() as c:
        c.execute("INSERT OR IGNORE INTO comptes (identifiant, pseudo, cree_le) VALUES (?,?,?)",
                  (ident, f"Joueur-{secrets.randbelow(9000) + 1000}", horloge.maintenant()))
        r = c.execute("SELECT * FROM comptes WHERE identifiant=?", (ident,)).fetchone()
    return {"identifiant": r["identifiant"], "pseudo": r["pseudo"], "xp": r["xp"],
            "admin": bool(config.admin()) and ident == config.admin()}
