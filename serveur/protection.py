"""Protections pour la mise en ligne : en-têtes de sécurité, requêtes de modification contrôlées, limites de débit, purge."""
import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from . import base, config, horloge

EN_TETES = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",   # origine seule : jamais le ?salon=CODE
    "X-Frame-Options": "DENY",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=(), payment=()",
}


def ip_client(conn) -> str:
    """Adresse du visiteur. Derrière nginx (même machine), nginx la met dans X-Real-IP ; sinon on prend la connexion."""
    hote = conn.client.host if conn.client else "?"
    if hote in ("127.0.0.1", "::1"):
        return (conn.headers.get("x-real-ip") or hote)[:64]
    return hote


class Limiteur:
    """Fenêtre glissante en mémoire : au plus `maxi` événements par `fenetre` secondes et par clé."""

    def __init__(self):
        self._evts = defaultdict(deque)

    def autoriser(self, cle, maxi, fenetre) -> bool:
        maintenant = time.monotonic()      # l'horloge de jeu peut être truquée par les tests ; ici on veut le temps réel
        q = self._evts[cle]
        while q and maintenant - q[0] > fenetre:
            q.popleft()
        if len(q) >= maxi:
            return False
        q.append(maintenant)
        if len(self._evts) > 20000:        # ménage : on oublie les clés vides
            for k in [k for k, v in self._evts.items() if not v]:
                del self._evts[k]
        return True

    def reinitialiser(self):
        self._evts.clear()


limiteur = Limiteur()

# (méthode, début de chemin) → (nombre, secondes) par adresse
LIMITES = {("POST", "/api/parties"): (60, 60), ("POST", "/api/defis"): (30, 60), ("POST", "/api/salons"): (10, 60)}


def _avec_en_tetes(reponse):
    for k, v in EN_TETES.items():
        reponse.headers.setdefault(k, v)
    return reponse


class Protection(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        chemin = request.url.path
        if request.method in ("POST", "PUT", "PATCH", "DELETE") and chemin.startswith("/api/"):
            # un site tiers ne peut pas poser cet en-tête sans autorisation : les envois depuis une autre page sont refusés
            if request.headers.get("X-Requete") != "ou-suis-je":
                return _avec_en_tetes(JSONResponse({"erreur": "Requête refusée."}, status_code=400))
        for (methode, debut), (maxi, fenetre) in LIMITES.items():
            if request.method == methode and chemin.startswith(debut):
                if not limiteur.autoriser(f"{methode}{debut}:{ip_client(request)}", maxi, fenetre):
                    return _avec_en_tetes(JSONResponse({"erreur": "Trop de demandes : attends un peu."},
                                                       status_code=429, headers={"Retry-After": "30"}))
        return _avec_en_tetes(await call_next(request))


derniere_purge = {"le": None}


def purger() -> dict:
    """Supprime les vieilles parties (données de jeu seulement : comptes, succès et records restent)."""
    now = horloge.maintenant()
    limite_invites = now - config.duree_garde_invites_jours() * 86400
    limite_comptes = now - config.duree_garde_comptes_jours() * 86400
    with base.connexion() as c:
        anciennes = [r["id"] for r in c.execute(
            "SELECT id FROM parties WHERE (compte IS NULL AND cree_le < ?) OR (compte IS NOT NULL AND cree_le < ?)",
            (limite_invites, limite_comptes))]
        for i in range(0, len(anciennes), 500):
            lot = anciennes[i:i + 500]
            marques = ",".join("?" * len(lot))
            c.execute(f"DELETE FROM manches WHERE partie_id IN ({marques})", lot)
            c.execute(f"DELETE FROM parties WHERE id IN ({marques})", lot)
        c.execute("DELETE FROM defis WHERE cree_le < ? AND id NOT LIKE 'jour-%' "
                  "AND id NOT IN (SELECT defi_id FROM parties WHERE defi_id IS NOT NULL)", (limite_invites,))
    derniere_purge["le"] = now
    return {"parties_supprimees": len(anciennes)}
