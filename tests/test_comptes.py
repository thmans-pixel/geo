"""Étape 2 : comptes (SSO), profil, succès, classements, éditeur de cartes (critères 15 à 20)."""
import sqlite3

import pytest

from serveur import base
from serveur.app import creer_app
from tests.client import Client
from tests.test_api import VALENCE, creer, jouer_tout, repondre

H = {"X-Requete": "ou-suis-je"}


@pytest.fixture
def app():
    return creer_app()


def membre(app, nom="thibault", **plus):
    return Client(app, {"Remote-User": nom, **plus})


def pseudo_de(c, nouveau):
    c.entetes.update(H)
    assert c.post("/api/moi/pseudo", {"pseudo": nouveau})[0] == 200


def test_en_tete_refuse_hors_proxy_local(app, monkeypatch):  # sécurité : usurpation
    c = membre(app)
    assert c.get("/api/moi")[1]["connecte"] is True
    monkeypatch.setenv("OUSUISJE_SECRET_PROXY", "s3cret")
    assert c.get("/api/moi")[1]["connecte"] is False                      # secret absent
    c.entetes["X-Auth-Secret"] = "faux"
    assert c.get("/api/moi")[1]["connecte"] is False
    c.entetes["X-Auth-Secret"] = "s3cret"
    assert c.get("/api/moi")[1]["connecte"] is True


def test_cookie_ne_peut_pas_usurper_un_compte(app):
    c = Client(app)
    c.cookies["joueur_id"] = "c:alice"
    c.get("/api/config")
    assert not c.cookies["joueur_id"].startswith("c:")


def test_pseudo_par_defaut_neutre_et_defi_suit_le_pseudo(app):
    c = membre(app, "alice")
    assert c.get("/api/moi")[1]["pseudo"].startswith("Joueur-")
    jouer_tout(c, creer(c, mode="defi_jour"))
    pseudo_de(c, "Zoé")
    assert [l["pseudo"] for l in c.get("/api/defi-du-jour")[1]["classement"]] == ["Zoé"]


def test_pas_d_inscription_ni_de_mot_de_passe(app):  # critère 15
    c = Client(app)
    for chemin in ("/api/inscription", "/api/register", "/api/connexion", "/api/login"):
        assert c.post(chemin, {"mot_de_passe": "x"})[0] in (404, 405)
    with base.connexion() as cn:
        colonnes = {r["name"].lower() for t in ("comptes", "succes") for r in cn.execute(f"PRAGMA table_info({t})")}
    assert not any(m in col for col in colonnes for m in ("pass", "mdp", "mail", "hash", "secret"))


def test_invite_et_membre(app):  # critère 16
    assert Client(app).get("/api/moi")[1]["connecte"] is False
    assert Client(app).get("/api/moi/profil")[0] == 401
    _, moi = membre(app).get("/api/moi")
    assert moi["connecte"] and moi["identifiant"] == "thibault" and moi["niveau"]["niveau"] == 1
    # un en-tête mal formé n'ouvre aucun compte
    assert Client(app, {"Remote-User": "../etc;drop"}).get("/api/moi")[1]["connecte"] is False


def test_pseudo_du_compte_et_csrf(app):
    c = membre(app)
    assert c.post("/api/moi/pseudo", {"pseudo": "Zoé"})[0] == 400          # sans l'en-tête X-Requete
    c.entetes.update(H)
    assert c.post("/api/moi/pseudo", {"pseudo": "Zoé"})[1]["pseudo"] == "Zoé"
    pid = creer(c, pseudo="Autre")
    assert c.get(f"/api/parties/{pid}")[1]["partie"]["pseudo"] == "Zoé"             # le pseudo du compte l'emporte


def test_profil_et_succes(app):  # critères 17 et 18
    c = membre(app)
    pid = creer(c)
    r = jouer_tout(c, pid)
    assert "premiere_partie" in [s["code"] for s in r["nouveaux_succes"]]
    _, p = c.get("/api/moi/profil")
    assert p["parties_jouees"] == 1 and p["niveau"]["xp"] > 0
    assert {s["code"] for s in p["succes"] if s["obtenu"]} >= {"premiere_partie"}
    # un succès ne s'obtient qu'une fois
    pid2 = creer(c)
    r2 = jouer_tout(c, pid2)
    assert "premiere_partie" not in [s["code"] for s in r2["nouveaux_succes"]]


