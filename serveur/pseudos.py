"""Pseudos refusés (le jeu est ouvert aux enfants). Liste volontairement courte ; elle se complète sans toucher au code :
mettre un mot par ligne dans le fichier désigné par OUSUISJE_PSEUDOS_REFUSES (ou donnees-locales/pseudos_refuses.txt)."""
import os
import unicodedata
from pathlib import Path

# Mots longs et sans ambiguïté : refusés même collés à d'autres lettres (« xxputainxx »).
DE_BASE = [
    "putain", "merde", "connard", "connasse", "salope", "encule", "couille", "foutre", "tapette", "nigger",
    "hitler", "bitch", "porno", "branler", "chatte",
]
# Mots courts : refusés seulement comme mot entier (« Violette », « Veronique », « Habite » restent permis).
MOTS_ENTIERS = [
    "pute", "nique", "niquer", "batard", "bite", "negre", "nazi", "fuck", "shit", "pedo", "viol", "sexe", "sucer",
    "enculer",
]


def _norm(m):
    return "".join(c for c in unicodedata.normalize("NFKD", m.lower()) if c.isalpha() and ord(c) < 128)


def mots_refuses() -> list[str]:
    mots = [_norm(m) for m in DE_BASE]
    chemin = Path(os.environ.get("OUSUISJE_PSEUDOS_REFUSES", "donnees-locales/pseudos_refuses.txt"))
    if chemin.is_file():
        mots += [_norm(l) for l in chemin.read_text(encoding="utf-8").splitlines() if _norm(l)]
    return [m for m in mots if m]


def mots_entiers() -> list[str]:
    return [_norm(m) for m in MOTS_ENTIERS]
