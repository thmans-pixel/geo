"""Parcours complet dans un vrai navigateur (Chrome sans écran), avec l'image factice.
Ne vérifie PAS Street View ni les tuiles de carte réelles : aucun accès réseau extérieur ici."""
import re
import shutil
import socket
import threading
import time

import pytest

playwright = pytest.importorskip("playwright.sync_api")
CHROME = shutil.which("google-chrome") or shutil.which("chromium")
pytestmark = pytest.mark.skipif(CHROME is None, reason="pas de navigateur")


@pytest.fixture
def site():
    import uvicorn
    from serveur.app import creer_app
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    serveur = uvicorn.Server(uvicorn.Config(creer_app(), host="127.0.0.1", port=port, log_level="error"))
    fil = threading.Thread(target=serveur.run, daemon=True); fil.start()
    for _ in range(100):
        if serveur.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    serveur.should_exit = True
    fil.join(5)


@pytest.fixture
def navigateur():
    with playwright.sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        yield b
        b.close()


def nouvelle_page(navigateur, site, **kw):
    ctx = navigateur.new_context(**kw)
    ctx.route("**/*", lambda r: r.continue_() if r.request.url.startswith(site) else r.abort())  # rien d'extérieur
    page = ctx.new_page()
    erreurs = []
    page.on("pageerror", lambda e: erreurs.append(str(e)))
    page.erreurs = erreurs
    return ctx, page


def poser_repere(page, dx=0.5, dy=0.5):
    """Survole la mini-carte (elle s'agrandit), attend la fin de l'agrandissement, puis clique."""
    boite = page.locator("#mini-carte").bounding_box()
    page.mouse.move(boite["x"] + boite["width"] / 2, boite["y"] + boite["height"] / 2)
    page.wait_for_timeout(450)
    boite = page.locator("#mini-carte").bounding_box()
    page.mouse.click(boite["x"] + boite["width"] * dx, boite["y"] + boite["height"] * dy)


def lancer(page, site, mode="classique", carte="drome-ardeche", contrainte="libre", chrono="0"):
    page.goto(site)
    page.click(f'.mode[data-mode="{mode}"]')
    if mode not in ("defi_jour",):
        if page.locator('select[name="carte"]').is_visible():
            page.select_option('select[name="carte"]', carte)
        if page.locator('select[name="contrainte"]').is_visible():
            page.select_option('select[name="contrainte"]', contrainte)
        if page.locator('select[name="chrono"]').is_visible():
            page.select_option('select[name="chrono"]', chrono)
    page.fill('input[name="pseudo"]', "Léo")
    page.click("#jouer")


def test_partie_classique_complete(navigateur, site):  # critères 1, 2, 7, 14
    ctx, page = nouvelle_page(navigateur, site)
    reponses = []
    page.on("response", lambda r: reponses.append(r) if "/api/parties/" in r.url and r.request.method == "GET" else None)
    lancer(page, site)
    page.wait_for_selector("#pano .pano-factice")
    assert page.is_disabled("#valider")                          # critère 1 : inactif tant qu'aucun repère
    assert page.locator("#mini-carte svg [data-repere]").count() == 0
    for manche in range(1, 6):
        assert f"Manche {manche} / 5" in page.inner_text("#hud-manche")
        poser_repere(page, 0.5, 0.5)
        assert page.is_enabled("#valider") and page.inner_text("#valider") == "Valider"
        poser_repere(page, 0.3, 0.4)                               # on peut déplacer son repère
        assert page.locator("#mini-carte svg [data-repere]").count() == 1
        page.click("#valider")
        page.wait_for_selector("#res-distance")                    # critère 2
        assert re.search(r"\d+(,\d)? (km|m)$", page.inner_text("#res-distance").replace("\u202f", " ").replace("\u00a0", " "))
        assert int(re.sub(r"\D", "", page.inner_text("#res-points"))) >= 0
        assert page.locator("#res-carte svg [data-repere]").count() == 2      # lieu + ma réponse
        assert page.locator("#res-carte svg line").count() == 1               # la ligne entre les deux
        assert page.locator(".fiche h3").inner_text().strip() != ""
        page.click("#suite")
        if manche < 5:
            page.wait_for_selector("#valider")
    page.wait_for_selector("#recap-total")                         # critère 7
    texte = re.sub(r"\s", " ", page.inner_text(".res-panneau"))
    assert "25 000" in texte.replace(" ", " ").replace(" ", " ")
    assert page.locator(".recap tbody tr").count() == 5
    assert page.locator("#res-carte svg [data-repere]").count() == 10
    # critère 4 vu du navigateur : jamais de coordonnées dans les réponses pendant une question
    for r in reponses:
        corps = r.json() if r.ok else {}
        if corps.get("phase") == "question":
            assert '"lat"' not in r.text() and '"lon"' not in r.text()
    assert page.erreurs == []
    ctx.close()


