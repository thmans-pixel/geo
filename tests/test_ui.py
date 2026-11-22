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
