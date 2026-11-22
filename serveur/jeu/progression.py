"""Expérience, niveaux et succès des comptes. Les invités n'ont ni l'un ni l'autre."""
from .. import horloge

SUCCES = {
    "premiere_partie": ("Première partie", "Terminer une partie."),
    "parfait": ("Pile au but", "Marquer 5 000 points sur une manche."),
    "score_20000": ("Globe-trotteur", "Marquer 20 000 points ou plus sur une partie de 5 manches."),
    "serie_5": ("Série de 5", "Trouver 5 pays de suite en Série de pays."),
    "serie_10": ("Série de 10", "Trouver 10 pays de suite en Série de pays."),
    "pays_10": ("10 pays trouvés", "Trouver 10 pays différents en Série de pays."),
    "pays_50": ("50 pays trouvés", "Trouver 50 pays différents en Série de pays."),
    "explorateur": ("Explorateur", "Révéler 20 lieux en mode Exploration."),
}
BONUS_SUCCES_XP = 50
SCORE_MODES = "('classique','defi','defi_jour')"


def seuil(niveau: int) -> int:
    """XP nécessaire pour atteindre ce niveau : 0, 100, 400, 900…"""
    return 100 * (niveau - 1) ** 2


def niveau(xp: int) -> int:
    n = 1
    while seuil(n + 1) <= xp:
        n += 1
    return n


def etat_niveau(xp: int) -> dict:
    n = niveau(xp)
    return {"niveau": n, "xp": xp, "xp_debut": seuil(n), "xp_suivant": seuil(n + 1)}


def _obtenus(c, ident) -> set:
    return {r["code"] for r in c.execute("SELECT code FROM succes WHERE identifiant=?", (ident,))}


def _attribuer(c, ident, codes) -> list[dict]:
    """Enregistre les succès nouvellement obtenus (+ bonus d'XP) et les renvoie pour affichage."""
    deja = _obtenus(c, ident)
    nouveaux = [k for k in codes if k not in deja]
    for k in nouveaux:
        c.execute("INSERT INTO succes (identifiant, code, obtenu_le) VALUES (?,?,?)", (ident, k, horloge.maintenant()))
    if nouveaux:
        c.execute("UPDATE comptes SET xp = xp + ? WHERE identifiant=?", (BONUS_SUCCES_XP * len(nouveaux), ident))
    return [{"code": k, "nom": SUCCES[k][0]} for k in nouveaux]


def _succes_a_jour(c, ident, p) -> list[str]:
    ok = ["premiere_partie"]
    if c.execute(f"SELECT 1 FROM manches m JOIN parties q ON q.id=m.partie_id WHERE q.compte=? AND q.mode IN {SCORE_MODES} "
                 "AND m.points >= 5000 LIMIT 1", (ident,)).fetchone():
        ok.append("parfait")
    if p["mode"] in ("classique", "defi", "defi_jour") and p["nb_manches"] == 5 and p["total"] >= 20000:
        ok.append("score_20000")
    if p["mode"] == "serie":
        for seuil_serie, code in ((5, "serie_5"), (10, "serie_10")):
            if p["total"] >= seuil_serie:
                ok.append(code)
    nb_pays = c.execute("SELECT COUNT(DISTINCT json_extract(m.lieu_json,'$.pays')) FROM manches m JOIN parties q ON q.id=m.partie_id "
                        "WHERE q.compte=? AND q.mode='serie' AND m.juste=1", (ident,)).fetchone()[0]
    ok += [code for n, code in ((10, "pays_10"), (50, "pays_50")) if nb_pays >= n]
    return ok


def fin_de_partie(c, partie_id) -> list[dict]:
    """À appeler quand une partie vient de se terminer. Ne fait rien pour un invité. Renvoie les nouveaux succès."""
    p = c.execute("SELECT * FROM parties WHERE id=?", (partie_id,)).fetchone()
    ident = p["compte"]
    if ident is None:
        return []
    gain = p["total"] * 10 if p["mode"] == "serie" else p["total"] // 50
    c.execute("UPDATE comptes SET xp = xp + ? WHERE identifiant=?", (gain, ident))
    return _attribuer(c, ident, _succes_a_jour(c, ident, p))


def lieu_revele(c, partie_id) -> list[dict]:
    """Mode Exploration : un lieu révélé rapporte un peu d'XP."""
    p = c.execute("SELECT * FROM parties WHERE id=?", (partie_id,)).fetchone()
    ident = p["compte"]
    if ident is None:
        return []
    c.execute("UPDATE comptes SET xp = xp + 2 WHERE identifiant=?", (ident,))
    n = c.execute("SELECT COUNT(*) FROM manches m JOIN parties q ON q.id=m.partie_id WHERE q.compte=? AND q.mode='exploration' "
                  "AND m.repondu_le IS NOT NULL", (ident,)).fetchone()[0]
    return _attribuer(c, ident, ["explorateur"] if n >= 20 else [])