def test_contraintes(navigateur, site):  # critère 5 (le comportement réel de Street View n'est pas testé ici)
    ctx, page = nouvelle_page(navigateur, site)
    lancer(page, site, contrainte="libre")
    page.wait_for_selector("#pano .pano-factice")
    assert page.locator(".fleches").count() == 1
    for contrainte in ("sans_deplacement", "fige"):
        lancer(page, site, contrainte=contrainte)
        page.wait_for_selector("#pano .pano-factice")
        assert page.locator(".fleches").count() == 0
        assert page.get_attribute(".jeu", "data-contrainte") == contrainte
    ctx.close()


def test_chrono_validation_automatique(navigateur, site):  # critère 6
    ctx, page = nouvelle_page(navigateur, site)
    lancer(page, site, chrono="10")
    page.wait_for_selector("#hud-chrono:not([hidden])")
    poser_repere(page)
    page.wait_for_selector("#res-distance", timeout=15000)         # validé tout seul à zéro
    assert int(re.sub(r"\D", "", page.inner_text("#res-points"))) > 0
    page.click("#suite")
    page.wait_for_selector("#valider")
    page.wait_for_selector("#res-points", timeout=15000)           # cette fois sans repère
    assert page.inner_text("#res-points") == "0" and "Temps écoulé" in page.inner_text(".res-panneau")
    ctx.close()


def test_defi_partage_par_lien(navigateur, site):  # critère 8
    ctx1, page1 = nouvelle_page(navigateur, site)
    lancer(page1, site, mode="defi", carte="france")
    page1.wait_for_selector("#lien")
    lien = page1.input_value("#lien")
    assert "/?defi=" in lien
    ctx2, page2 = nouvelle_page(navigateur, site)
    page2.goto(lien.replace(lien.split("/?")[0], site))
    page2.wait_for_selector("#rejoindre")
    assert "Classement" in page2.inner_text("main")
    page2.fill('input[name="pseudo"]', "Arthur")
    page2.click("#jouer")
    page2.wait_for_selector("#valider")
    ctx1.close(); ctx2.close()


def test_serie_de_pays(navigateur, site):  # critère 10
    ctx, page = nouvelle_page(navigateur, site)
    lancer(page, site, mode="serie", carte="france")
    page.wait_for_selector("#valider")
    poser_repere(page)
    page.click("#valider")
    page.wait_for_selector(".res-panneau h2")
    assert page.locator(".bravo, .rate").count() == 1
    ctx.close()


def test_exploration(navigateur, site):  # critère 12
    ctx, page = nouvelle_page(navigateur, site)
    lancer(page, site, mode="exploration", carte="europe")
    page.wait_for_selector("#reveler")
    assert page.locator("#valider").count() == 0 and page.locator("#hud-score").count() == 0
    page.click("#reveler")
    page.wait_for_selector(".res-panneau")
    assert "point" not in page.inner_text(".res-panneau").lower()
    page.click("#suite")
    page.wait_for_selector("#reveler")
    ctx.close()


