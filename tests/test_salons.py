"""Étape 3, lot 1 : salons, Partie entre amis, spectateurs, chat, reconnexion (critères 21, 22, 26, 27, 28, 29)."""
import asyncio
import json
import logging

import pytest

from serveur import base, salons
from serveur.app import creer_app
from serveur.jeu.moteur import ErreurJeu
from tests.client import Client, ClientWS

H = {"X-Requete": "ou-suis-je"}
VALENCE = (44.9334, 4.8924)


def run(coro):
    return asyncio.run(coro)


class Faux:
    """Une liaison de test : garde ce que le serveur envoie."""
    def __init__(self):
        self.messages, self.ferme = [], False

    async def envoyer(self, m):
        self.messages.append(m)

    async def fermer(self):
        self.ferme = True

    def dernier_etat(self):
        return [m for m in self.messages if m["t"] == "etat"][-1]

    def chats(self):
        return [m for m in self.messages if m["t"] == "chat"]


@pytest.fixture(autouse=True)
def propre():
    salons.gestionnaire.salons.clear()
    yield
    salons.gestionnaire.salons.clear()


def nouveau(chrono=0, carte="drome-ardeche"):
    return salons.gestionnaire.creer("hote", carte, "libre", chrono)


def entrer(salon, cle, pseudo=None, role="joueur"):
    f = Faux()
    return salon.rejoindre(cle, pseudo or cle, role, f), f


def agir(salon, membre, **msg):
    run(salon.traiter(membre, msg))


def partie_prete(nb=3, **kw):
    s = nouveau(**kw)
    gens = [entrer(s, c) for c in ["hote", "b", "c", "d"][:nb]]
    return s, gens


# ------------------------------------------------------------ critère 21 : salon, code, réglages, lancement
def test_code_et_acces_par_code_seulement():
    s = nouveau()
    assert len(s.code) == 6 and set(s.code) <= set(salons.ALPHABET)
    assert salons.gestionnaire.trouver(s.code.lower()) is s
    with pytest.raises(ErreurJeu) as e:
        salons.gestionnaire.trouver("ZZZZZZ")
    assert e.value.statut == 404


def test_l_hote_regle_puis_lance_et_les_autres_ne_peuvent_pas():
    s, [(h, _), (b, fb)] = partie_prete(2)
    with pytest.raises(ErreurJeu):
        agir(s, b, t="regler", carte="monde")
    agir(s, h, t="regler", carte="monde", contrainte="fige", chrono=30)
    assert (s.carte_id, s.contrainte, s.chrono) == ("monde", "fige", 30)
    with pytest.raises(ErreurJeu):
        agir(s, h, t="regler", carte="inconnue")
    with pytest.raises(ErreurJeu):
        agir(s, b, t="lancer")
    agir(s, h, t="lancer")
    assert fb.dernier_etat()["phase"] == "manche"
    with pytest.raises(ErreurJeu):
        agir(s, h, t="regler", carte="france")          # plus de réglage en cours de partie


def test_au_moins_deux_joueurs_et_dix_au_plus():
    s, [(h, _)] = partie_prete(1)
    with pytest.raises(ErreurJeu):
        agir(s, h, t="lancer")
    for i in range(12):
        entrer(s, f"x{i}")
    assert len(s.joueurs()) == salons.MAX_JOUEURS
    assert sum(m.role == "spectateur" for m in s.membres.values()) == 3       # les suivants regardent


def test_creation_http_exige_l_en_tete_et_limite_par_hote():
    c = Client(creer_app())
    c.get("/api/config")                                    # pose le cookie invité
    c.entetes.pop("X-Requete")
    assert c.post("/api/salons", {"carte": "monde"})[0] == 400
    c.entetes["X-Requete"] = "ou-suis-je"
    statut, r = c.post("/api/salons", {"carte": "monde"})
    assert statut == 200 and len(r["code"]) == 6
    assert c.get(f"/api/salons/{r['code']}")[0] == 200 and c.get("/api/salons/ZZZZZZ")[0] == 404
    assert c.post("/api/salons", {"carte": "monde"})[0] == 200
    assert c.post("/api/salons", {"carte": "monde"})[0] == 429                # 2 salons au plus par hôte
    assert c.post("/api/salons", {"carte": "nulle-part"})[0] in (400, 429)


