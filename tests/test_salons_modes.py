"""Étape 3, lot 2 : Duel, équipes 2 contre 2, Batailles royales (critères 23, 24, 25)."""
import asyncio

import pytest

from serveur import salons
from serveur.jeu import cartes, score
from serveur.jeu.moteur import ErreurJeu
from tests.test_salons import Faux, agir, entrer, nouveau, propre, run, _tick  # noqa: F401  (fixture « propre »)

GENEVE = (46.2044, 6.1432)        # en Suisse : un « mauvais pays » pour un lieu de la Drôme-Ardèche
MER = (0.0, -30.0)


def salle(mode, n, **kw):
    s = nouveau(**kw)
    gens = [entrer(s, c) for c in ["hote", "b", "c", "d", "e"][:n]]
    agir(s, gens[0][0], t="regler", mode=mode)
    return s, gens


def lieu(s):
    return s.lieux[s.numero - 1]


def exact(s, m):
    agir(s, m, t="repondre", lat=lieu(s)["lat"], lon=lieu(s)["lon"])


def loin(s, m):
    agir(s, m, t="repondre", lat=MER[0], lon=MER[1])


# ------------------------------------------------------------ réglages communs
def test_changer_de_mode_et_de_role():
    s, [(h, _), (b, _), (c, _), (d, _), (e, _)] = salle("amis", 5)
    with pytest.raises(ErreurJeu) as err:
        agir(s, h, t="regler", mode="duel")                 # 5 joueurs : trop pour un Duel
    assert err.value.statut == 409
    agir(s, h, t="role", id=e.id, role="spectateur")        # l'hôte fait passer quelqu'un en spectateur
    agir(s, h, t="role", id=d.id, role="spectateur")
    agir(s, h, t="regler", mode="duel")
    assert s.mode == "duel"
    with pytest.raises(ErreurJeu):
        agir(s, b, t="role", id=c.id, role="spectateur")    # un simple joueur ne décide que pour lui
    agir(s, c, t="role", role="spectateur")
    with pytest.raises(ErreurJeu):
        agir(s, h, t="regler", mode="n_importe_quoi")
    assert s.joueurs() == [h, b]


def test_minimums_de_joueurs():
    s, [(h, _), (b, _)] = salle("br_distance", 2)
    with pytest.raises(ErreurJeu):
        agir(s, h, t="lancer")                              # il en faut 3
    s, gens = salle("duel", 3)
    with pytest.raises(ErreurJeu) as err:
        agir(s, gens[0][0], t="lancer")                     # un Duel : 2 ou 4
    assert "Duel" in err.value.message


# ------------------------------------------------------------ critère 23 : Duel
def test_duel_degats_multiplicateur_et_fin():
    s, [(h, fh), (b, fb)] = salle("duel", 2)
    agir(s, h, t="lancer")
    e = fh.dernier_etat()
    assert e["duel"]["variante"] == "1v1" and [c["pv"] for c in e["duel"]["cotes"]] == [6000, 6000]
    assert s._multiplicateur(1) == s._multiplicateur(4) == 1.0
    assert s._multiplicateur(5) == 1.5 and s._multiplicateur(6) == 2.0 and s._multiplicateur(8) == 3.0
    # égalité parfaite : personne ne perd rien
    exact(s, h); exact(s, b)
    r = fh.dernier_etat()
    assert r["phase"] == "resultat" and r["resultat"]["duel"]["perdant"] is None and r["resultat"]["duel"]["degats"] == 0
    assert [c["pv"] for c in r["duel"]["cotes"]] == [6000, 6000]
    agir(s, h, t="suivante")
    # le moins précis perd l'écart de score × 1
    exact(s, h); agir(s, b, t="repondre", lat=lieu(s)["lat"] + 0.3, lon=lieu(s)["lon"])
    diag = cartes.carte("drome-ardeche")["diagonale_km"]
    pts_b = score.points(s.resultat["reponses"][1]["distance_m"], diag)
    d = fh.dernier_etat()["resultat"]["duel"]
    assert d["degats"] == 5000 - pts_b and d["perdant"] == b.cle and d["multiplicateur"] == 1.0
    pv_b = 6000 - d["degats"]
    assert {c["id"]: c["pv"] for c in fh.dernier_etat()["duel"]["cotes"]}[b.cle] == pv_b
    # on continue jusqu'à 0 : la partie s'arrête, l'autre gagne
    while s.phase != "fin":
        agir(s, h, t="suivante"); exact(s, h); loin(s, b)
    fin = fb.dernier_etat()
    assert fin["fin_partie"]["gagnants"] == [h.id] and fin["fin_partie"]["classement"][0]["pseudo"] == "hote"
    assert min(c["pv"] for c in fin["duel"]["cotes"]) == 0


