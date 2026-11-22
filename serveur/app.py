"""Application web « Où suis-je ? » : API JSON + pages statiques."""
import asyncio
import contextlib
import json
import re
import secrets
from pathlib import Path

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route, WebSocketRoute
from starlette.staticfiles import StaticFiles

from . import base, config, horloge, identite, salons
from .jeu import cartes, cartes_perso, fiches, lieux, moteur, profil, progression
from .jeu.moteur import ErreurJeu

COOKIE_VALIDE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")   # jamais « c:… » : cette forme est réservée aux comptes
WEB = Path(__file__).resolve().parent.parent / "web"


class Joueur(BaseHTTPMiddleware):
    """Identifiant anonyme de navigateur (cookie) : relie un joueur à ses parties."""

    async def dispatch(self, request, call_next):
        ident = request.cookies.get("joueur_id")
        neuf = not ident or not COOKIE_VALIDE.match(ident)
        if neuf:
            ident = secrets.token_urlsafe(12)
        request.state.joueur_id = ident
        reponse = await call_next(request)
        if neuf:
            reponse.set_cookie("joueur_id", ident, max_age=3600 * 24 * 365, httponly=True, samesite="lax")
        return reponse


async def _corps(request) -> dict:
    try:
        corps = await request.json()
    except Exception:
        return {}
    return corps if isinstance(corps, dict) else {}


def _json(f):
    """Convertit les ErreurJeu en réponses JSON {« erreur »: …}."""
    async def route(request):
        try:
            return JSONResponse(await f(request), headers={"Cache-Control": "no-store"})
        except ErreurJeu as e:
            return JSONResponse({"erreur": e.message, **e.extra}, status_code=e.statut)
    return route


@_json
async def api_config(request):
    return {"images": config.fournisseur_images(), "cle_google": config.cle_google(),
            "url_connexion": config.url_connexion()}


@_json
async def api_cartes(request):
    sortie = []
    for c in cartes.liste():
        try:
            n = len(lieux.charger(c["id"]))
        except lieux.PasDeLieux:
            n = 0
        sortie.append({**cartes.publique(c), "nb_lieux": n})
    return {"cartes": sortie}


@_json
async def api_creer_partie(request):
    b = await _corps(request)
    ident = moteur.creer_partie(request.state.joueur_id, b.get("mode"), b.get("carte"),
                                b.get("contrainte", "libre"), b.get("chrono", 0), b.get("pseudo", ""),
                                b.get("defi_id"), identite.compte(request))
    return {"id": ident}


@_json
async def api_etat(request):
    return moteur.etat(request.state.joueur_id, request.path_params["id"])


@_json
async def api_reponse(request):
    b = await _corps(request)
    return moteur.repondre(request.state.joueur_id, request.path_params["id"], b.get("lat"), b.get("lon"))


@_json
async def api_reveler(request):
    return moteur.reveler(request.state.joueur_id, request.path_params["id"])


@_json
async def api_suivante(request):
    moteur.suivante(request.state.joueur_id, request.path_params["id"])
    return {"ok": True}


@_json
async def api_recap(request):
    return moteur.recap(request.state.joueur_id, request.path_params["id"])


@_json
async def api_creer_defi(request):
    b = await _corps(request)
    return moteur.creer_defi(b.get("carte"), b.get("contrainte", "libre"), b.get("chrono", 0))


@_json
async def api_defi(request):
    return moteur.infos_defi(request.state.joueur_id, request.path_params["id"])


@_json
async def api_defi_du_jour(request):
    with base.connexion() as c:
        moteur._defi_jour(c)
    return moteur.infos_defi(request.state.joueur_id, f"jour-{horloge.jour_paris()}")


@_json
async def api_fiche(request):
    return fiches.fiche(request.path_params["code"].upper()[:2])


