import random

from outils import generer_reserve as g
from serveur.jeu import geo
from tests.conftest import DONNEES


def faux_google(lat, lon, rayon):
    """Répond comme l'API de métadonnées : un panorama partout en France, rien ailleurs."""
    if 42 <= lat <= 51 and -5 <= lon <= 8:
        return {"status": "OK", "pano_id": f"P{lat:.4f}_{lon:.4f}", "copyright": "© Google", "date": "2022-06",
                "location": {"lat": lat, "lng": lon}}
    return {"status": "ZERO_RESULTS"}


def test_generer_une_reserve():
    pays = geo.pays_disponibles(DONNEES / "pays_test.geojson")
    lieux = g.generer("france", 25, faux_google, pays, random.Random(1))
    assert len(lieux) == 25 and len({l["pano_id"] for l in lieux}) == 25
    assert all(l["pays"] == "FR" for l in lieux)
    for i, a in enumerate(lieux):                                   # jamais deux lieux voisins
        for b in lieux[i + 1:]:
            assert geo.distance_m(a["lat"], a["lon"], b["lat"], b["lon"]) >= g.DISTANCE_MIN_M


def test_filtres_de_la_reserve():
    pays = geo.pays_disponibles(DONNEES / "pays_test.geojson")

    def photos_utilisateurs(lat, lon, rayon):
        return {**faux_google(lat, lon, rayon), "copyright": "© Jean Dupont"}

    def vieilles(lat, lon, rayon):
        return {**faux_google(lat, lon, rayon), "date": "2009-05"}

    assert g.generer("france", 5, photos_utilisateurs, pays, random.Random(1), essais_max=50) == []
    assert g.generer("france", 5, vieilles, pays, random.Random(1), essais_max=50) == []
    assert g.generer("drome-ardeche", 5, faux_google, pays, random.Random(1))[0]["lat"] < 45.4   # reste dans la carte
