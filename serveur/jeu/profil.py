"""Profil, statistiques et classements des comptes."""
import json

from .. import base, horloge
from . import cartes, progression

SCORE_MODES = progression.SCORE_MODES
SEUIL_BIEN_RECONNU = 3000   # en Classique/Défi, une manche à 3 000 points ou plus compte comme « reconnue »
MIN_MANCHES_PAYS = 3        # un pays n'entre dans le palmarès qu'avec au moins 3 manches


def proprietaire_record(compte, joueur_id) -> str:
    """Clé des records : l'identifiant du compte s'il y en a un, sinon le cookie du navigateur."""
    return f"c:{compte}" if compte else joueur_id


def _nom_carte(carte_id) -> str:
    c = cartes.carte(carte_id)
    return c["nom"] if c else carte_id


def profil(compte: dict) -> dict:
    ident = compte["identifiant"]
    with base.connexion() as c:
        xp = c.execute("SELECT xp FROM comptes WHERE identifiant=?", (ident,)).fetchone()["xp"]
        jouees = c.execute("SELECT COUNT(*) FROM parties WHERE compte=? AND statut='terminee'", (ident,)).fetchone()[0]
        meilleurs = [{"carte": r["carte"], "nom": _nom_carte(r["carte"]), "total": r["m"]} for r in c.execute(
            f"SELECT carte, MAX(total) m FROM parties WHERE compte=? AND statut='terminee' AND mode IN {SCORE_MODES} "
            "AND nb_manches=5 GROUP BY carte ORDER BY m DESC", (ident,))]
        moyenne = c.execute(f"SELECT AVG(m.distance_m) FROM manches m JOIN parties p ON p.id=m.partie_id WHERE p.compte=? "
                            f"AND p.mode IN {SCORE_MODES} AND m.distance_m IS NOT NULL", (ident,)).fetchone()[0]
        records = {r["cle"].split(":", 1)[1]: r["valeur"] for r in c.execute(
            "SELECT cle, valeur FROM records WHERE joueur_id=? AND cle LIKE 'serie:%'", (proprietaire_record(ident, None),))}
        pays = []
        for r in c.execute(
                "SELECT json_extract(m.lieu_json,'$.pays') pays, COUNT(*) n, "
                "SUM(CASE WHEN p.mode='serie' THEN COALESCE(m.juste,0) WHEN m.points >= ? THEN 1 ELSE 0 END) ok "
                "FROM manches m JOIN parties p ON p.id=m.partie_id WHERE p.compte=? AND p.mode != 'exploration' "
                "AND m.repondu_le IS NOT NULL GROUP BY pays HAVING n >= ?", (SEUIL_BIEN_RECONNU, ident, MIN_MANCHES_PAYS)):
            pays.append({"pays": r["pays"], "manches": r["n"], "taux": r["ok"] / r["n"]})
        from . import fiches
        for p in pays:
            p["nom"] = fiches.fiche(p["pays"])["nom"]
        mieux = sorted(pays, key=lambda p: (-p["taux"], -p["manches"]))[:3]
        moins = sorted(pays, key=lambda p: (p["taux"], -p["manches"]))[:3]
        historique = [{"mode": r["mode"], "carte": _nom_carte(r["carte"]), "total": r["total"], "date": r["cree_le"]}
                      for r in c.execute("SELECT mode, carte, total, cree_le FROM parties WHERE compte=? AND statut='terminee' "
                                         "ORDER BY cree_le DESC LIMIT 20", (ident,))]
        obtenus = {r["code"]: r["obtenu_le"] for r in c.execute("SELECT code, obtenu_le FROM succes WHERE identifiant=?", (ident,))}
    return {
        "compte": {"identifiant": ident, "pseudo": compte["pseudo"]},
        "niveau": progression.etat_niveau(xp),
        "parties_jouees": jouees,
        "meilleurs_scores": meilleurs,
        "distance_moyenne_m": moyenne,
        "records_serie": records,
        "pays_mieux_reconnus": mieux,
        "pays_moins_bien_reconnus": moins,
        "historique": historique,
        "succes": [{"code": k, "nom": v[0], "description": v[1], "obtenu": k in obtenus} for k, v in progression.SUCCES.items()],
    }


def classements(carte_id: str) -> dict:
    """Classements entre comptes (les invités n'y figurent pas)."""
    jour = f"jour-{horloge.jour_paris()}"
    with base.connexion() as c:
        par_carte = [{"pseudo": r["pseudo"], "total": r["t"]} for r in c.execute(
            "SELECT k.pseudo pseudo, MAX(p.total) t FROM parties p JOIN comptes k ON k.identifiant=p.compte "
            "WHERE p.carte=? AND p.mode='classique' AND p.statut='terminee' GROUP BY p.compte ORDER BY t DESC, p.cree_le LIMIT 20",
            (carte_id,))]
        du_jour = [{"pseudo": r["pseudo"], "total": r["total"]} for r in c.execute(
            "SELECT k.pseudo pseudo, p.total total FROM parties p JOIN comptes k ON k.identifiant=p.compte "
            "WHERE p.defi_id=? AND p.statut='terminee' ORDER BY p.total DESC, p.cree_le LIMIT 20", (jour,))]
        serie = [{"pseudo": r["pseudo"], "total": r["valeur"]} for r in c.execute(
            "SELECT k.pseudo pseudo, r.valeur valeur FROM records r JOIN comptes k ON r.joueur_id = 'c:' || k.identifiant "
            "WHERE r.cle=? ORDER BY r.valeur DESC LIMIT 20", (f"serie:{carte_id}",))]
    return {"carte": carte_id, "par_carte": par_carte, "defi_du_jour": du_jour, "serie": serie}
