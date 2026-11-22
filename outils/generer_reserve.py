#!/usr/bin/env python3
"""Remplit la réserve de lieux d'une carte avec des panoramas Street View vérifiés.

La vérification utilise l'API « Street View Metadata » de Google, gratuite et sans limite
(https://developers.google.com/maps/billing-and-pricing/pricing : Street View Metadata = illimité).
Elle ne charge aucune image : seules les parties jouées consomment le quota de panoramas.

Utilisation (sur thnas, avec les contours de pays en place dans serveur/donnees/pays.geojson) :
    OUSUISJE_GOOGLE_KEY_OUTIL=... python3 outils/generer_reserve.py drome-ardeche --nombre 300
    OUSUISJE_GOOGLE_KEY_OUTIL=... python3 outils/generer_reserve.py --toutes --nombre 400

Le résultat est écrit dans donnees-locales/reserves/<carte>.json (ou OUSUISJE_RESERVES).
"""
import argparse
import json
import os
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from serveur import config  # noqa: E402
from serveur.jeu import cartes, geo  # noqa: E402
from serveur.jeu.reserve import ErreurReserve, generer, interroger_google  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("carte", nargs="?", help="identifiant de carte (monde, europe, france, drome-ardeche…)")
    ap.add_argument("--toutes", action="store_true", help="toutes les cartes")
    ap.add_argument("--nombre", type=int, default=300, help="nombre de lieux à ajouter par carte")
    ap.add_argument("--rayon", type=int, default=None, help="rayon de recherche autour du point tiré, en mètres")
    ap.add_argument("--depuis", type=int, default=2014, help="année minimale de la prise de vue")
    a = ap.parse_args()
    cle = config.cle_google_outil()
    if not cle:
        sys.exit("Il manque la clé serveur : OUSUISJE_GOOGLE_KEY_OUTIL=... python3 outils/generer_reserve.py ...\n"
                 "(ce n'est PAS la clé du navigateur : voir README.md)")
    pays = geo.pays_disponibles(config.chemin_pays())
    if pays is None:
        sys.exit(f"Il manque le fichier des contours de pays : {config.chemin_pays()}")
    choisies = [c["id"] for c in cartes.liste() if not c.get("perso")] if a.toutes else [a.carte]
    if not choisies or None in choisies:
        sys.exit("Donne une carte ou --toutes. Cartes : " + ", ".join(c["id"] for c in cartes.liste()))
    graines = [g for g in json.loads((config.DONNEES / "graines.json").read_text(encoding="utf-8")) if g.get("celebre")]
    dossier = config.dossier_reserves()
    dossier.mkdir(parents=True, exist_ok=True)
    for cid in choisies:
        if cartes.carte(cid) is None or cartes.carte(cid).get("perso"):
            sys.exit(f"Carte inconnue (ou personnalisée, créée par l'éditeur) : {cid}")
        chemin = dossier / f"{cid}.json"
        existants = json.loads(chemin.read_text(encoding="utf-8")) if chemin.is_file() else []
        petite = geo.diagonale_km(cartes.carte(cid)["bbox"]) < 1500
        rayon = a.rayon or (3000 if petite else 10_000)
        print(f"{cid} : {len(existants)} lieux déjà là, recherche de {a.nombre} de plus…", flush=True)
        try:
            nouveaux = generer(cartes.carte(cid), a.nombre, lambda la, lo, r: (time.sleep(0.03), interroger_google(la, lo, r, cle))[1],
                               pays, random.Random(), existants, rayon, a.depuis, graines=graines)
        except ErreurReserve as e:
            sys.exit(f"Google refuse : {e}")
        tout = sorted(existants + nouveaux, key=lambda l: l["pano_id"])
        tmp = chemin.with_suffix(".tmp")
        tmp.write_text(json.dumps(tout, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        os.replace(tmp, chemin)
        print(f"  +{len(nouveaux)} (total {len(tout)}) → {chemin}")


if __name__ == "__main__":
    main()