def test_telephone(navigateur, site):  # critère 13 (affichage mobile simulé, pas un vrai téléphone)
    ctx, page = nouvelle_page(navigateur, site, viewport={"width": 390, "height": 800}, has_touch=True, is_mobile=True)
    lancer(page, site)
    page.wait_for_selector("#pano .pano-factice")
    assert page.is_visible("#bascule") and not page.is_visible("#mini-carte")
    page.tap("#bascule")
    page.wait_for_selector("#mini-carte", state="visible")
    boite = page.locator("#mini-carte").bounding_box()
    assert boite["width"] > 300 and boite["height"] > 300
    page.tap("#mini-carte")
    assert page.is_enabled("#valider")
    ctx.close()


def test_accueil_en_francais(navigateur, site):  # critère 14 (contrôle partiel ; relecture à faire à la main)
    ctx, page = nouvelle_page(navigateur, site)
    page.goto(site)
    page.wait_for_selector(".mode")
    texte = page.inner_text("body")
    for mot in ("Classique", "Défi du jour", "Série de pays", "Exploration", "Ton pseudo", "Chrono par manche"):
        assert mot in texte
    assert page.get_attribute("html", "lang") == "fr"
    ctx.close()


# ------------------------------------------------------------ étape 2 : comptes, profil, éditeur

def test_invite_voit_se_connecter_et_garde_son_pseudo(site, navigateur):  # critère 16
    ctx, page = nouvelle_page(navigateur, site)
    page.goto(site)
    page.wait_for_selector(".modes")
    assert page.locator("#connexion").is_visible()
    assert page.locator('input[name="pseudo"]').is_visible()
    page.goto(site + "/?profil=1")                       # un invité n'a pas de profil
    page.wait_for_timeout(300)
    assert not page.erreurs
    ctx.close()


def test_membre_profil_et_succes(site, navigateur):  # critères 16, 17, 18
    ctx, page = nouvelle_page(navigateur, site, extra_http_headers={"Remote-User": "thibault"})
    page.goto(site)
    page.wait_for_selector(".modes")
    assert not page.locator('input[name="pseudo"]').is_visible()          # le pseudo vient du compte
    assert "Joueur-" in page.locator(".barre").inner_text()
    page.click("#jouer")
    for i in range(5):
        page.wait_for_selector("#valider")
        poser_repere(page)
        page.click("#valider")
        page.wait_for_selector("#suite")
        if i == 4:
            assert "Première partie" in page.locator(".succes-gagne").inner_text()
        page.click("#suite")
    page.wait_for_selector("#recap-total")
    page.goto(site + "/?profil=1")
    page.wait_for_selector("#form-pseudo")
    assert "Parties terminées : 1" in page.inner_text("main")
    assert page.locator(".succes li.obtenu").count() >= 1
    page.fill('#form-pseudo input[name="pseudo"]', "Zoé")
    page.click('#form-pseudo button')
    page.wait_for_selector("h1:has-text('Zoé')")
    assert not page.erreurs
    ctx.close()


def test_editeur_reserve_a_l_admin_et_cree_une_carte(site, navigateur, monkeypatch):  # critère 20
    monkeypatch.setenv("OUSUISJE_ADMIN", "thibault")
    ctx, page = nouvelle_page(navigateur, site, extra_http_headers={"Remote-User": "leo"})
    page.goto(site + "/?editeur=1")
    page.wait_for_selector(".modes")                     # renvoyé à l'accueil
    assert page.locator(".editeur").count() == 0
    ctx.close()

    ctx, page = nouvelle_page(navigateur, site, extra_http_headers={"Remote-User": "thibault"})
    page.goto(site)
    page.wait_for_selector(".modes")
    page.click("text=Éditeur de cartes")
    page.wait_for_selector("#e-carte")
    page.fill("#e-nom", "Test éditeur")
    page.select_option("#e-mode", "zone")
    # un triangle en France : on le place avec la projection de la carte (clic aux pixels)
    boite = page.locator("#e-carte").bounding_box()
    page.evaluate("""() => { window.__c = document.querySelector('#e-carte'); }""")
    for dx, dy in ((0.48, 0.40), (0.52, 0.40), (0.50, 0.46)):
        page.mouse.click(boite["x"] + boite["width"] * dx, boite["y"] + boite["height"] * dy)
    assert page.locator("#e-compte").inner_text().startswith("3 sommet")
    page.fill("#e-nombre", "6")
    page.click("#e-creer")
    page.wait_for_selector("#e-ok:not([hidden]), #message:not([hidden])", timeout=20000)
    texte = page.locator("#e-ok").inner_text() + page.locator("#message").inner_text()
    assert "créée" in texte or "Seulement" in texte                      # créée, ou refus clair faute d'images
    assert not page.erreurs
    ctx.close()