def test_duel_quinze_secondes_apres_la_premiere_reponse(temps):
    s, [(h, fh), (b, fb)] = salle("duel", 2)
    agir(s, h, t="lancer")
    assert fb.dernier_etat()["manche"]["temps_restant"] is None and not fb.dernier_etat()["manche"]["compte_a_rebours"]
    exact(s, h)
    m = s.etat_pour(b)["manche"]
    assert m["compte_a_rebours"] and 14 < m["temps_restant"] <= 15
    temps.t += 15.5
    assert run(_tick(s)) is False and s.phase == "manche"        # courte marge (1 s) pour les réponses en vol
    temps.t += 1
    assert run(_tick(s)) is True and s.phase == "resultat"
    assert fh.dernier_etat()["resultat"]["duel"]["perdant"] == b.cle      # sans réponse = 0 point


def test_duel_abandon_donne_la_victoire(temps):
    s, [(h, fh), (b, fb)] = salle("duel", 2)
    agir(s, h, t="lancer")
    s.deconnecter(b, fb)
    temps.t += 70
    run(_tick(s))
    assert s.phase == "fin" and s.gagnants == [h.id]


# ------------------------------------------------------------ critère 24 : équipes 2 contre 2
def test_equipes_la_meilleure_reponse_compte():
    s, [(h, fh), (b, _), (c, _), (d, _)] = salle("duel", 4)
    assert [s.equipes[m.cle] for m in (h, b, c, d)] == ["A", "B", "A", "B"]
    agir(s, h, t="equipe", id=c.id, equipe="B")
    with pytest.raises(ErreurJeu):
        agir(s, h, t="lancer")                              # 1 contre 3 : refusé
    agir(s, h, t="equipe", id=c.id, equipe="A")
    with pytest.raises(ErreurJeu):
        agir(s, b, t="equipe", id=c.id, equipe="B")         # seul l'hôte compose les équipes
    agir(s, h, t="lancer")
    assert fh.dernier_etat()["duel"]["variante"] == "2v2"
    exact(s, h); loin(s, c)                                  # équipe A : un exact, un très loin → 5000
    loin(s, b); loin(s, d)                                   # équipe B : deux très loin
    pts_b = max(l["points"] for l in s.resultat["reponses"] if l["equipe"] == "B")
    duel = fh.dernier_etat()["resultat"]["duel"]
    cotes = {c_["id"]: c_ for c_ in duel["cotes"]}
    assert cotes["A"]["points"] == 5000 and cotes["B"]["points"] == pts_b
    assert duel["perdant"] == "B" and duel["degats"] == 5000 - pts_b
    assert cotes["A"]["pv"] == 6000 and cotes["B"]["pv"] == 6000 - duel["degats"]
    assert [c_["nom"] for c_ in fh.dernier_etat()["duel"]["cotes"]] == ["Équipe A", "Équipe B"]


# ------------------------------------------------------------ critère 25 : Bataille royale « distance »
def test_br_distance_le_plus_loin_est_elimine():
    s, [(h, fh), (b, fb), (c, fc)] = salle("br_distance", 3)
    agir(s, h, t="lancer")
    exact(s, h)
    agir(s, b, t="repondre", lat=lieu(s)["lat"] + 0.2, lon=lieu(s)["lon"])
    loin(s, c)
    r = fb.dernier_etat()
    assert r["phase"] == "resultat" and r["resultat"]["elimine"] == c.id
    assert [l["pseudo"] for l in r["resultat"]["reponses"]] == ["hote", "b", "c"] and r["resultat"]["reponses"][2]["elimine"]
    assert fc.dernier_etat()["moi"]["elimine"] and not fc.dernier_etat()["moi"]["hote"]
    agir(s, h, t="suivante")
    with pytest.raises(ErreurJeu):
        loin(s, c)                                           # l'éliminé regarde, il ne joue plus
    assert fc.dernier_etat()["manche"]["numero"] == 2        # …mais il voit la manche
    agir(s, c, t="chat", texte="je regarde")                 # …et peut écrire
    loin(s, h)                                               # h et b répondent ; b est plus près
    exact(s, b)
    fin = fc.dernier_etat()
    assert fin["phase"] == "fin" and fin["fin_partie"]["gagnants"] == [b.id]
    assert [(x["pseudo"], x["detail"]) for x in fin["fin_partie"]["classement"]] == [
        ("b", "vainqueur"), ("hote", "éliminé à la manche 2"), ("c", "éliminé à la manche 1")]