def _verifier_requete(request):
    """Les actions qui modifient un compte ou une carte exigent un en-tête qu'un autre site ne peut pas poser
    sans autorisation (protège contre les requêtes envoyées depuis une page tierce)."""
    if request.headers.get("X-Requete") != "ou-suis-je":
        raise ErreurJeu(400, "Requête refusée.")


def _admin(request) -> dict:
    cpt = identite.compte(request)
    if cpt is None:
        raise ErreurJeu(401, "Connexion nécessaire.")
    if not cpt["admin"]:
        raise ErreurJeu(403, "Réservé à l'administrateur.")
    return cpt


@_json
async def api_moi(request):
    cpt = identite.compte(request)
    if cpt is None:
        return {"connecte": False, "url_connexion": config.url_connexion()}
    return {"connecte": True, **cpt, "niveau": progression.etat_niveau(cpt["xp"])}


@_json
async def api_pseudo(request):
    _verifier_requete(request)
    cpt = identite.compte(request)
    if cpt is None:
        raise ErreurJeu(401, "Connexion nécessaire.")
    pseudo = moteur.nettoyer_pseudo((await _corps(request)).get("pseudo"))
    if not pseudo:
        raise ErreurJeu(400, "Pseudo vide ou invalide.")
    with base.connexion() as c:
        c.execute("UPDATE comptes SET pseudo=? WHERE identifiant=?", (pseudo, cpt["identifiant"]))
    return {"pseudo": pseudo}


@_json
async def api_profil(request):
    cpt = identite.compte(request)
    if cpt is None:
        raise ErreurJeu(401, "Connexion nécessaire.")
    return profil.profil(cpt)


@_json
async def api_classements(request):
    return profil.classements(request.query_params.get("carte", "monde"))


@_json
async def api_admin_cartes(request):
    _admin(request)
    return {"cartes": cartes_perso.lister()}


@_json
async def api_admin_creer_carte(request):
    _verifier_requete(request)
    cpt = _admin(request)
    corps = await _corps(request)
    # La vérification interroge Google (lent) : hors de la boucle pour ne pas bloquer les autres joueurs.
    return await asyncio.to_thread(cartes_perso.creer, cpt["identifiant"], corps)


@_json
async def api_admin_archiver(request):
    _verifier_requete(request)
    _admin(request)
    cartes_perso.archiver(request.path_params["id"])
    return {"ok": True}


def _cle_et_pseudo(conn, pseudo_brut):
    """Qui est là ? Le compte (clé « c:… ») ou, pour un invité, son cookie de navigateur."""
    cpt = identite.compte(conn)
    if cpt:
        return "c:" + cpt["identifiant"], cpt["pseudo"]
    cookie = getattr(conn.state, "joueur_id", None) or conn.cookies.get("joueur_id")
    if not cookie or not COOKIE_VALIDE.match(cookie):
        raise ErreurJeu(401, "Ouvre d'abord le site (cookie manquant).")
    return cookie, moteur.nettoyer_pseudo(pseudo_brut)


@_json
async def api_creer_salon(request):
    _verifier_requete(request)
    cle, _ = _cle_et_pseudo(request, "")
    b = await _corps(request)
    s = salons.gestionnaire.creer(cle, b.get("carte"), b.get("contrainte", "libre"), b.get("chrono", 0))
    return {"code": s.code}


@_json
async def api_salon(request):
    """Le salon existe-t-il ? (pour dire « code inconnu » avant d'ouvrir la liaison temps réel)"""
    s = salons.gestionnaire.trouver(request.path_params["code"])
    return {"code": s.code}


class Liaison:
    def __init__(self, ws):
        self.ws = ws

    async def envoyer(self, message):
        await self.ws.send_json(message)

    async def fermer(self):
        await self.ws.close()


def _origine_permise(ws) -> bool:
    """Un WebSocket n'est pas protégé par les règles du navigateur : on exige que la page vienne de ce site."""
    origine, hote = ws.headers.get("origin", ""), ws.headers.get("host", "")
    return bool(origine) and origine.split("://", 1)[-1] == hote


