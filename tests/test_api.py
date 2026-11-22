"""Parties, chrono, défis, série et exploration, par l'API (application complète, base temporaire)."""
import json
from datetime import datetime

import pytest

from serveur import horloge
from serveur.app import creer_app
from serveur.jeu import cartes, geo
from tests.client import Client

VALENCE = (44.9334, 4.8924)
GENEVE = (46.2044, 6.1432)


@pytest.fixture
def app():
    return creer_app()


def creer(client, **kw):
    corps = {"mode": "classique", "carte": "drome-ardeche", "contrainte": "libre", "chrono": 0, "pseudo": "Léo"}
    corps.update(kw)
    statut, d = client.post("/api/parties", corps)
    assert statut == 200, d
    return d["id"]


def repondre(client, pid, lat=VALENCE[0], lon=VALENCE[1]):
    return client.post(f"/api/parties/{pid}/reponse", {"lat": lat, "lon": lon})


def jouer_tout(client, pid, nb=5):
    for i in range(nb):
        statut, r = repondre(client, pid)
        assert statut == 200, r
        if i < nb - 1:
            assert client.post(f"/api/parties/{pid}/suivante")[0] == 200
    return r


# ------------------------------------------------------------ critères 2, 3, 4, 7

def test_une_manche_complete(app):  # critère 2
    c = Client(app)
    pid = creer(c)
    statut, etat = c.get(f"/api/parties/{pid}")
    assert etat["phase"] == "question" and etat["manche"]["numero"] == 1
    statut, r = repondre(c, pid, 45.0, 5.0)
    assert r["lieu"]["pays"] == "FR" and r["reponse"] == {"lat": 45.0, "lon": 5.0}
    assert r["distance_m"] > 0 and 0 <= r["points"] <= 5000 and r["fiche"]["nom"] == "France"
    assert c.get(f"/api/parties/{pid}")[1]["phase"] == "resultat"


def test_le_serveur_calcule_le_score_seul(app):  # critère 3
    c = Client(app)
    pid = creer(c)
    _, r = c.post(f"/api/parties/{pid}/reponse", {"lat": 45.0, "lon": 5.0, "points": 5000, "distance_m": 0})
    attendu = round(5000 * 2.718281828459045 ** (-10 * r["distance_m"] / 1000 / cartes.carte("drome-ardeche")["diagonale_km"]))
    assert r["points"] == attendu != 5000


def test_pas_de_coordonnees_avant_la_reponse(app):  # critère 4
    c = Client(app)
    pid = creer(c)
    brut = json.dumps(c.get(f"/api/parties/{pid}")[1])
    assert '"lat"' not in brut and '"lon"' not in brut and '"pays"' not in brut
    from serveur import base
    with base.connexion() as db:                      # les vraies coordonnées du lieu, côté serveur
        lieu = json.loads(db.execute("SELECT lieu_json FROM manches").fetchone()[0])
    assert str(lieu["lat"]) not in brut and str(lieu["lon"]) not in brut and lieu["id"] not in brut
    assert c.get(f"/api/parties/{pid}/recap")[0] == 403          # pas de récap avant la fin
    # un autre navigateur ne peut pas lire la partie
    assert Client(app).get(f"/api/parties/{pid}")[0] == 404


def test_recap_cinq_manches(app):  # critère 7
    c = Client(app)
    pid = creer(c)
    dernier = jouer_tout(c, pid)
    assert dernier["statut"] == "terminee"
    _, rc = c.get(f"/api/parties/{pid}/recap")
    assert len(rc["manches"]) == 5 and rc["maximum"] == 25000
    assert rc["total"] == sum(m["points"] for m in rc["manches"])
    assert c.post(f"/api/parties/{pid}/suivante")[0] == 409      # plus de manche après la 5e