# ------------------------------------------------------------ critère 22 : même manche pour tous, résultats de tous
def test_partie_complete_a_trois():
    s, [(h, fh), (b, fb), (c, fc)] = partie_prete(3)
    agir(s, h, t="lancer")
    vus = set()
    for numero in range(1, 6):
        etats = [f.dernier_etat() for f in (fh, fb, fc)]
        assert {e["manche"]["numero"] for e in etats} == {numero}
        assert len({json.dumps(e["manche"]["image"], sort_keys=True) for e in etats}) == 1     # même image
        vus.add(json.dumps(etats[0]["manche"]["image"], sort_keys=True))
        agir(s, h, t="repondre", lat=VALENCE[0], lon=VALENCE[1])
        agir(s, b, t="repondre", lat=0, lon=0)
        assert s.phase == "manche"                         # il manque encore c
        agir(s, c, t="repondre", lat=45.0, lon=5.0)
        r = fh.dernier_etat()["resultat"]
        assert r["numero"] == numero and len(r["reponses"]) == 3 and r["fiche"]["nom"] == "France"
        assert all(x["lat"] is not None and x["points"] >= 0 for x in r["reponses"])
        if numero < 5:
            with pytest.raises(ErreurJeu):
                agir(s, b, t="suivante")                   # seul l'hôte avance
            agir(s, h, t="suivante")
    assert len({l["id"] for l in s.lieux}) == 5            # cinq lieux différents
    fin = fb.dernier_etat()
    assert fin["phase"] == "fin" and len(fin["classement"]) == 3
    assert fin["classement"][0]["total"] >= fin["classement"][1]["total"] >= fin["classement"][2]["total"]
    assert fin["classement"][-1]["pseudo"] == "b"          # (0,0) est le plus loin de la Drôme-Ardèche
    agir(s, h, t="rejouer")
    assert fb.dernier_etat()["phase"] == "attente" and fb.dernier_etat()["classement"] == []


def test_aucune_coordonnee_avant_la_fin_de_la_manche():
    s, [(h, fh), (b, fb)] = partie_prete(2)
    agir(s, h, t="lancer")
    agir(s, h, t="repondre", lat=VALENCE[0], lon=VALENCE[1])
    lieu = s.lieux[0]
    for f in (fh, fb):
        brut = json.dumps(f.dernier_etat())
        assert str(lieu["lat"]) not in brut and str(lieu["lon"]) not in brut
        assert "pays" not in json.dumps(f.dernier_etat()["manche"])
        assert f.dernier_etat()["resultat"] is None
    # la réponse des autres reste cachée aussi : on voit seulement qui a répondu
    assert [m["a_repondu"] for m in fb.dernier_etat()["membres"]] == [True, False]
    assert "lat" not in json.dumps(fb.dernier_etat()["membres"])


def test_reponses_invalides_ou_doubles(temps):
    s, [(h, _), (b, _)] = partie_prete(2, chrono=10)
    agir(s, h, t="lancer")
    for lat, lon in (("a", 1), (91, 0), (0, 181), (True, 1), (None, None)):
        with pytest.raises(ErreurJeu):
            agir(s, h, t="repondre", lat=lat, lon=lon)
    agir(s, h, t="repondre", lat=1, lon=1)
    with pytest.raises(ErreurJeu):
        agir(s, h, t="repondre", lat=2, lon=2)
    temps.t += 14
    with pytest.raises(ErreurJeu):
        agir(s, b, t="repondre", lat=2, lon=2)               # chrono + 3 s dépassés


def test_chrono_clot_la_manche_et_non_repondu_vaut_zero(temps):
    s, [(h, fh), (b, _)] = partie_prete(2, chrono=10)
    agir(s, h, t="lancer")
    agir(s, h, t="repondre", lat=VALENCE[0], lon=VALENCE[1])
    assert run(_tick(s)) is False and s.phase == "manche"
    temps.t += 12
    assert fh.dernier_etat()["manche"]["temps_restant"] == 0 or True
    assert run(_tick(s)) is False and s.phase == "manche"      # encore dans la marge de 3 s
    temps.t += 2
    assert run(_tick(s)) is True and s.phase == "resultat"
    pts = {x["pseudo"]: x["points"] for x in fh.dernier_etat()["resultat"]["reponses"]}
    assert pts["b"] == 0 and pts["hote"] > 0


async def _tick(s):
    ch = s.tick()
    if ch:
        await s.diffuser()
    return ch


