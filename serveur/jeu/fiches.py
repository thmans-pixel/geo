"""Fiches découverte des pays."""
import json
from functools import lru_cache

from .. import config


@lru_cache(maxsize=1)
def _fiches() -> dict:
    return json.loads((config.DONNEES / "fiches_pays.json").read_text(encoding="utf-8"))


def drapeau(code: str | None) -> str:
    if not code or len(code) != 2 or not code.isalpha():
        return "🏳️"
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in code.upper())


def fiche(code: str | None) -> dict:
    f = _fiches().get(code or "")
    if f:
        return {"code": code, "drapeau": drapeau(code), **f}
    return {"code": code, "drapeau": drapeau(code), "nom": code or "Lieu inconnu",
            "capitale": None, "langues": [], "circulation": None, "indices": []}
