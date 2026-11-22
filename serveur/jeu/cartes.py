"""Les cartes (zones de jeu) et leur filtre."""
import json
from functools import lru_cache

from .. import config
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


def liste() -> list[dict]:
    return list(_toutes().values())


def carte(carte_id: str) -> dict | None:
    return _toutes().get(carte_id)


def appartient(c: dict, lat: float, lon: float, pays: str | None, celebre: bool = False) -> bool:
    """Un point est-il dans la carte ? (même règle pour les lieux de démonstration et le générateur)"""
    f = c["filtre"]
    s, w, n, e = c["bbox"]
    if not (s <= lat <= n and w <= lon <= e):
        return False
    if "pays" in f and pays not in f["pays"]:
        return False
    if f.get("celebre") and not celebre:
        return False
    return True


def publique(c: dict) -> dict:
    return {"id": c["id"], "nom": c["nom"], "description": c.get("description", ""), "bbox": c["bbox"]}
