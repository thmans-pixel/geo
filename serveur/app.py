"""Application web « Où suis-je ? » : API JSON + pages statiques."""
import secrets
from pathlib import Path

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from . import config
from .jeu import cartes, fiches, lieux, moteur
from .jeu.moteur import ErreurJeu

WEB = Path(__file__).resolve().parent.parent / "web"


class Joueur(BaseHTTPMiddleware):
    """Identifiant anonyme de navigateur (cookie) : relie un joueur à ses parties."""

    async def dispatch(self, request, call_next):
        ident = request.cookies.get("joueur_id")
        neuf = not ident or len(ident) > 64
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
    return {"images": config.fournisseur_images(), "cle_google": config.cle_google()}


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
                                b.get("defi_id"))
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
    from . import base, horloge
    with base.connexion() as c:
        moteur._defi_jour(c)
    return moteur.infos_defi(request.state.joueur_id, f"jour-{horloge.jour_paris()}")


@_json
async def api_fiche(request):
    return fiches.fiche(request.path_params["code"].upper()[:2])


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
            Mount("/", StaticFiles(directory=WEB, html=True), name="web"),
        ],
        middleware=[Middleware(Joueur)],
    )


app = creer_app()