# ------------------------------------------------------------ étape 3 : salons (WebSocket relayé par tests/ws_shim.py)

@pytest.fixture
def site_salon():
    import asyncio
    import uvicorn
    from serveur.app import creer_app
    from tests.ws_shim import serveur_relais

    def port_libre():
        s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p
    p_uvicorn, p_site = port_libre(), port_libre()
    app = creer_app()
    serveur = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=p_uvicorn, log_level="error"))
    etat = {}

    async def principal():
        relais = await asyncio.start_server(serveur_relais(app, p_uvicorn), "127.0.0.1", p_site)
        etat["pret"] = True
        await serveur.serve()
        relais.close()
    fil = threading.Thread(target=lambda: asyncio.run(principal()), daemon=True); fil.start()
    for _ in range(100):
        if serveur.started and etat.get("pret"):
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{p_site}"
    serveur.should_exit = True
    fil.join(5)


def entrer_salon(page, site, code, pseudo, spectateur=False):
    page.goto(site)
    page.wait_for_selector("#form-salon")
    page.fill('#form-salon input[name="code"]', code)
    if spectateur:
        page.check('#form-salon input[name="spectateur"]')
    page.click("#form-salon button")
    page.fill('#entree input[name="pseudo"]', pseudo)
    page.click("#entree button")


def test_salon_a_deux_avec_chat_et_spectateur(site_salon, navigateur):  # critères 21, 22, 26, 28
    site = site_salon
    ctx_a, a = nouvelle_page(navigateur, site)
    ctx_b, b = nouvelle_page(navigateur, site)
    ctx_s, s = nouvelle_page(navigateur, site)
    a.goto(site)
    a.wait_for_selector(".modes")
    a.click('.mode[data-mode="salon"]')
    a.select_option('select[name="carte"]', "drome-ardeche")
    a.click("#jouer")
    a.fill('#entree input[name="pseudo"]', "Hôte")
    a.click("#entree button")
    a.wait_for_selector("#code-salon")
    code = a.inner_text("#code-salon").strip()
    assert len(code) == 6
    assert a.locator("#lancer").is_disabled()                          # il faut 2 joueurs
    a.check("#verrou"); a.wait_for_timeout(200); a.uncheck("#verrou")  # verrouiller puis rouvrir marche

    entrer_salon(b, site, code.lower(), "Ami")
    entrer_salon(s, site, code, "Curieux", spectateur=True)
    a.wait_for_selector("#lancer:not([disabled])")
    a.wait_for_selector(".membres:has-text('Curieux')")
    assert "Curieux" in a.inner_text(".membres") and "spectateur" in a.inner_text(".membres")
    b.wait_for_selector(".membres")
    assert b.locator("#lancer").count() == 0                           # seul l'hôte lance

    # chat : l'ami écrit, tous le voient (hôte, spectateur) ; le texte reste du texte
    b.click("#chat-bascule")
    b.fill("#chat-texte", "Salut <b>tout le monde</b> https://exemple.fr")
    b.press("#chat-texte", "Enter")
    a.click("#chat-bascule")
    a.wait_for_selector("#chat-liste p")
    assert "<b>tout le monde</b>" in a.inner_text("#chat-liste")
    assert a.locator("#chat-liste a, #chat-liste b").count() == 0     # ni lien ni HTML
    s.click("#chat-bascule")
    s.wait_for_selector("#chat-liste p")

    # partie : les deux joueurs répondent, le spectateur voit l'image sans carte pour répondre
    a.click("#lancer")
    for p in (a, b):
        p.wait_for_selector("#valider")
    s.wait_for_selector("#pano")
    assert s.locator("#mini").count() == 0
    poser_repere(a, 0.5, 0.5); a.click("#valider")
    b.wait_for_selector("#hud-reponses:has-text('1 / 2')")
    poser_repere(b, 0.3, 0.3); b.click("#valider")
    for p in (a, b, s):
        p.wait_for_selector("#res-carte")
        assert "C'était" in p.inner_text(".res-panneau") and "Hôte" in p.inner_text(".res-panneau") and "Ami" in p.inner_text(".res-panneau")
    assert b.locator("#suivante").count() == 0
    a.click("#suivante")
    b.wait_for_selector("#valider")
    # reconnexion : l'ami recharge la page et retrouve sa place dans la manche
    b.reload()
    b.fill('#entree input[name="pseudo"]', "Ami")
    b.click("#entree button")
    b.wait_for_selector("#hud-reponses")
    for p in (a, b, s):
        assert not p.erreurs, p.erreurs
    for c in (ctx_a, ctx_b, ctx_s):
        c.close()


