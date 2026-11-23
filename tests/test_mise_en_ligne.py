"""Étape 4 : plafond d'images, limites de débit, en-têtes de sécurité, pseudos refusés, purge, migration."""
import pytest

from serveur import base, horloge, protection, quota
from serveur.app import creer_app
from serveur.jeu import moteur
from tests.client import Client


@pytest.fixture
def app():
    return creer_app()


def test_quota_inactif_en_mode_factice(app):
    for _ in range(50):
        quota.consommer(1)
    assert quota.usage()["aujourdhui"] == 0


def test_quota_plafond_refuse_sans_compter(monkeypatch, app):
    monkeypatch.setenv("OUSUISJE_IMAGES", "google")
    monkeypatch.setenv("OUSUISJE_PLAFOND_IMAGES", "5")
    quota.consommer(3)
    quota.consommer(2)
    with pytest.raises(moteur.ErreurJeu) as e:
        quota.consommer(1)
    assert e.value.statut == 503 and "reviens demain" in str(e.value)
    assert quota.usage()["aujourdhui"] == 5          # le refus n'a rien consommé


def test_quota_compte_par_jour_de_paris(monkeypatch, temps, app):
    monkeypatch.setenv("OUSUISJE_IMAGES", "google")
    monkeypatch.setenv("OUSUISJE_PLAFOND_IMAGES", "2")
    quota.consommer(2)
    with pytest.raises(moteur.ErreurJeu):
        quota.consommer(1)
    temps.t += 86400
    quota.consommer(2)                               # nouveau jour : le compteur repart


def test_manche_suivante_refusee_quand_plus_d_images(monkeypatch, app):
    c = Client(app)
    statut, d = c.post("/api/parties", {"mode": "classique", "carte": "drome-ardeche", "contrainte": "libre",
                                        "chrono": 0, "pseudo": "Léo"})
    assert statut == 200
    assert c.post(f"/api/parties/{d['id']}/reponse", {"lat": 44.9, "lon": 4.9})[0] == 200
    monkeypatch.setenv("OUSUISJE_IMAGES", "google")
    monkeypatch.setenv("OUSUISJE_PLAFOND_IMAGES", "1")
    with base.connexion() as cx:
        cx.execute("INSERT OR REPLACE INTO usage_images (jour, n) VALUES (?, 1)", (horloge.jour_paris(),))
    statut, r = c.post(f"/api/parties/{d['id']}/suivante")
    assert statut == 503 and "reviens demain" in r["erreur"]


def test_admin_usage_reserve_a_l_admin(app, monkeypatch):
    monkeypatch.setenv("OUSUISJE_ADMIN", "thibault")
    assert Client(app).get("/api/admin/usage")[0] in (401, 403)
    admin = Client(app, {"Remote-User": "thibault"})
    statut, d = admin.get("/api/admin/usage")
    assert statut == 200 and "aujourdhui" in d


def test_en_tetes_de_securite(app):
    # on lit les en-têtes bruts de la réponse
    import asyncio
    recus = {}

    async def go():
        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(m):
            if m["type"] == "http.response.start":
                recus.update({k.decode().lower(): v.decode() for k, v in m["headers"]})
        await app({"type": "http", "method": "GET", "path": "/api/config", "query_string": b"", "headers": [],
                   "client": ("1.2.3.4", 1), "server": ("x", 80), "scheme": "http", "http_version": "1.1",
                   "root_path": ""}, receive, send)
    asyncio.run(go())
    assert recus["x-content-type-options"] == "nosniff"
    assert recus["x-frame-options"] == "DENY"
    assert "geolocation=()" in recus["permissions-policy"]


def test_post_sans_en_tete_refuse_partout(app):
    c = Client(app)
    c.entetes.pop("X-Requete")
    for chemin in ("/api/parties", "/api/defis", "/api/salons", "/api/admin/cartes"):
        assert c.post(chemin, {})[0] == 400, chemin