async def ws_salon(ws):
    if not _origine_permise(ws):
        await ws.close(code=4403)
        return
    try:
        salon = salons.gestionnaire.trouver(ws.path_params["code"])
        cle, _ = _cle_et_pseudo(ws, "")
    except ErreurJeu as e:
        await ws.accept()
        await ws.send_json({"t": "erreur", "message": e.message, "fatale": True})
        await ws.close(code=4404)
        return
    await ws.accept()
    liaison = Liaison(ws)
    # Le pseudo et le rôle arrivent dans le premier message, pas dans l'adresse : les journaux d'accès n'y voient rien.
    try:
        premier = json.loads(await asyncio.wait_for(ws.receive_text(), 10))
        if not isinstance(premier, dict) or premier.get("t") != "entrer":
            raise ValueError
    except Exception:
        await ws.close(code=4400)
        return
    cpt = identite.compte(ws)
    pseudo = cpt["pseudo"] if cpt else moteur.nettoyer_pseudo(premier.get("pseudo"))
    role = "spectateur" if premier.get("role") == "spectateur" else "joueur"
    try:
        membre = salon.rejoindre(cle, pseudo, role, liaison)
    except ErreurJeu as e:
        await ws.send_json({"t": "erreur", "message": e.message, "fatale": True})
        await ws.close(code=4409)
        return
    try:
        await salon.diffuser()
        while True:
            texte = await ws.receive_text()
            if len(texte) > 2048:
                continue
            try:
                await salon.traiter(membre, json.loads(texte))
            except (ValueError, ErreurJeu) as e:
                await liaison.envoyer({"t": "erreur", "message": e.message if isinstance(e, ErreurJeu) else "Message invalide."})
    except Exception:          # déconnexion (WebSocketDisconnect) ou liaison cassée
        pass
    finally:
        salon.deconnecter(membre, liaison)
        try:
            await salon.diffuser()
        except Exception:
            pass


@contextlib.asynccontextmanager
async def _vie(app):
    tache = asyncio.create_task(salons.gestionnaire.boucle())
    try:
        yield
    finally:
        tache.cancel()


def creer_app() -> Starlette:
    return Starlette(
        routes=[
            Route("/api/config", api_config),
            Route("/api/cartes", api_cartes),
            Route("/api/parties", api_creer_partie, methods=["POST"]),
            Route("/api/parties/{id}", api_etat),
            Route("/api/parties/{id}/reponse", api_reponse, methods=["POST"]),
            Route("/api/parties/{id}/reveler", api_reveler, methods=["POST"]),
            Route("/api/parties/{id}/suivante", api_suivante, methods=["POST"]),
            Route("/api/parties/{id}/recap", api_recap),
            Route("/api/defis", api_creer_defi, methods=["POST"]),
            Route("/api/defis/{id}", api_defi),
            Route("/api/defi-du-jour", api_defi_du_jour),
            Route("/api/pays/{code}", api_fiche),
            Route("/api/salons", api_creer_salon, methods=["POST"]),
            Route("/api/salons/{code}", api_salon),
            WebSocketRoute("/ws/salons/{code}", ws_salon),
            Route("/api/moi", api_moi),
            Route("/api/moi/pseudo", api_pseudo, methods=["POST"]),
            Route("/api/moi/profil", api_profil),
            Route("/api/classements", api_classements),
            Route("/api/admin/cartes", api_admin_cartes),
            Route("/api/admin/cartes", api_admin_creer_carte, methods=["POST"]),
            Route("/api/admin/cartes/{id}", api_admin_archiver, methods=["DELETE"]),
            Mount("/", StaticFiles(directory=WEB, html=True), name="web"),
        ],
        middleware=[Middleware(Joueur)],
        lifespan=_vie,
    )


app = creer_app()
