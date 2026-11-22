#!/usr/bin/env python3
"""Vérifie le fichier de contours de pays : chaque lieu de démonstration doit tomber dans son pays.

    python3 outils/verifier_pays.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from serveur import config  # noqa: E402
from serveur.jeu import geo  # noqa: E402


def verifier(pays, graines, tolerance_km=5):
    """Liste des lieux dont le pays trouvé n'est pas le pays attendu : [(nom, attendu, trouvé)]."""
    erreurs = []
    for g in graines:
        trouve = pays.code_du_point(g["lat"], g["lon"], tolerance_km)
        if trouve != g["pays"]:
            erreurs.append((g["nom"], g["pays"], trouve))
    return erreurs


def main():
    pays = geo.pays_disponibles(config.chemin_pays())
    if pays is None:
        sys.exit(f"Fichier absent : {config.chemin_pays()} (voir serveur/donnees/LISEZMOI.md)")
    graines = json.loads((config.DONNEES / "graines.json").read_text(encoding="utf-8"))
    erreurs = verifier(pays, graines)
    for nom, attendu, trouve in erreurs:
        print(f"  ✗ {nom} : attendu {attendu}, trouvé {trouve}")
    print(f"{len(graines) - len(erreurs)} lieux sur {len(graines)} dans le bon pays.")
    sys.exit(1 if erreurs else 0)


if __name__ == "__main__":
    main()