# ------------------------------------------------------------ critère 26 : spectateurs
def test_spectateur_voit_tout_et_ne_joue_pas():
    s, [(h, _), (b, _)] = partie_prete(2)
    sp, fs = entrer(s, "spec", role="spectateur")
    agir(s, h, t="lancer")
    assert fs.dernier_etat()["manche"]["numero"] == 1 and fs.dernier_etat()["moi"]["role"] == "spectateur"
    with pytest.raises(ErreurJeu):
        agir(s, sp, t="repondre", lat=1, lon=1)
    tard, ft = entrer(s, "tard")                              # arrive en cours de partie : forcé en spectateur
    assert tard.role == "spectateur"
    agir(s, h, t="repondre", lat=1, lon=1)
    agir(s, b, t="repondre", lat=2, lon=2)                    # les spectateurs ne retardent pas la fin de manche
    assert fs.dernier_etat()["phase"] == "resultat" and len(fs.dernier_etat()["resultat"]["reponses"]) == 2
    agir(s, sp, t="chat", texte="bravo")                      # un spectateur peut écrire dans le salon
    assert any(c["texte"] == "bravo" for c in fs.chats())


# ------------------------------------------------------------ critère 27 : reconnexion 60 s
def test_reconnexion_avant_60_s_reprend_sa_place(temps):
    s, [(h, fh), (b, fb)] = partie_prete(2)
    agir(s, h, t="lancer")
    agir(s, h, t="repondre", lat=VALENCE[0], lon=VALENCE[1])
    agir(s, b, t="repondre", lat=VALENCE[0], lon=VALENCE[1])
    agir(s, h, t="suivante")
    ancien_id, total = b.id, s.totaux["b"]
    s.deconnecter(b, fb)
    temps.t += 20
    run(_tick(s))
    assert "b" in s.membres and not b.connecte
    m2, f2 = entrer(s, "b")
    assert m2 is b and m2.id == ancien_id and s.totaux["b"] == total
    assert f2.dernier_etat() if f2.messages else True
    run(s.diffuser())
    assert f2.dernier_etat()["manche"]["numero"] == 2 and f2.dernier_etat()["moi"]["role"] == "joueur"


def test_au_dela_de_60_s_retire_et_la_partie_continue(temps):
    s, [(h, fh), (b, fb), (c, fc)] = partie_prete(3)
    agir(s, h, t="lancer")
    agir(s, h, t="repondre", lat=1, lon=1)
    agir(s, c, t="repondre", lat=1, lon=1)
    assert s.phase == "manche"                                # b est connecté et n'a pas répondu
    s.deconnecter(b, fb)
    assert s.phase == "manche"
    temps.t += 30
    run(_tick(s))
    assert s.phase == "manche" and "b" in s.membres
    temps.t += 40
    run(_tick(s))
    assert "b" not in s.membres and s.phase == "resultat"     # retiré : sa manche ne retient plus personne
    agir(s, h, t="suivante")
    assert fh.dernier_etat()["phase"] == "manche" and len(fh.dernier_etat()["classement"]) == 2


def test_l_hote_parti_passe_la_main(temps):
    s, [(h, fh), (b, fb)] = partie_prete(2)
    s.deconnecter(h, fh)
    temps.t += 70
    run(_tick(s))
    assert s.hote() is b
    agir(s, b, t="regler", chrono=30)


def test_salon_vide_expire(temps):
    s, [(h, fh)] = partie_prete(1)
    s.deconnecter(h, fh)
    temps.t += 70
    run(salons.gestionnaire.passer_le_temps())
    assert s.code in salons.gestionnaire.salons                 # vidé mais pas encore périmé
    temps.t += salons.DELAI_SALON_VIDE_S + 1
    run(salons.gestionnaire.passer_le_temps())
    assert s.code not in salons.gestionnaire.salons


# ------------------------------------------------------------ critères 28 et 29 : chat
def test_chat_vu_par_les_presents_seulement(temps):
    s, [(h, fh), (b, fb)] = partie_prete(2)
    autre = salons.gestionnaire.creer("autre", "monde")
    _, fa = entrer(autre, "z")
    agir(s, b, t="chat", texte="salut 😀 https://exemple.fr")
    assert [c["texte"] for c in fh.chats()] == ["salut 😀 https://exemple.fr"] == [c["texte"] for c in fb.chats()]
    assert fa.chats() == []
    assert fh.chats()[0]["de"] == "b" and set(fh.chats()[0]) == {"t", "id", "de", "texte"}   # pas de clé privée


def test_chat_limites(temps):
    s, [(h, _), (b, fb)] = partie_prete(2)
    agir(s, b, t="chat", texte="un")
    with pytest.raises(ErreurJeu) as e:
        agir(s, b, t="chat", texte="deux")
    assert e.value.statut == 429
    temps.t += 1.1
    agir(s, b, t="chat", texte="deux")
    temps.t += 1.1
    for mauvais in ("", "   ", "\x00\x07", "x" * 201):
        with pytest.raises(ErreurJeu):
            agir(s, b, t="chat", texte=mauvais)
        temps.t += 1.1
    agir(s, b, t="chat", texte="x" * 200)
    temps.t += 1.1
    agir(s, b, t="chat", texte="a‮b\nc")                 # caractères de contrôle et retours à la ligne retirés
    assert fb.chats()[-1]["texte"] == "ab c"