def test_br_distance_sans_reponse_est_elimine_en_premier(temps):
    s, [(h, fh), (b, _), (c, _)] = salle("br_distance", 3, chrono=10)
    agir(s, h, t="lancer")
    loin(s, h); exact(s, b)                                  # c ne répond pas
    temps.t += 14
    run(_tick(s))
    assert s.resultat["elimine"] == c.id


def test_br_distance_un_depart_compte_comme_elimination(temps):
    s, [(h, fh), (b, fb), (c, _)] = salle("br_distance", 3)
    agir(s, h, t="lancer")
    s.deconnecter(b, fb)
    temps.t += 70
    run(_tick(s))
    assert [x for x, _ in s.elimines] == ["b"] and s.phase == "manche"
    exact(s, h); loin(s, c)                                  # il ne reste que h et c
    assert s.phase == "fin" and s.gagnants == [h.id]


# ------------------------------------------------------------ critère 25 : Bataille royale « pays »
def mauvais(s, m):
    agir(s, m, t="repondre", lat=GENEVE[0], lon=GENEVE[1])


def bon(s, m):
    agir(s, m, t="repondre", lat=lieu(s)["lat"], lon=lieu(s)["lon"])


def test_br_pays_trois_essais_trois_vies():
    s, [(h, fh), (b, fb), (c, fc)] = salle("br_pays", 3)
    agir(s, h, t="lancer")
    assert fh.dernier_etat()["manche"]["essais"] == {"restants": 3, "trouve": False, "dernier": None}
    mauvais(s, b)
    e = fb.dernier_etat()["manche"]["essais"]
    assert e["restants"] == 2 and e["dernier"] == {"pays": "Suisse", "juste": False}
    agir(s, b, t="repondre", lat=MER[0], lon=MER[1])
    assert fb.dernier_etat()["manche"]["essais"]["dernier"]["pays"] is None      # en mer
    assert s.phase == "manche" and not fb.dernier_etat()["manche"]["a_repondu"]
    mauvais(s, b)                                            # 3ᵉ essai raté : b a fini la manche
    assert fb.dernier_etat()["manche"]["a_repondu"]
    with pytest.raises(ErreurJeu):
        mauvais(s, b)
    bon(s, h)                                                # h trouve du premier coup
    assert s.phase == "manche"
    mauvais(s, c); mauvais(s, c); bon(s, c)                  # c trouve au 3ᵉ essai
    r = fh.dernier_etat()
    assert r["phase"] == "resultat"
    vies = {l["pseudo"]: l["vies"] for l in r["resultat"]["reponses"]}
    assert vies == {"hote": 3, "b": 2, "c": 3}
    assert {l["pseudo"]: (l["trouve"], l["essais"]) for l in r["resultat"]["reponses"]} == {
        "hote": (True, 1), "b": (False, 3), "c": (True, 3)}


def test_br_pays_pas_de_pays_avant_la_fin():
    s, [(h, fh), (b, fb), (c, _)] = salle("br_pays", 3)
    agir(s, h, t="lancer")
    assert "pays" not in fb.dernier_etat()["manche"] and "lon" not in str(fb.dernier_etat()["manche"])
    assert "lat" not in str(fb.dernier_etat()["manche"]) and str(lieu(s)["lat"]) not in str(fb.dernier_etat())
    assert fb.dernier_etat()["resultat"] is None


