"""Cartes personnalisées créées par l'administrateur : une liste de lieux cliqués, ou une zone tracée.

Seuls les points où une image de rue existe sont gardés. La carte devient ensuite jouable dans tous les modes.
"""
import json
import random
import re
import secrets
import unicodedata

from .. import base, config, horloge
from . import cartes, geo, reserve
from .moteur import ErreurJeu

MAX_POINTS = 200
MAX_SOMMETS = 100
MAX_NOMBRE = 150
MIN_LIEUX = 5               # une partie Classique tire 5 lieux différents
DIAGONALE_MIN_KM = 10       # une carte minuscule ne doit pas rendre le score impitoyable
RAYON_POINT_M = 150         # un point cliqué est « accroché » au panorama le plus proche dans ce rayon
RAYON_ZONE_M = 2000


def _slug(nom: str) -> str:
    s = unicodedata.normalize("NFKD", nom).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:30] or "carte"


def _coordonnees(p):
    try:
        lat, lon = float(p[0]), float(p[1])
    except (TypeError, ValueError, IndexError, KeyError):
        raise ErreurJeu(400, "Point invalide.")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ErreurJeu(400, "Point invalide.")
    return lat, lon


def _liste_points(brut, minimum, maximum, quoi):
    if not isinstance(brut, list) or not (minimum <= len(brut) <= maximum):
        raise ErreurJeu(400, f"{quoi} : entre {minimum} et {maximum} points attendus.")
    return [_coordonnees(p) for p in brut]


def creer(auteur: str, corps: dict) -> dict:
    nom = re.sub(r"\s+", " ", str(corps.get("nom") or "")).strip()[:40]
    if not nom:
        raise ErreurJeu(400, "Donne un nom à la carte.")
    description = re.sub(r"\s+", " ", str(corps.get("description") or "")).strip()[:120]
    mode = corps.get("mode")
    pays = geo.pays_disponibles(config.chemin_pays())
    if pays is None:
        raise ErreurJeu(503, "Le fichier des contours de pays (pays.geojson) est absent.")
    try:
        verifie = reserve.verificateur()
    except reserve.ErreurReserve as e:
        raise ErreurJeu(503, str(e))

    retenus, essais = [], 0
    try:
        if mode == "points":
            points = _liste_points(corps.get("points"), 1, MAX_POINTS, "Lieux")
            lats, lons = [p[0] for p in points], [p[1] for p in points]
            for lat, lon in points:
                essais += 1
                d = verifie(lat, lon, RAYON_POINT_M)
                if d.get("status") != "OK" or "Google" not in d.get("copyright", ""):
                    continue
                plat, plon = d["location"]["lat"], d["location"]["lng"]
                code = pays.code_du_point(plat, plon)
                if code and all(r["pano_id"] != d["pano_id"] for r in retenus):
                    retenus.append({"pano_id": d["pano_id"], "lat": plat, "lon": plon, "pays": code})
            marge = 0.01
        elif mode == "zone":
            zone = _liste_points(corps.get("zone"), 3, MAX_SOMMETS, "Zone")
            nombre = corps.get("nombre", 60)
            if isinstance(nombre, bool) or not isinstance(nombre, int) or not (MIN_LIEUX <= nombre <= MAX_NOMBRE):
                raise ErreurJeu(400, f"Nombre de lieux : entre {MIN_LIEUX} et {MAX_NOMBRE}.")
            lats, lons = [p[0] for p in zone], [p[1] for p in zone]
            tirage = {"bbox": [min(lats), min(lons), max(lats), max(lons)], "filtre": {}, "zone": zone}
            retenus = reserve.generer(tirage, nombre, verifie, pays, random.SystemRandom(), rayon_m=RAYON_ZONE_M,
                                      depuis=2014, essais_max=nombre * 25)
            essais = nombre * 25
            marge = 0
        else:
            raise ErreurJeu(400, "Mode inconnu : « points » ou « zone ».")
    except reserve.ErreurReserve as e:
        raise ErreurJeu(502, f"Google refuse la vérification : {e}")

    if len(retenus) < MIN_LIEUX:
        raise ErreurJeu(422, f"Seulement {len(retenus)} lieu(x) avec une image de rue : il en faut au moins {MIN_LIEUX}. "
                             "Rien n'a été créé.", retenus=len(retenus))
    bbox = [min(lats) - marge, min(lons) - marge, max(lats) + marge, max(lons) + marge]
    diagonale = max(geo.diagonale_km(bbox), DIAGONALE_MIN_KM)
    ident = f"perso-{_slug(nom)}-{secrets.token_hex(2)}"
    with base.connexion() as c:
        c.execute("INSERT INTO cartes_perso (id, nom, description, bbox_json, diagonale_km, auteur, cree_le) VALUES (?,?,?,?,?,?,?)",
                  (ident, nom, description, json.dumps(bbox), diagonale, auteur, horloge.maintenant()))
        c.executemany("INSERT OR IGNORE INTO lieux_perso VALUES (?,?,?,?,?)",
                      [(ident, r["pano_id"], r["lat"], r["lon"], r["pays"]) for r in retenus])
    return {"id": ident, "nom": nom, "retenus": len(retenus), "essais": essais}


def lister() -> list[dict]:
    with base.connexion() as c:
        return [{"id": r["id"], "nom": r["nom"], "description": r["description"], "lieux": r["n"], "auteur": r["auteur"]}
                for r in c.execute("SELECT k.*, (SELECT COUNT(*) FROM lieux_perso l WHERE l.carte_id=k.id) n "
                                   "FROM cartes_perso k WHERE archivee=0 ORDER BY cree_le DESC")]


def archiver(carte_id: str) -> None:
    """Retire la carte de la liste. Les parties et défis déjà créés continuent de fonctionner."""
    with base.connexion() as c:
        n = c.execute("UPDATE cartes_perso SET archivee=1 WHERE id=? AND archivee=0", (carte_id,)).rowcount
    if not n:
        raise ErreurJeu(404, "Carte personnalisée introuvable.")
