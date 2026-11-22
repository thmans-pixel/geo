"""Les lieux jouables : réserve Street View (google) ou lieux de démonstration (factice)."""
import json
import re
import unicodedata
import zlib

from .. import config
from . import cartes


class PasDeLieux(Exception):
    """Aucun lieu (assez) pour cette carte."""


def _slug(nom: str) -> str:
    s = unicodedata.normalize("NFKD", nom).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def _lire(chemin):
    return json.loads(chemin.read_text(encoding="utf-8"))


def charger(carte_id: str) -> list[dict]:
    """Tous les lieux d'une carte, triés par identifiant (ordre stable)."""
    carte = cartes.carte(carte_id)
    if carte is None:
        raise PasDeLieux("Carte inconnue.")
    lieux = []
    if config.fournisseur_images() == "google":
        chemin = config.dossier_reserves() / f"{carte_id}.json"
        if not chemin.is_file():
            raise PasDeLieux(f"La réserve de lieux de la carte « {carte['nom']} » n'existe pas encore "
                             "(lancer outils/generer_reserve.py).")
        for r in _lire(chemin):
            lieux.append({"id": r["pano_id"], "lat": r["lat"], "lon": r["lon"], "pays": r.get("pays"),
                          "image": {"type": "google", "pano_id": r["pano_id"]}})
    else:
        for g in _lire(config.DONNEES / "graines.json"):
            if cartes.appartient(carte, g["lat"], g["lon"], g["pays"], g.get("celebre", False)):
                ident = "graine:" + _slug(g["nom"])
                lieux.append({"id": ident, "lat": g["lat"], "lon": g["lon"], "pays": g["pays"],
                              "image": {"type": "factice", "motif": zlib.crc32(ident.encode()) % 360}})
    lieux.sort(key=lambda l: l["id"])
    return lieux


def tirer(carte_id: str, n: int, rng) -> list[dict]:
    lieux = charger(carte_id)
    if len(lieux) < n:
        raise PasDeLieux(f"Pas assez de lieux sur cette carte ({len(lieux)} sur {n} nécessaires).")
    return rng.sample(lieux, n)


def tirer_un(carte_id: str, exclus: set, rng) -> dict:
    lieux = charger(carte_id)
    if not lieux:
        raise PasDeLieux("Aucun lieu sur cette carte.")
    restants = [l for l in lieux if l["id"] not in exclus] or lieux
    return rng.choice(restants)