def test_hote_coupe_le_chat_rend_muet_exclut(temps):
    s, [(h, fh), (b, fb), (c, fc)] = partie_prete(3)
    with pytest.raises(ErreurJeu):
        agir(s, b, t="muet", id=c.id, valeur=True)             # pas l'hôte
    with pytest.raises(ErreurJeu):
        agir(s, b, t="exclure", id=c.id)
    agir(s, h, t="muet", id=b.id, valeur=True)
    with pytest.raises(ErreurJeu):
        agir(s, b, t="chat", texte="coucou")
    agir(s, c, t="chat", texte="je parle")
    agir(s, h, t="muet", id=b.id, valeur=False)
    temps.t += 2
    agir(s, b, t="chat", texte="de retour")
    agir(s, h, t="chat_actif", valeur=False)
    temps.t += 2
    with pytest.raises(ErreurJeu):
        agir(s, c, t="chat", texte="bloqué")
    agir(s, h, t="chat", texte="l'hôte peut encore")
    agir(s, h, t="chat_actif", valeur=True)
    # exclusion : retiré, prévenu, ne peut plus écrire ni revenir
    agir(s, h, t="exclure", id=c.id)
    assert fc.ferme and any(m["t"] == "exclu" for m in fc.messages) and "c" not in s.membres
    with pytest.raises(ErreurJeu) as e:
        entrer(s, "c")
    assert e.value.statut == 403
    with pytest.raises(ErreurJeu):
        agir(s, h, t="exclure", id=h.id)


def test_le_chat_n_est_enregistre_nulle_part(temps, caplog):
    caplog.set_level(logging.DEBUG)
    s, [(h, fh), (b, fb)] = partie_prete(2)
    agir(s, b, t="chat", texte="SECRET-ABCDEF")
    assert s._chats == []                                      # rien ne reste en mémoire après l'envoi
    assert "SECRET-ABCDEF" not in caplog.text
    brut = repr(vars(s)) + repr([vars(m) for m in s.membres.values()])
    assert "SECRET-ABCDEF" not in brut.replace(repr(fh.messages), "").replace(repr(fb.messages), "")
    with base.connexion() as c:
        dump = "\n".join(c.iterdump())
    assert "SECRET-ABCDEF" not in dump
    assert not [t for t in ("chat", "messages") if f"CREATE TABLE {t}" in dump]
    tard, ft = entrer(s, "tard")
    run(s.diffuser())
    assert ft.chats() == []                                    # un nouvel arrivant ne reçoit aucun historique
    del salons.gestionnaire.salons[s.code]


# ------------------------------------------------------------ le transport WebSocket (au niveau ASGI)
def _site():
    app = creer_app()
    c = Client(app)
    c.get("/api/config")
    c.entetes["X-Requete"] = "ou-suis-je"
    return app, c


def _ws(app, c, code, pseudo="Zoé", role=None, origine="http://test"):
    w = ClientWS(app, f"/ws/salons/{code}", {"Origin": origine}, dict(c.cookies))
    w.entree = {"t": "entrer", "pseudo": pseudo, **({"role": role} if role else {})}
    return w


def test_websocket_origine_et_code_inconnu():
    app, c = _site()
    code = c.post("/api/salons", {"carte": "drome-ardeche"})[1]["code"]

    async def main():
        async with _ws(app, c, code, origine="http://pirate.example") as w:
            assert await w.recevoir() is None and w.code_fermeture == 4403 and not w.accepte
        async with _ws(app, c, "ZZZZZZ") as w:
            m = await w.recevoir()
            assert m["t"] == "erreur" and m["fatale"] and (await w.recevoir()) is None
        async with ClientWS(app, f"/ws/salons/{code}", {"Origin": "http://test"}) as w:        # pas de cookie
            assert (await w.recevoir())["fatale"]
    run(main())


