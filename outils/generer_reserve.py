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
import math
import os
import random
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from serveur import config  # noqa: E402
from serveur.jeu import cartes, geo  # noqa: E402

URL = "https://maps.googleapis.com/maps/api/streetview/metadata"
DISTANCE_MIN_M = 300  # deux lieux d'une même réserve ne sont jamais voisins


class ArretClef(Exception):
    """Clé refusée ou quota dépassé : inutile de continuer."""


def interroger_google(lat, lon, rayon_m, cle):
    q = urllib.parse.urlencode({"location": f"{lat:.6f},{lon:.6f}", "radius": rayon_m, "source": "outdoor", "key": cle})
    for tentative in range(3):
        try:
            with urllib.request.urlopen(f"{URL}?{q}", timeout=20) as r:
                d = json.load(r)
        except OSError:
            time.sleep(1 + tentative)
            continue
        if d.get("status") in ("REQUEST_DENIED", "INVALID_REQUEST"):
            raise ArretClef(d.get("error_message") or d["status"])
        if d.get("status") == "OVER_QUERY_LIMIT":
            time.sleep(5)
            continue
        return d
    return {"status": "ERREUR"}


def point_au_hasard(carte, rng, graines):
    s, w, n, e = carte["bbox"]
    if carte["filtre"].get("celebre"):
        g = rng.choice(graines)
        d = rng.uniform(0, 1500) / 111_320            # à moins de 1,5 km du centre de la ville
        a = rng.uniform(0, 2 * math.pi)
        return g["lat"] + d * math.sin(a), g["lon"] + d * math.cos(a) / math.cos(math.radians(g["lat"]))
    lat = math.degrees(math.asin(rng.uniform(math.sin(math.radians(s)), math.sin(math.radians(n)))))  # uniforme en surface
    return lat, rng.uniform(w, e)


def generer(carte_id, nombre, interroger, pays, rng, existants=(), rayon_m=10_000, depuis=2014, essais_max=None,
            graines=()):
    """Renvoie la liste des nouveaux lieux [{pano_id, lat, lon, pays}]. `interroger(lat, lon, rayon)` → réponse Google."""
    carte = cartes.carte(carte_id)
    lieux = list(existants)
    deja = {l["pano_id"] for l in lieux}
    nouveaux = []
    essais = 0
    essais_max = essais_max or nombre * 60
    while len(nouveaux) < nombre and essais < essais_max:
        essais += 1
        lat, lon = point_au_hasard(carte, rng, graines)
        d = interroger(lat, lon, rayon_m)
        if d.get("status") != "OK" or d["pano_id"] in deja:
            continue
        if "Google" not in d.get("copyright", ""):
            continue                                   # photos d'utilisateurs : on garde la couverture officielle
        if int((d.get("date") or "0000")[:4]) < depuis:
            continue
        plat, plon = d["location"]["lat"], d["location"]["lng"]
        code = pays.code_du_point(plat, plon)
        if code is None or not cartes.appartient(carte, plat, plon, code, bool(carte["filtre"].get("celebre"))):
            continue
        if any(geo.distance_m(plat, plon, l["lat"], l["lon"]) < DISTANCE_MIN_M for l in lieux):
            continue
        lieu = {"pano_id": d["pano_id"], "lat": plat, "lon": plon, "pays": code}
        lieux.append(lieu); nouveaux.append(lieu); deja.add(d["pano_id"])
    return nouveaux


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
    choisies = [c["id"] for c in cartes.liste()] if a.toutes else [a.carte]
    if not choisies or None in choisies:
        sys.exit("Donne une carte ou --toutes. Cartes : " + ", ".join(c["id"] for c in cartes.liste()))
    graines = [g for g in json.loads((config.DONNEES / "graines.json").read_text(encoding="utf-8")) if g.get("celebre")]
    dossier = config.dossier_reserves()
    dossier.mkdir(parents=True, exist_ok=True)
    for cid in choisies:
        if cartes.carte(cid) is None:
            sys.exit(f"Carte inconnue : {cid}")
        chemin = dossier / f"{cid}.json"
        existants = json.loads(chemin.read_text(encoding="utf-8")) if chemin.is_file() else []
        petite = geo.diagonale_km(cartes.carte(cid)["bbox"]) < 1500
        rayon = a.rayon or (3000 if petite else 10_000)
        print(f"{cid} : {len(existants)} lieux déjà là, recherche de {a.nombre} de plus…", flush=True)
        try:
            nouveaux = generer(cid, a.nombre, lambda la, lo, r: (time.sleep(0.03), interroger_google(la, lo, r, cle))[1],
                               pays, random.Random(), existants, rayon, a.depuis, graines=graines)
        except ArretClef as e:
            sys.exit(f"Google refuse : {e}")
        tout = sorted(existants + nouveaux, key=lambda l: l["pano_id"])
        tmp = chemin.with_suffix(".tmp")
        tmp.write_text(json.dumps(tout, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        os.replace(tmp, chemin)
        print(f"  +{len(nouveaux)} (total {len(tout)}) → {chemin}")


if __name__ == "__main__":
    main()