def test_limite_de_debit_creation_de_salons(app):
    c = Client(app)
    codes = [c.post("/api/salons", {"carte": "monde"})[0] for _ in range(14)]
    assert 429 in codes
    assert codes.index(429) <= 10


def test_pseudo_refuse(tmp_path, monkeypatch):
    fichier = tmp_path / "refuses.txt"
    fichier.write_text("zorglub\n", encoding="utf-8")
    monkeypatch.setenv("OUSUISJE_PSEUDOS_REFUSES", str(fichier))
    assert moteur.nettoyer_pseudo("Zorglub") == "Invité"
    assert moteur.nettoyer_pseudo("Z0rglub") == "Invité"       # chiffres à la place des lettres
    assert moteur.nettoyer_pseudo("Léo") == "Léo"


def test_purge_des_vieilles_parties(temps, app):
    c = Client(app)
    statut, d = c.post("/api/parties", {"mode": "classique", "carte": "drome-ardeche", "contrainte": "libre",
                                        "chrono": 0, "pseudo": "Léo"})
    assert statut == 200
    temps.t += 89 * 86400
    assert protection.purger()["parties_supprimees"] == 0
    temps.t += 2 * 86400                                       # 91 jours : invité > 90 jours
    assert protection.purger()["parties_supprimees"] == 1
    with base.connexion() as cx:
        assert cx.execute("SELECT COUNT(*) n FROM manches").fetchone()["n"] == 0


def test_migration_usage_images_et_version():
    with base.connexion() as c:
        assert c.execute("PRAGMA user_version").fetchone()[0] >= 3
        c.execute("SELECT jour, n FROM usage_images").fetchall()


def test_pas_de_verrou_quand_la_manche_expire_en_mode_google(monkeypatch, temps, app):
    """consommer() réutilise la connexion de l'appelant : pas de « database is locked » après une écriture."""
    c = Client(app)
    statut, d = c.post("/api/parties", {"mode": "classique", "carte": "drome-ardeche", "contrainte": "libre",
                                        "chrono": 30, "pseudo": "Léo"})
    assert statut == 200
    monkeypatch.setenv("OUSUISJE_IMAGES", "google")
    monkeypatch.setenv("OUSUISJE_PLAFOND_IMAGES", "10")
    temps.t += 120                                   # la manche expire : _regler_si_expiree écrit avant le quota
    statut, r = c.post(f"/api/parties/{d['id']}/suivante")
    assert statut == 200, r
    assert quota.usage()["aujourdhui"] == 1


def test_adresse_truquee_par_x_forwarded_for_ne_change_pas_la_limite(app):
    c = Client(app)
    c.entetes["X-Real-IP"] = "9.9.9.9"
    codes = []
    for i in range(14):
        c.entetes["X-Forwarded-For"] = f"10.0.0.{i}"
        codes.append(c.post("/api/salons", {"carte": "monde"})[0])
    assert 429 in codes


@pytest.mark.parametrize("pseudo,refuse", [
    ("Violette", False), ("Veronique", False), ("Habite", False), ("Computer", False), ("Léo", False),
    ("viol", True), ("Gros_Pute", True), ("xxPutainxx", True), ("Pute!", True),
])
def test_pseudos_par_mots(pseudo, refuse):
    assert moteur.pseudo_refuse(pseudo) is refuse


def test_suppression_de_compte(app):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "outils"))
    import supprimer_compte
    with base.connexion() as c:
        c.execute("INSERT INTO comptes (identifiant, pseudo, cree_le) VALUES ('thib', 'Thib', 1)")
        c.execute("INSERT INTO succes (identifiant, code, obtenu_le) VALUES ('thib', 'x', 1)")
    assert supprimer_compte.supprimer_compte("thib")["comptes"] == 1
    with base.connexion() as c:
        assert c.execute("SELECT COUNT(*) n FROM succes").fetchone()["n"] == 0
