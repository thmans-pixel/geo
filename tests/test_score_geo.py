import math

from serveur.jeu import cartes, fiches, geo, lieux, score
from tests.conftest import DONNEES


def test_score_formule_et_seuil_de_25_m():  # critère 3
    D = 1000.0
    assert score.points(0, D) == 5000
    assert score.points(24.9, D) == 5000
    assert score.points(25, D) == round(5000 * math.exp(-10 * 0.025 / D))
    assert score.points(D * 1000 / 10, D) == 1839      # d = D/10 → 5000 × e⁻¹
    assert score.points(D * 1000, D) == 0              # d = D → 5000 × e⁻¹⁰ ≈ 0,2


def test_distance_connue():
    # Valence → Lyon : environ 100 km
    d = geo.distance_m(44.9334, 4.8924, 45.7640, 4.8357)
    assert 90_000 < d < 100_000
    assert geo.distance_m(10, 10, 10, 10) == 0


def test_diagonale_du_monde_est_celle_de_geoguessr():
    assert abs(cartes.carte("monde")["diagonale_km"] - 14916.862) < 0.01


def pays():
    return geo.pays_disponibles(DONNEES / "pays_test.geojson")


def test_pays_du_point():  # critère 10 (avec des contours de test)
    p = pays()
    assert p.code_du_point(44.9334, 4.8924) == "FR"     # Valence ; ISO_A2 = -99 → ISO_A2_EH
    assert p.code_du_point(46.2044, 6.1432) == "CH"     # Genève : dans le trou de la France
    assert p.code_du_point(41.9, 12.5) == "IT"          # Rome : multipolygone
    assert p.code_du_point(39.5, 9.0) == "IT"           # Sardaigne : second polygone
    assert p.code_du_point(0, 0) is None                # en mer


def test_tolerance_pres_de_la_cote():
    p = pays()
    assert p.code_du_point(41.95, -6.0) is None
    assert p.code_du_point(41.95, -5.1, tolerance_km=20) == "FR"  # à quelques km du rivage : repêché


def test_fichier_absent():
    assert geo.pays_disponibles(DONNEES / "nexiste-pas.geojson") is None


def test_tous_les_lieux_ont_une_fiche():  # critère 11
    for c in cartes.liste():
        for l in lieux.charger(c["id"]):
            f = fiches.fiche(l["pays"])
            assert f["capitale"] and f["langues"] and f["circulation"] and len(f["indices"]) >= 2, l["pays"]


def test_fiche_trois_pays():
    assert fiches.fiche("JP")["circulation"] == "gauche"
    assert fiches.fiche("FR")["drapeau"] == "🇫🇷"
    assert fiches.fiche("US")["nom"] == "États-Unis"
    assert fiches.fiche("ZZ")["nom"] == "ZZ"   # inconnu : ne plante pas


def test_chaque_carte_a_assez_de_lieux():
    for c in cartes.liste():
        assert len(lieux.charger(c["id"])) >= 10, c["id"]
