"""Géographie : distances et pays d'un point (contours Natural Earth, Python pur)."""
import json
import math
from functools import lru_cache
from pathlib import Path

RAYON_TERRE_M = 6_371_008.8


def distance_m(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * RAYON_TERRE_M * math.asin(min(1.0, math.sqrt(a)))


def diagonale_km(bbox) -> float:
    s, w, n, e = bbox
    return distance_m(s, w, n, e) / 1000


def _dans_anneau(lat, lon, anneau) -> bool:
    dedans = False
    j = len(anneau) - 1
    for i in range(len(anneau)):
        xi, yi = anneau[i][0], anneau[i][1]
        xj, yj = anneau[j][0], anneau[j][1]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            dedans = not dedans
        j = i
    return dedans


def _dans_polygone(lat, lon, polygone) -> bool:
    """polygone = [anneau extérieur, *trous], points en [lon, lat]."""
    if not _dans_anneau(lat, lon, polygone[0]):
        return False
    return not any(_dans_anneau(lat, lon, trou) for trou in polygone[1:])


def _code(proprietes) -> str | None:
    for cle in ("ISO_A2_EH", "ISO_A2", "iso_a2", "WB_A2"):
        v = proprietes.get(cle)
        if v and v != "-99":
            return v
    return None


class Pays:
    def __init__(self, geojson: dict):
        self.formes = []  # (code, bbox(w,s,e,n), polygones)
        for f in geojson["features"]:
            code = _code(f.get("properties", {}))
            g = f["geometry"]
            if not code or not g:
                continue
            polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
            xs = [p[0] for poly in polys for p in poly[0]]
            ys = [p[1] for poly in polys for p in poly[0]]
            self.formes.append((code, (min(xs), min(ys), max(xs), max(ys)), polys))

    def _exact(self, lat, lon) -> str | None:
        for code, (w, s, e, n), polys in self.formes:
            if w <= lon <= e and s <= lat <= n and any(_dans_polygone(lat, lon, p) for p in polys):
                return code
        return None

    def code_du_point(self, lat, lon, tolerance_km: float = 0) -> str | None:
        """Code ISO du pays du point ; en mer, cherche dans un rayon de `tolerance_km`."""
        code = self._exact(lat, lon)
        if code or tolerance_km <= 0:
            return code
        dlat = tolerance_km / 111.32
        dlon = tolerance_km / (111.32 * max(0.05, math.cos(math.radians(lat))))
        for k in range(8):
            a = k * math.pi / 4
            code = self._exact(max(-90, min(90, lat + dlat * math.sin(a))), lon + dlon * math.cos(a))
            if code:
                return code
        return None


@lru_cache(maxsize=4)
def _charger(chemin: str, mtime: float) -> Pays:
    return Pays(json.loads(Path(chemin).read_text(encoding="utf-8")))


def pays_disponibles(chemin: Path) -> Pays | None:
    """Les contours, ou None si le fichier pays.geojson n'est pas là."""
    chemin = Path(chemin)
    if not chemin.is_file():
        return None
    return _charger(str(chemin), chemin.stat().st_mtime)
