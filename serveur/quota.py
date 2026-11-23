"""Plafond d'images par jour (critère 31).

Le vrai garde-fou contre une facture est le quota réglé chez Google (voir deploiement/LISEZMOI.md). Ce compteur est la
ceinture en plus des bretelles : il arrête le jeu proprement, avec un message, avant que Google ne refuse.
Une « image » = un panorama chargé par un navigateur : une manche pour chaque personne qui la regarde (joueurs et spectateurs).
"""
from . import base, config, horloge

MESSAGE = "Plus d'images pour aujourd'hui, reviens demain."


def consommer(n: int = 1, c=None) -> None:
    """Compte n images ; lève une erreur claire si le plafond du jour serait dépassé (rien n'est alors compté)."""
    if config.fournisseur_images() != "google":
        return
    from .jeu.moteur import ErreurJeu          # import tardif : moteur.py importe ce module
    jour = horloge.jour_paris()
    plafond = config.plafond_images()
    if c is None:                      # sinon on réutilise la connexion de l'appelant (une seconde connexion se bloquerait sur ses écritures)
        with base.connexion() as c2:
            return consommer(n, c2)
    c.execute("INSERT OR IGNORE INTO usage_images (jour, n) VALUES (?, 0)", (jour,))
    deja = c.execute("SELECT n FROM usage_images WHERE jour=?", (jour,)).fetchone()["n"]
    if plafond and deja + n > plafond:
        raise ErreurJeu(503, MESSAGE, plus_d_images=True)
    c.execute("UPDATE usage_images SET n = n + ? WHERE jour=?", (n, jour))


def usage() -> dict:
    jour = horloge.jour_paris()
    with base.connexion() as c:
        lignes = c.execute("SELECT jour, n FROM usage_images ORDER BY jour DESC LIMIT 8").fetchall()
    aujourdhui = next((r["n"] for r in lignes if r["jour"] == jour), 0)
    return {"jour": jour, "aujourdhui": aujourdhui, "plafond": config.plafond_images(),
            "derniers_jours": [{"jour": r["jour"], "n": r["n"]} for r in lignes]}
