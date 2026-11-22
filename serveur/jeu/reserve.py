"""Constitution de réserves de lieux : tirage de points et vérification qu'une image de rue existe.

Utilisé par outils/generer_reserve.py (cartes livrées) et par l'éditeur de cartes (cartes personnalisées).
La vérification passe par l'API « Street View Metadata » de Google, gratuite et sans limite : elle ne charge aucune image.
"""
import json
import math
import time
import urllib.parse
import urllib.request

from .. import config
from . import cartes, geo

URL = "https://maps.googleapis.com/maps/api/streetview/metadata"
DISTANCE_MIN_M = 300  # deux lieux d'une même réserve ne sont jamais voisins


class ErreurReserve(Exception):
    """Vérification impossible (clé absente ou refusée)."""


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
            raise ErreurReserve(d.get("error_message") or d["status"])
        if d.get("status") == "OVER_QUERY_LIMIT":
            time.sleep(5)
            continue
        return d
    return {"status": "ERREUR"}


def _image_factice(lat, lon, rayon_m):
    """Mode essai : une « image » existe partout (la terre ferme est contrôlée plus loin par les contours de pays)."""
    return {"status": "OK", "pano_id": f"factice:{lat:.5f},{lon:.5f}", "copyright": "© Google", "date": "2024-01",
            "location": {"lat": lat, "lng": lon}}


def verificateur():
    """La fonction (lat, lon, rayon) → métadonnées qui convient au fournisseur d'images courant."""
    if config.fournisseur_images() == "google":
        cle = config.cle_google_outil()
        if not cle:
            raise ErreurReserve("La clé serveur Google (OUSUISJE_GOOGLE_KEY_OUTIL) n'est pas réglée.")
        return lambda lat, lon, rayon: interroger_google(lat, lon, rayon, cle)
    return _image_factice


def point_au_hasard(carte, rng, graines=()):
    s, w, n, e = carte["bbox"]
    if carte["filtre"].get("celebre"):
        g = rng.choice(graines)
        d = rng.uniform(0, 1500) / 111_320            # à moins de 1,5 km du centre de la ville
        a = rng.uniform(0, 2 * math.pi)
        return g["lat"] + d * math.sin(a), g["lon"] + d * math.cos(a) / math.cos(math.radians(g["lat"]))
    for _ in range(1000):
        lat = math.degrees(math.asin(rng.uniform(math.sin(math.radians(s)), math.sin(math.radians(n)))))  # uniforme en surface
        lon = rng.uniform(w, e)
        if not carte.get("zone") or geo.dans_zone(lat, lon, carte["zone"]):
            return lat, lon
    return lat, lon


def generer(carte, nombre, interroger, pays, rng, existants=(), rayon_m=10_000, depuis=2014, essais_max=None,
            graines=()):
    """Nouveaux lieux [{pano_id, lat, lon, pays}] pour `carte` (un dict de cartes.py, avec éventuellement une « zone»)."""
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
