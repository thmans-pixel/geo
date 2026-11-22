"""Calcul du score : 5000 × e^(−10 × d / D), arrondi ; 5000 sous 25 m."""
import math

POINTS_MAX = 5000
SEUIL_PARFAIT_M = 25


def points(distance_m: float, diagonale_km: float) -> int:
    if distance_m < SEUIL_PARFAIT_M:
        return POINTS_MAX
    d_km = distance_m / 1000
    return int(round(POINTS_MAX * math.exp(-10 * d_km / diagonale_km)))