def creer_salon_ui(page, site, pseudo="Hôte"):
    page.goto(site)
    page.wait_for_selector(".modes")
    page.click('.mode[data-mode="salon"]')
    page.select_option('select[name="carte"]', "drome-ardeche")
    page.click("#jouer")
    page.fill('#entree input[name="pseudo"]', pseudo)
    page.click("#entree button")
    page.wait_for_selector("#code-salon")
    return page.inner_text("#code-salon").strip()


def test_duel_a_deux_navigateurs(site_salon, navigateur):  # critère 23
    site = site_salon
    ctx_a, a = nouvelle_page(navigateur, site)
    ctx_b, b = nouvelle_page(navigateur, site)
    code = creer_salon_ui(a, site)
    entrer_salon(b, site, code, "Rival")
    a.wait_for_selector("#lancer:not([disabled])")
    a.select_option("#r-mode", "duel")
    a.wait_for_selector("#aide-mode:has-text('6 000 points de vie')")
    assert "équipe" in a.inner_text(".membres")
    a.click("#lancer")
    for p in (a, b):
        p.wait_for_selector("#hud-pv .pv-cote")
        assert p.locator(".pv-cote").count() == 2 and p.inner_text("#hud-pv").count("000 PV") == 2
    poser_repere(a, 0.5, 0.5); a.click("#valider")
    b.wait_for_selector("#hud-urgence:has-text('le temps presse')")        # compte à rebours de 15 s pour l'autre
    poser_repere(b, 0.9, 0.9); b.click("#valider")
    for p in (a, b):
        p.wait_for_selector("#bloc-duel")
        assert "perd" in p.inner_text("#bloc-duel") or "Égalité" in p.inner_text("#bloc-duel")
    a.click("#suivante")
    b.wait_for_selector("#valider")
    assert not a.erreurs and not b.erreurs, (a.erreurs, b.erreurs)
    ctx_a.close(); ctx_b.close()


def test_bataille_royale_pays_a_trois(site_salon, navigateur):  # critère 25
    site = site_salon
    ctxs = [nouvelle_page(navigateur, site) for _ in range(3)]
    (_, a), (_, b), (_, c) = ctxs
    code = creer_salon_ui(a, site)
    entrer_salon(b, site, code, "Deux")
    entrer_salon(c, site, code, "Trois")
    a.wait_for_selector(".membres:has-text('Trois')")
    a.select_option("#r-mode", "br_pays")
    a.wait_for_selector("#lancer:not([disabled])")
    a.click("#lancer")
    for p in (a, b, c):
        p.wait_for_selector("#valider")
        assert "Essais restants" in p.inner_text("#hud-feedback") or p.inner_text("#hud-feedback") == ""
        poser_repere(p, 0.5, 0.5)
        p.click("#valider")
    for p in (a, b, c):
        p.wait_for_selector("#res-carte")
        assert "C'était" in p.inner_text(".res-panneau") and "trouvé" in p.inner_text(".res-panneau")
    a.click("#suivante")
    for p in (a, b, c):
        p.wait_for_selector("#valider")
        assert not p.erreurs, p.erreurs
    for _, p in ctxs:
        pass
    for ctx, _ in ctxs:
        ctx.close()
