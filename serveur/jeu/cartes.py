"""Les cartes (zones de jeu) et leur filtre."""
import json
from functools import lru_cache

from .. import base, config
from . import geo


@lru_cache(maxsize=1)
def _toutes() -> dict:
    brut = json.loads((config.DONNEES / "cartes.json").read_text(encoding="utf-8"))
    cartes = {}
    for c in brut:
        c = dict(c)
        c.setdefault("diagonale_km", geo.diagonale_km(c["bbox"]))
        cartes[c["id"]] = c
    return cartes


def _perso(ligne) -> dict:
    return {"id": ligne["id"], "nom": ligne["nom"], "description": ligne["description"],
            "bbox": json.loads(ligne["bbox_json"]), "diagonale_km": ligne["diagonale_km"], "filtre": {},
            "perso": True, "archivee": bool(ligne["archivee"])}


def liste() -> list[dict]:
    """Cartes livrées, puis cartes personnalisées (sauf les archivées)."""
    with base.connexion() as c:
        perso = [_perso(r) for r in c.execute("SELECT * FROM cartes_perso WHERE archivee=0 ORDER BY cree_le")]
    return list(_toutes().values()) + perso


def carte(carte_id: str) -> dict | None:
    """Une carte par son identifiant. Une carte personnalisée archivée reste lisible (anciennes parties)."""
    if carte_id in _toutes():
        return _toutes()[carte_id]
    with base.connexion() as c:
        r = c.execute("SELECT * FROM cartes_perso WHERE id=?", (carte_id,)).fetchone()
    return _perso(r) if r else None


def appartient(c: dict, lat: float, lon: float, pays: str | None, celebre: bool = False) -> bool:
    """Un point est-il dans la carte ? (même règle pour les lieux de démonstration et le générateur)"""
    f = c["filtre"]
    s, w, n, e = c["bbox"]
    if not (s <= lat <= n and w <= lon <= e):
        return False
    if "pays" in f and pays not in f["pays"]:
        return False
    if c.get("zone") and not geo.dans_zone(lat, lon, c["zone"]):
        return False
    if f.get("celebre") and not celebre:
        return False
    return True


def publique(c: dict) -> dict:
    return {"id": c["id"], "nom": c["nom"], "description": c.get("description", ""), "bbox": c["bbox"],
            "perso": bool(c.get("perso"))}