def test_donnees_invalides(app):
    c = Client(app)
    pid = creer(c)
    assert c.post("/api/parties", {"mode": "nimportequoi"})[0] == 400
    assert c.post("/api/parties", {"mode": "classique", "carte": "lune"})[0] == 400
    assert c.post("/api/parties", {"mode": "classique", "carte": "monde", "chrono": 7})[0] == 400
    assert c.post(f"/api/parties/{pid}/reponse", {"lat": 200, "lon": 0})[0] == 400
    assert c.post(f"/api/parties/{pid}/reponse", {"lat": "x", "lon": 0})[0] == 400
    assert repondre(c, pid)[0] == 200
    assert repondre(c, pid)[0] == 409                              # déjà répondu
    assert c.get("/api/parties/inconnue")[0] == 404


def test_pseudo_nettoye(app):
    c = Client(app)
    pid = creer(c, pseudo="  <b>Léo\n</b>   le  grand  pseudo très très long ")
    pseudo = c.get(f"/api/parties/{pid}")[1]["partie"]["pseudo"]
    assert len(pseudo) <= 20 and "\n" not in pseudo and "  " not in pseudo
    assert c.get(f"/api/parties/{creer(c, pseudo='   ')}")[1]["partie"]["pseudo"] == "Invité"


# ------------------------------------------------------------ critère 6 : chrono

def test_chrono_sans_repere_vaut_zero(app, temps):
    c = Client(app)
    pid = creer(c, chrono=10)
    _, e = c.get(f"/api/parties/{pid}")
    assert 9 < e["manche"]["temps_restant"] <= 10
    temps.t += 20                                                  # le temps passe, personne ne répond
    _, e = c.get(f"/api/parties/{pid}")
    assert e["phase"] == "resultat" and e["resultat"]["points"] == 0 and e["resultat"]["temps_ecoule"]


def test_chrono_repere_valide_a_zero(app, temps):
    c = Client(app)
    pid = creer(c, chrono=10)
    temps.t += 10.5                                                # réponse envoyée quand le chrono tombe à zéro
    _, r = repondre(c, pid)
    assert r["points"] > 0 and not r["temps_ecoule"]
    pid = creer(c, chrono=10)
    temps.t += 10.2
    _, r = c.post(f"/api/parties/{pid}/reponse", {})               # aucun repère posé
    assert r["points"] == 0 and r["temps_ecoule"]


def test_reponse_trop_tardive_ne_compte_pas(app, temps):
    c = Client(app)
    pid = creer(c, chrono=10)
    temps.t += 14
    statut, r = repondre(c, pid)
    assert statut == 200 and r["points"] == 0 and r["temps_ecoule"]


def test_le_chrono_ne_demarre_qu_a_la_manche_suivante(app, temps):
    c = Client(app)
    pid = creer(c, chrono=10)
    repondre(c, pid)
    temps.t += 600                                                 # longue pause sur l'écran de résultat
    c.post(f"/api/parties/{pid}/suivante")
    _, e = c.get(f"/api/parties/{pid}")
    assert e["phase"] == "question" and e["manche"]["temps_restant"] > 9


# ------------------------------------------------------------ critères 8, 9 : défis

def test_defi_partage_memes_lieux_et_classement(app):  # critère 8
    createur = Client(app)
    statut, d = createur.post("/api/defis", {"carte": "france", "contrainte": "libre", "chrono": 0})
    assert statut == 200 and d["lien"] == f"/?defi={d['id']}"
    lieux_vus = []
    for pseudo, lat in (("Léo", 45.0), ("Arthur", 48.0)):
        joueur = Client(app)
        _, p = joueur.post("/api/parties", {"mode": "defi", "defi_id": d["id"], "pseudo": pseudo})
        suite = []
        for i in range(5):
            _, r = repondre(joueur, p["id"], lat, 2.0)
            suite.append((r["lieu"]["lat"], r["lieu"]["lon"]))
            if i < 4:
                joueur.post(f"/api/parties/{p['id']}/suivante")
        lieux_vus.append(suite)
    assert lieux_vus[0] == lieux_vus[1] and len(set(lieux_vus[0])) == 5
    _, infos = Client(app).get(f"/api/defis/{d['id']}")
    assert [l["pseudo"] for l in infos["classement"]] != [] and len(infos["classement"]) == 2
    assert infos["classement"][0]["total"] >= infos["classement"][1]["total"]
    assert "lieux" not in json.dumps(infos) and '"lat"' not in json.dumps(infos)