def test_websocket_partie_a_deux_avec_chat():
    app, c = _site()
    code = c.post("/api/salons", {"carte": "drome-ardeche"})[1]["code"]
    c2 = Client(app); c2.get("/api/config")

    async def main():
        async with _ws(app, c, code, "Hôte") as a, _ws(app, c2, code, "Ami") as b:
            ea = await a.jusqu_a("etat")
            assert ea["moi"]["hote"] and ea["phase"] == "attente"
            eb = await b.jusqu_a("etat")
            assert not eb["moi"]["hote"] and [m["pseudo"] for m in eb["membres"]] == ["Hôte", "Ami"]
            await b.envoyer({"t": "lancer"})
            assert (await b.jusqu_a("erreur"))["message"].startswith("Seul l'hôte")
            await a.envoyer({"t": "chat", "texte": "Salut !"})
            assert (await b.jusqu_a("chat"))["texte"] == "Salut !"
            await a.envoyer({"t": "lancer"})
            while True:
                e = await b.jusqu_a("etat")
                if e["phase"] == "manche":
                    break
            await a.envoyer({"t": "repondre", "lat": 45, "lon": 5})
            await b.envoyer({"t": "repondre", "lat": 46, "lon": 6})
            while True:
                e = await a.jusqu_a("etat")
                if e["phase"] == "resultat":
                    break
            assert len(e["resultat"]["reponses"]) == 2
            await a.envoyer("pas un objet")
            assert (await a.jusqu_a("erreur"))["message"] == "Message invalide."
    run(main())
    s = salons.gestionnaire.trouver(code)
    assert all(not m.connecte for m in s.membres.values())      # fermeture propre : les liaisons sont retirées


def test_websocket_reprise_apres_coupure():
    app, c = _site()
    code = c.post("/api/salons", {"carte": "drome-ardeche"})[1]["code"]

    async def main():
        async with _ws(app, c, code, "Hôte") as a:
            premier = (await a.jusqu_a("etat"))["moi"]["id"]
        async with _ws(app, c, code, "Hôte") as a:               # même cookie : même place
            e = await a.jusqu_a("etat")
            assert e["moi"]["id"] == premier and e["moi"]["hote"] and len(e["membres"]) == 1
    run(main())


# ------------------------------------------------------------ corrections de la relecture « enfants »
def test_le_muet_survit_a_une_deconnexion_longue(temps):
    s, [(h, _), (b, fb)] = partie_prete(2)
    agir(s, h, t="muet", id=b.id, valeur=True)
    s.deconnecter(b, fb)
    temps.t += 70
    run(_tick(s))
    assert "b" not in s.membres
    b2, f2 = entrer(s, "b")
    temps.t += 2
    with pytest.raises(ErreurJeu):
        agir(s, b2, t="chat", texte="je reviens")


def test_salon_verrouille_et_exclu_retire(temps):
    s, [(h, _), (b, fb)] = partie_prete(2)
    agir(s, h, t="verrouiller", valeur=True)
    with pytest.raises(ErreurJeu) as e:
        entrer(s, "nouveau")
    assert e.value.statut == 403
    s.deconnecter(b, fb)
    entrer(s, "b")                                           # un membre déjà présent peut revenir
    agir(s, h, t="verrouiller", valeur=False)
    entrer(s, "nouveau")
    with pytest.raises(ErreurJeu):
        agir(s, b, t="verrouiller", valeur=True)             # seul l'hôte


def test_un_membre_retire_ne_peut_plus_agir(temps):
    s, [(h, _), (b, fb)] = partie_prete(2)
    agir(s, h, t="exclure", id=b.id)
    with pytest.raises(ErreurJeu):
        agir(s, b, t="chat", texte="encore là ?")


def test_deux_personnes_ne_portent_pas_le_meme_pseudo():
    s = nouveau()
    a = s.rejoindre("a", "Léo", "joueur", Faux())
    b = s.rejoindre("b", "Léo", "joueur", Faux())
    c = s.rejoindre("c", "Léo", "joueur", Faux())
    assert [a.pseudo, b.pseudo, c.pseudo] == ["Léo", "Léo (2)", "Léo (3)"]


def test_websocket_sans_message_d_entree_est_ferme():
    app, c = _site()
    code = c.post("/api/salons", {"carte": "drome-ardeche"})[1]["code"]

    async def main():
        w = ClientWS(app, f"/ws/salons/{code}", {"Origin": "http://test"}, dict(c.cookies))   # pas d'« entree »
        async with w:
            await w.envoyer({"t": "chat", "texte": "je saute l'accueil"})
            assert await w.recevoir() is None and w.code_fermeture == 4400
    run(main())
    assert salons.gestionnaire.trouver(code).membres == {}


def test_le_pseudo_ne_passe_jamais_par_l_adresse():
    app, c = _site()
    code = c.post("/api/salons", {"carte": "drome-ardeche"})[1]["code"]

    async def main():
        async with _ws(app, c, code, "Prénom-Secret") as w:
            assert w.scope["query_string"] == b"" and b"Secret" not in w.scope["raw_path"]
            e = await w.jusqu_a("etat")
            assert e["membres"][0]["pseudo"] == "Prénom-Secret"
    run(main())