def test_classements_comptes_seulement(app):  # critère 19
    a, b, invite = membre(app, "alice"), membre(app, "bob"), Client(app)
    pseudo_de(a, "alice"); pseudo_de(b, "bob")
    for cl in (a, b, invite):
        jouer_tout(cl, creer(cl))
    _, cl = Client(app).get("/api/classements?carte=drome-ardeche")
    noms = [l["pseudo"] for l in cl["par_carte"]]
    assert sorted(noms) == ["alice", "bob"] and len(noms) == 2          # l'invité n'y figure pas


def test_admin_reserve(app, monkeypatch):  # critère 20
    monkeypatch.setenv("OUSUISJE_ADMIN", "thibault")
    assert Client(app).get("/api/admin/cartes")[0] == 401
    assert membre(app, "leo").get("/api/admin/cartes")[0] == 403
    corps = {"nom": "Valence", "mode": "zone", "nombre": 8,
             "zone": [[44.90, 4.85], [44.90, 4.95], [44.97, 4.95], [44.97, 4.85]]}
    assert membre(app).post("/api/admin/cartes", corps)[0] == 400          # sans X-Requete
    assert membre(app, "leo", **H).post("/api/admin/cartes", corps)[0] == 403


def test_editeur_zone_et_points(app, monkeypatch):  # critère 20
    monkeypatch.setenv("OUSUISJE_ADMIN", "thibault")
    c = membre(app, **H)
    zone = {"nom": "Valence centre", "mode": "zone", "nombre": 8,
            "zone": [[44.90, 4.85], [44.90, 4.95], [44.97, 4.95], [44.97, 4.85]]}
    statut, r = c.post("/api/admin/cartes", zone)
    assert statut == 200 and r["retenus"] >= 5 and r["id"].startswith("perso-valence-centre")
    assert any(k["id"] == r["id"] and k["perso"] for k in c.get("/api/cartes")[1]["cartes"])
    pid = creer(c, carte=r["id"])
    _, rep = repondre(c, pid)
    assert rep["lieu"]["pays"] == "FR" and 44.90 <= rep["lieu"]["lat"] <= 44.97
    # carte par points
    statut, r2 = c.post("/api/admin/cartes", {"nom": "Six lieux", "mode": "points",
                                              "points": [[44.93 + i * .01, 4.89] for i in range(6)]})
    assert statut == 200 and r2["retenus"] == 6
    # archivage : disparaît de la liste, la partie en cours continue
    assert c.delete(f"/api/admin/cartes/{r['id']}")[0] == 200
    assert all(k["id"] != r["id"] for k in c.get("/api/cartes")[1]["cartes"])
    assert c.get(f"/api/parties/{pid}")[0] == 200
    assert creer_refuse(c, r["id"])


def creer_refuse(c, carte):
    return c.post("/api/parties", {"mode": "classique", "carte": carte, "pseudo": "x"})[0] >= 400


def test_editeur_refuse_les_entrees_invalides(app, monkeypatch):
    monkeypatch.setenv("OUSUISJE_ADMIN", "thibault")
    c = membre(app, **H)
    assert c.post("/api/admin/cartes", {"nom": "", "mode": "zone"})[0] == 400
    assert c.post("/api/admin/cartes", {"nom": "x", "mode": "points", "points": [[95, 0]]})[0] == 400
    assert c.post("/api/admin/cartes", {"nom": "x", "mode": "points", "points": [[1, 1]] * 201})[0] == 400
    assert c.post("/api/admin/cartes", {"nom": "x", "mode": "zone", "zone": [[1, 1]] * 2})[0] == 400
    assert c.post("/api/admin/cartes", {"nom": "x", "mode": "zone", "nombre": 999,
                                        "zone": [[44, 4], [44, 5], [45, 5]]})[0] == 400
    # trop peu de lieux avec image (en mer) : rien n'est créé
    statut, r = c.post("/api/admin/cartes", {"nom": "Mer", "mode": "points", "points": [[0, -30], [1, -30]]})
    assert statut == 422
    assert c.get("/api/admin/cartes")[1]["cartes"] == []