def test_defi_une_seule_tentative_et_inconnu(app):
    c = Client(app)
    _, d = c.post("/api/defis", {"carte": "france"})
    _, p = c.post("/api/parties", {"mode": "defi", "defi_id": d["id"]})
    statut, e = c.post("/api/parties", {"mode": "defi", "defi_id": d["id"]})
    assert statut == 409 and e["partie_id"] == p["id"]
    assert c.get("/api/defis/nexistepas")[0] == 404
    assert c.post("/api/parties", {"mode": "defi", "defi_id": "nexistepas"})[0] == 404


def paris(annee, mois, jour, h, m, s):
    return datetime(annee, mois, jour, h, m, s, tzinfo=horloge.PARIS).timestamp()


def lieux_du_defi(client, defi_id):
    _, p = client.post("/api/parties", {"mode": "defi", "defi_id": defi_id, "pseudo": "x"})
    sortie = []
    for i in range(5):
        _, r = repondre(client, p["id"])
        sortie.append((r["lieu"]["lat"], r["lieu"]["lon"]))
        if i < 4:
            client.post(f"/api/parties/{p['id']}/suivante")
    return sortie


def test_defi_du_jour(app, temps):  # critère 9
    temps.t = paris(2026, 11, 22, 23, 59, 50)
    a, b = Client(app), Client(app)
    _, ja = a.get("/api/defi-du-jour")
    assert ja["id"] == "jour-2026-11-22"
    assert lieux_du_defi(a, ja["id"]) == lieux_du_defi(b, ja["id"])   # identique pour tous
    statut, e = a.post("/api/parties", {"mode": "defi_jour", "pseudo": "Léo"})
    assert statut == 409 and "partie_id" in e                          # une seule tentative par jour
    temps.t = paris(2026, 11, 23, 0, 0, 5)                             # minuit passé à Paris
    _, jb = a.get("/api/defi-du-jour")
    assert jb["id"] == "jour-2026-11-23"
    statut, e = a.post("/api/parties", {"mode": "defi_jour", "pseudo": "Léo"})
    assert statut == 200                                               # nouvelle journée : on peut rejouer
    assert jb["deja_joue"] is None


def test_tirage_du_jour_deterministe(temps):
    from serveur import base
    from serveur.jeu import moteur
    temps.t = paris(2026, 11, 22, 12, 0, 0)
    with base.connexion() as c:
        premier = moteur._defi_jour(c)["lieux_json"]
        c.execute("DELETE FROM defis")
        assert moteur._defi_jour(c)["lieux_json"] == premier           # même date → mêmes lieux
    temps.t = paris(2026, 11, 23, 12, 0, 0)
    with base.connexion() as c:
        assert moteur._defi_jour(c)["lieux_json"] != premier


# ------------------------------------------------------------ critère 10 : série de pays

def test_serie_juste_puis_fausse(app):
    c = Client(app)
    pid = creer(c, mode="serie", carte="france")
    _, r = repondre(c, pid, *VALENCE)                                  # cible en France, clic en France
    assert r["juste"] and r["points"] == 1 and r["statut"] == "en_cours"
    c.post(f"/api/parties/{pid}/suivante")
    _, r = repondre(c, pid, *GENEVE)                                   # clic en Suisse
    assert not r["juste"] and r["pays_choisi"] == "Suisse" and r["statut"] == "terminee"
    _, e = c.get(f"/api/parties/{pid}")
    assert e["phase"] == "fin" and e["resultat"]["serie"] == 1 and e["resultat"]["record"] == 1
    assert c.post(f"/api/parties/{pid}/suivante")[0] == 409


def test_serie_en_mer_et_record(app):
    c = Client(app)
    pid = creer(c, mode="serie", carte="france")
    repondre(c, pid, *VALENCE)
    c.post(f"/api/parties/{pid}/suivante")
    repondre(c, pid, *VALENCE)
    c.post(f"/api/parties/{pid}/suivante")
    _, r = repondre(c, pid, 0, 0)                                      # en pleine mer : fausse
    assert not r["juste"] and r["pays_choisi"] is None
    assert c.get(f"/api/parties/{pid}")[1]["resultat"]["record"] == 2
    pid2 = creer(c, mode="serie", carte="france")
    repondre(c, pid2, *GENEVE)                                         # série ratée dès le début
    assert c.get(f"/api/parties/{pid2}")[1]["resultat"]["record"] == 2  # le record n'est pas écrasé