def test_br_pays_elimination_et_victoire():
    s, [(h, fh), (b, fb), (c, fc)] = salle("br_pays", 3)
    agir(s, h, t="lancer")
    for manche in range(3):                                  # b rate trois manches de suite : plus de vies
        bon(s, h); bon(s, c)
        for _ in range(3):
            mauvais(s, b)
        if s.phase == "resultat":
            agir(s, h, t="suivante")
    assert [x for x, _ in s.elimines] == ["b"] and fb.dernier_etat()["moi"]["elimine"]
    assert s.phase == "manche" and s.numero == 4
    for _ in range(3):                                       # h et c : c rate trois fois de suite
        bon(s, h)
        for _ in range(3):
            mauvais(s, c)
        if s.phase == "resultat":
            agir(s, h, t="suivante")
    assert s.phase == "fin" and s.gagnants == [h.id]
    cl = [(x["pseudo"], x["detail"]) for x in fh.dernier_etat()["fin_partie"]["classement"]]
    assert cl[0] == ("hote", "vainqueur") and [x[0] for x in cl] == ["hote", "c", "b"]


def test_br_pays_egalite_si_tous_perdent_leur_derniere_vie():
    s, gens = salle("br_pays", 3)
    h = gens[0][0]
    agir(s, h, t="lancer")
    for m in s.participants:
        s.vies[m] = 1
    for m, _ in gens:
        for _ in range(3):
            mauvais(s, m)
    assert s.phase == "fin" and len(s.gagnants) == 3         # égalité plutôt qu'une partie sans vainqueur


def test_br_pays_chrono_les_non_trouves_perdent_une_vie(temps):
    s, [(h, fh), (b, _), (c, _)] = salle("br_pays", 3, chrono=10)
    agir(s, h, t="lancer")
    bon(s, h); mauvais(s, b)                                 # b n'a pas fini, c n'a rien tenté
    temps.t += 14
    run(_tick(s))
    assert s.phase == "resultat" and s.vies == {h.cle: 3, b.cle: 2, c.cle: 2}


def test_rejouer_remet_le_mode_a_zero():
    s, [(h, fh), (b, _)] = salle("duel", 2)
    agir(s, h, t="lancer")
    while s.phase != "fin":
        exact(s, h); loin(s, b)
        if s.phase == "resultat":
            agir(s, h, t="suivante")
    agir(s, h, t="rejouer")
    e = fh.dernier_etat()
    assert e["phase"] == "attente" and e["duel"] is None and e["mode"] == "duel" and e["resultat"] is None
    agir(s, h, t="lancer")
    assert [c["pv"] for c in fh.dernier_etat()["duel"]["cotes"]] == [6000, 6000]


def test_equipes_un_depart_en_pleine_partie_ne_casse_rien(temps):
    s, [(h, fh), (b, fb), (c, fc), (d, fd)] = salle("duel", 4)
    agir(s, h, t="lancer")
    agir(s, h, t="exclure", id=d.id)                         # exclusion en manche : l'équipe B n'a plus que b
    assert s.phase == "manche" and "d" not in s.membres
    exact(s, h); exact(s, c); loin(s, b)
    r = fh.dernier_etat()
    assert r["phase"] == "resultat" and r["resultat"]["duel"]["perdant"] == "B"
    assert [c_["membres"] for c_ in r["duel"]["cotes"]][1] == [b.id, d.id]     # le côté garde ses deux noms
    agir(s, h, t="suivante")
    s.deconnecter(b, fb)
    temps.t += 70
    run(_tick(s))                                            # b part à son tour : l'équipe B n'existe plus
    assert s.phase == "fin" and set(s.gagnants) == {h.id, c.id}
    assert fc.dernier_etat()["fin_partie"]["classement"][0]["pseudo"].startswith("Équipe A")


def test_plus_de_lieux_la_partie_s_arrete_sans_rejouer_un_lieu(monkeypatch):
    s, [(h, fh), (b, _)] = salle("duel", 2)
    n = len(salons.lieux_mod.charger(s.carte_id))
    agir(s, h, t="lancer")
    vus = [lieu(s)["id"]]
    for _ in range(n + 2):
        if s.phase == "fin":
            break
        exact(s, h); agir(s, b, t="repondre", lat=lieu(s)["lat"] + 0.01, lon=lieu(s)["lon"])   # score voisin : peu de dégâts
        if s.phase == "resultat":
            agir(s, h, t="suivante")
            if s.phase == "manche":
                vus.append(lieu(s)["id"])
    assert len(vus) == len(set(vus))                         # jamais deux fois le même lieu
    if s.phase == "fin":
        assert s.gagnants                                    # un vainqueur, ou une égalité déclarée
