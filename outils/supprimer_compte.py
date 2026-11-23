#!/usr/bin/env python3
"""Efface les données d'un compte (identifiant YunoHost) : parties, manches, succès, records, compte.

    OUSUISJE_BASE=/var/lib/ou-suis-je/jeu.sqlite3 python3 outils/supprimer_compte.py <identifiant>

Pour un invité (cookie), le joueur peut aussi demander l'effacement de ses records : `--invite <joueur_id>`.
Les sauvegardes déjà faites (restic) gardent l'ancienne copie jusqu'à leur expiration.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from serveur import base  # noqa: E402


def supprimer_compte(identifiant: str) -> dict:
    with base.connexion() as c:
        parties = [r["id"] for r in c.execute("SELECT id FROM parties WHERE compte=?", (identifiant,))]
        for i in parties:
            c.execute("DELETE FROM manches WHERE partie_id=?", (i,))
        c.execute("DELETE FROM parties WHERE compte=?", (identifiant,))
        c.execute("DELETE FROM succes WHERE identifiant=?", (identifiant,))
        c.execute("DELETE FROM records WHERE joueur_id=?", ("c:" + identifiant,))
        n = c.execute("DELETE FROM comptes WHERE identifiant=?", (identifiant,)).rowcount
    return {"comptes": n, "parties": len(parties)}


def supprimer_invite(joueur_id: str) -> dict:
    with base.connexion() as c:
        parties = [r["id"] for r in c.execute("SELECT id FROM parties WHERE joueur_id=? AND compte IS NULL", (joueur_id,))]
        for i in parties:
            c.execute("DELETE FROM manches WHERE partie_id=?", (i,))
        c.execute("DELETE FROM parties WHERE joueur_id=? AND compte IS NULL", (joueur_id,))
        c.execute("DELETE FROM records WHERE joueur_id=?", (joueur_id,))
    return {"parties": len(parties)}


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) == 2 and a[0] == "--invite":
        print(supprimer_invite(a[1]))
    elif len(a) == 1 and not a[0].startswith("-"):
        print(supprimer_compte(a[0]))
    else:
        sys.exit(__doc__)