def test_serie_indisponible_sans_contours(app, monkeypatch, tmp_path):
    monkeypatch.setenv("OUSUISJE_PAYS", str(tmp_path / "absent.geojson"))
    statut, e = Client(app).post("/api/parties", {"mode": "serie", "carte": "france"})
    assert statut == 503 and "pays.geojson" in e["erreur"]
    assert Client(app).post("/api/parties", {"mode": "classique", "carte": "france"})[0] == 200  # le reste marche


# ------------------------------------------------------------ critère 12 : exploration

def test_exploration_sans_score(app):
    c = Client(app)
    pid = creer(c, mode="exploration", carte="europe")
    assert repondre(c, pid)[0] == 400
    statut, r = c.post(f"/api/parties/{pid}/reveler")
    assert statut == 200 and r["lieu"]["pays"] and r["points"] == 0 and r["reponse"] is None
    assert c.post(f"/api/parties/{pid}/reveler")[0] == 409
    assert c.post(f"/api/parties/{pid}/suivante")[0] == 200            # autant de lieux qu'on veut
    _, e = c.get(f"/api/parties/{pid}")
    assert e["phase"] == "question" and e["manche"]["numero"] == 2 and e["partie"]["nb_manches"] is None


def test_contraintes_et_cartes_exposees(app):
    c = Client(app)
    _, cs = c.get("/api/cartes")
    assert {x["id"] for x in cs["cartes"]} >= {"monde", "europe", "france", "auvergne-rhone-alpes", "drome-ardeche", "villes-celebres"}
    assert c.get("/api/config")[1]["images"] == "factice"
    for k in ("libre", "sans_deplacement", "fige"):
        pid = creer(c, contrainte=k)
        assert c.get(f"/api/parties/{pid}")[1]["partie"]["contrainte"] == k


def test_google_sans_reserve_donne_un_message_clair(app, monkeypatch, tmp_path):
    monkeypatch.setenv("OUSUISJE_IMAGES", "google")
    monkeypatch.setenv("OUSUISJE_RESERVES", str(tmp_path))
    statut, e = Client(app).post("/api/parties", {"mode": "classique", "carte": "france"})
    assert statut == 503 and "generer_reserve" in e["erreur"]


def test_google_reserve_envoie_un_identifiant_de_panorama(app, monkeypatch, tmp_path):
    monkeypatch.setenv("OUSUISJE_IMAGES", "google")
    monkeypatch.setenv("OUSUISJE_RESERVES", str(tmp_path))
    reserve = [{"pano_id": f"PANO{i}", "lat": 44.0 + i / 10, "lon": 4.5, "pays": "FR"} for i in range(8)]
    (tmp_path / "drome-ardeche.json").write_text(json.dumps(reserve))
    c = Client(app)
    pid = creer(c)
    _, e = c.get(f"/api/parties/{pid}")
    assert e["manche"]["image"]["type"] == "google" and e["manche"]["image"]["pano_id"].startswith("PANO")
    assert '"lat"' not in json.dumps(e)


def test_entrees_mal_typees_ne_font_pas_de_500(app):
    c = Client(app)
    for corps in ({"mode": "classique", "carte": []}, {"mode": ["x"]}, {"mode": "classique", "carte": "monde", "chrono": "10"},
                  {"mode": "classique", "carte": "monde", "chrono": True}, {"mode": "classique", "carte": "monde", "contrainte": {}},
                  {"mode": "defi", "defi_id": ["a"]}):
        assert c.post("/api/parties", corps)[0] == 400, corps
    assert c.post("/api/defis", {"carte": {}})[0] == 400


def test_pseudo_sans_caracteres_invisibles(app):
    c = Client(app)
    pid = creer(c, pseudo="Léo‮​﻿!")
    assert c.get(f"/api/parties/{pid}")[1]["partie"]["pseudo"] == "Léo!"
