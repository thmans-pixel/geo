"""Règles du jeu solo : parties, manches, chrono, défis, série de pays, exploration.

Principe : tout est décidé ici, côté serveur. Le navigateur ne reçoit les coordonnées d'un lieu
qu'après avoir répondu (ou après avoir demandé à le révéler en mode Exploration).
"""
import json
import random
import re
import secrets
import unicodedata

from .. import base, config, horloge
from . import cartes, fiches, geo, lieux as lieux_mod, profil, progression, score

NB_MANCHES = 5
MODES = ("classique", "defi", "defi_jour", "serie", "exploration")
CONTRAINTES = ("libre", "sans_deplacement", "fige")
CHRONOS = (0, 10, 30, 60, 120, 300)
GRACE_S = 3.0          # marge accordée à la réponse envoyée à l'instant où le chrono tombe à zéro
TOLERANCE_PAYS_KM = 20  # un clic tout près de la côte compte pour le pays voisin du rivage


class ErreurJeu(Exception):
    def __init__(self, statut: int, message: str, **extra):
        super().__init__(message)
        self.statut, self.message, self.extra = statut, message, extra


# ---------------------------------------------------------------- outils

def nettoyer_pseudo(pseudo) -> str:
    p = "".join(ch for ch in str(pseudo or "") if unicodedata.category(ch) not in ("Cc", "Cf", "Co", "Cs"))
    p = re.sub(r"\s+", " ", p).strip()[:20]
    return p or "Invité"


def _carte(carte_id) -> dict:
    c = cartes.carte(carte_id) if isinstance(carte_id, str) else None
    if c is None or c.get("archivee"):
        raise ErreurJeu(400, "Carte inconnue.")
    return c


def _reglages(contrainte, chrono):
    if not isinstance(contrainte, str) or contrainte not in CONTRAINTES:
        raise ErreurJeu(400, "Contrainte inconnue.")
    if isinstance(chrono, bool) or not isinstance(chrono, int) or chrono not in CHRONOS:
        raise ErreurJeu(400, "Durée de chrono inconnue.")


def _pays():
    p = geo.pays_disponibles(config.chemin_pays())
    if p is None:
        raise ErreurJeu(503, "Le fichier des contours de pays (pays.geojson) est absent : "
                             "la Série de pays n'est pas disponible.")
    return p


def _lieux(fonction, *args):
    try:
        return fonction(*args)
    except lieux_mod.PasDeLieux as e:
        raise ErreurJeu(503, str(e))


def _json(o) -> str:
    return json.dumps(o, ensure_ascii=False)


# ---------------------------------------------------------------- défis

def _lieux_public_defi(row) -> dict:
    return {"id": row["id"], "nom": row["nom"], "carte": row["carte"], "contrainte": row["contrainte"],
            "chrono": row["chrono"], "nb_manches": len(json.loads(row["lieux_json"]))}


def _defi_jour(c) -> dict:
    ident = f"jour-{horloge.jour_paris()}"
    row = c.execute("SELECT * FROM defis WHERE id=?", (ident,)).fetchone()
    if row is None:
        liste = _lieux(lieux_mod.tirer, "monde", NB_MANCHES, random.Random(ident))
        c.execute("INSERT OR IGNORE INTO defis VALUES (?,?,?,?,?,?,?)",
                  (ident, f"Défi du {horloge.jour_paris()}", "monde", "libre", 0, _json(liste), horloge.maintenant()))
        row = c.execute("SELECT * FROM defis WHERE id=?", (ident,)).fetchone()
    return row


def _charger_defi(c, defi_id):
    if defi_id and str(defi_id).startswith("jour-"):
        if defi_id != f"jour-{horloge.jour_paris()}":
            row = c.execute("SELECT * FROM defis WHERE id=?", (defi_id,)).fetchone()
        else:
            row = _defi_jour(c)
    else:
        row = c.execute("SELECT * FROM defis WHERE id=?", (defi_id,)).fetchone() if defi_id else None
    if row is None:
        raise ErreurJeu(404, "Défi introuvable.")
    return row


def creer_defi(carte_id, contrainte="libre", chrono=0) -> dict:
    carte = _carte(carte_id)
    _reglages(contrainte, chrono)
    liste = _lieux(lieux_mod.tirer, carte_id, NB_MANCHES, random.SystemRandom())
    ident = secrets.token_urlsafe(6)
    with base.connexion() as c:
        c.execute("INSERT INTO defis VALUES (?,?,?,?,?,?,?)",
                  (ident, f"Défi {carte['nom']}", carte_id, contrainte, chrono, _json(liste), horloge.maintenant()))
    return {"id": ident, "lien": f"/?defi={ident}"}


def infos_defi(joueur_id, defi_id) -> dict:
    with base.connexion() as c:
        row = _charger_defi(c, defi_id)
        classement = [{"pseudo": r["pseudo"], "total": r["total"]} for r in c.execute(
            "SELECT COALESCE(k.pseudo, p.pseudo) pseudo, p.total total FROM parties p "
            "LEFT JOIN comptes k ON k.identifiant = p.compte WHERE p.defi_id=? AND p.statut='terminee' "
            "ORDER BY p.total DESC, p.cree_le ASC LIMIT 20", (row["id"],))]
        deja = c.execute("SELECT id, statut FROM parties WHERE defi_id=? AND joueur_id=?",
                         (row["id"], joueur_id)).fetchone()
        infos = _lieux_public_defi(row)
        infos["carte_nom"] = _carte(row["carte"])["nom"]
        infos["classement"] = classement
        infos["deja_joue"] = {"partie_id": deja["id"], "statut": deja["statut"]} if deja else None
        return infos


# ---------------------------------------------------------------- parties

def creer_partie(joueur_id, mode, carte_id=None, contrainte="libre", chrono=0, pseudo="", defi_id=None, compte=None) -> str:
    if not isinstance(mode, str) or mode not in MODES:
        raise ErreurJeu(400, "Mode de jeu inconnu.")
    if defi_id is not None and not isinstance(defi_id, str):
        raise ErreurJeu(400, "Défi inconnu.")
    pseudo = compte["pseudo"] if compte else nettoyer_pseudo(pseudo)
    ident = compte["identifiant"] if compte else None
    with base.connexion() as c:
        nb = None
        if mode in ("defi", "defi_jour"):
            defi = _defi_jour(c) if mode == "defi_jour" else _charger_defi(c, defi_id)
            deja = c.execute("SELECT id FROM parties WHERE defi_id=? AND (joueur_id=? OR (compte IS NOT NULL AND compte=?))",
                             (defi["id"], joueur_id, ident)).fetchone()
            if deja:
                raise ErreurJeu(409, "Tu as déjà joué ce défi.", partie_id=deja["id"])
            carte_id, contrainte, chrono = defi["carte"], defi["contrainte"], defi["chrono"]
            liste = json.loads(defi["lieux_json"])
            nb, defi_ref = len(liste), defi["id"]
        else:
            _carte(carte_id)
            _reglages(contrainte, chrono)
            defi_ref = None
            if mode == "classique":
                liste, nb = _lieux(lieux_mod.tirer, carte_id, NB_MANCHES, random.SystemRandom()), NB_MANCHES
            else:
                if mode == "serie":
                    _pays()
                liste = [_lieux(lieux_mod.tirer_un, carte_id, set(), random.SystemRandom())]
        ident_partie = secrets.token_urlsafe(9)
        now = horloge.maintenant()
        c.execute("INSERT INTO parties (id, joueur_id, pseudo, mode, carte, contrainte, chrono, defi_id, "
                  "lieux_json, nb_manches, cree_le, compte) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                  (ident_partie, joueur_id, pseudo, mode, carte_id, contrainte, chrono, defi_ref, _json(liste), nb, now, ident))
        c.execute("INSERT INTO manches (partie_id, numero, lieu_json, debut_le) VALUES (?,?,?,?)",
                  (ident_partie, 1, _json(liste[0]), now))
        return ident_partie


def _partie(c, partie_id, joueur_id):
    p = c.execute("SELECT * FROM parties WHERE id=?", (partie_id,)).fetchone()
    if p is None or p["joueur_id"] != joueur_id:
        raise ErreurJeu(404, "Partie introuvable.")
    return p


def _manche(c, p):
    return c.execute("SELECT * FROM manches WHERE partie_id=? AND numero=?", (p["id"], p["manche"])).fetchone()


def _enregistrer(c, p, m, lat, lon, temps_ecoule) -> list:
    """Range la réponse d'une manche (ou l'absence de réponse) et fait avancer la partie.
    Renvoie les succès obtenus si la partie vient de se terminer."""
    lieu = json.loads(m["lieu_json"])
    carte = cartes.carte(p["carte"])
    distance = geo.distance_m(lieu["lat"], lieu["lon"], lat, lon) if lat is not None else None
    points, juste, pays_choisi = 0, None, None
    if p["mode"] == "serie":
        if lat is not None:
            pays_choisi = _pays().code_du_point(lat, lon, TOLERANCE_PAYS_KM)
        juste = int(pays_choisi is not None and pays_choisi == lieu["pays"])
        points = juste
    elif distance is not None:
        points = score.points(distance, carte["diagonale_km"])
    c.execute("UPDATE manches SET repondu_le=?, rep_lat=?, rep_lon=?, pays_choisi=?, distance_m=?, points=?, "
              "juste=?, temps_ecoule=? WHERE partie_id=? AND numero=?",
              (horloge.maintenant(), lat, lon, pays_choisi, distance, points, juste, int(temps_ecoule),
               p["id"], m["numero"]))
    statut = "en_cours"
    if p["nb_manches"] and m["numero"] >= p["nb_manches"]:
        statut = "terminee"
    if p["mode"] == "serie" and not juste:
        statut = "terminee"
    c.execute("UPDATE parties SET total = total + ?, statut=? WHERE id=?", (points, statut, p["id"]))
    if p["mode"] == "serie" and statut == "terminee":
        serie = p["total"] + points
        cle = f"serie:{p['carte']}"
        c.execute("INSERT INTO records VALUES (?,?,?) ON CONFLICT(joueur_id, cle) DO UPDATE SET "
                  "valeur = MAX(valeur, excluded.valeur)", (profil.proprietaire_record(p["compte"], p["joueur_id"]), cle, serie))
    return progression.fin_de_partie(c, p["id"]) if statut == "terminee" else []


def _regler_si_expiree(c, p, m):
    """Manche dont le chrono est écoulé sans réponse : 0 point, enregistré par le serveur."""
    if (m["repondu_le"] is None and p["chrono"] and p["mode"] != "exploration"
            and horloge.maintenant() > m["debut_le"] + p["chrono"] + GRACE_S):
        _enregistrer(c, p, m, None, None, True)
        return True
    return False


def _resultat(p, m) -> dict:
    lieu = json.loads(m["lieu_json"])
    r = {"numero": m["numero"],
         "reponse": None if m["rep_lat"] is None else {"lat": m["rep_lat"], "lon": m["rep_lon"]},
         "lieu": {"lat": lieu["lat"], "lon": lieu["lon"], "pays": lieu["pays"]},
         "fiche": fiches.fiche(lieu["pays"]),
         "distance_m": m["distance_m"], "points": m["points"], "temps_ecoule": bool(m["temps_ecoule"])}
    if p["mode"] == "serie":
        r["juste"] = bool(m["juste"])
        r["pays_choisi"] = fiches.fiche(m["pays_choisi"])["nom"] if m["pays_choisi"] else None
    return r


def etat(joueur_id, partie_id) -> dict:
    with base.connexion() as c:
        p = _partie(c, partie_id, joueur_id)
        m = _manche(c, p)
        _regler_si_expiree(c, p, m)
        p = _partie(c, partie_id, joueur_id)
        m = _manche(c, p)
        carte = cartes.carte(p["carte"])
        out = {"partie": {"id": p["id"], "mode": p["mode"], "carte": cartes.publique(carte),
                          "contrainte": p["contrainte"], "chrono": p["chrono"],
                          "nb_manches": p["nb_manches"], "statut": p["statut"], "pseudo": p["pseudo"],
                          "defi_id": p["defi_id"]},
               "total": p["total"],
               "historique": [{"numero": r["numero"], "points": r["points"], "distance_m": r["distance_m"]}
                              for r in c.execute("SELECT numero, points, distance_m FROM manches WHERE "
                                                 "partie_id=? AND repondu_le IS NOT NULL ORDER BY numero",
                                                 (p["id"],))]}
        if m["repondu_le"] is None:
            lieu = json.loads(m["lieu_json"])
            restant = None
            if p["chrono"] and p["mode"] != "exploration":
                restant = max(0.0, m["debut_le"] + p["chrono"] - horloge.maintenant())
            out["phase"] = "question"
            out["manche"] = {"numero": m["numero"], "image": lieu["image"], "temps_restant": restant}
        else:
            out["phase"] = "fin" if p["statut"] == "terminee" else "resultat"
            out["resultat"] = _resultat(p, m)
            if p["mode"] == "serie" and p["statut"] == "terminee":
                rec = c.execute("SELECT valeur FROM records WHERE joueur_id=? AND cle=?",
                                (profil.proprietaire_record(p["compte"], joueur_id), f"serie:{p['carte']}")).fetchone()
                out["resultat"]["serie"] = p["total"]
                out["resultat"]["record"] = rec["valeur"] if rec else p["total"]
        return out


def _coordonnees(lat, lon):
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        raise ErreurJeu(400, "Coordonnées invalides.")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180) or lat != lat or lon != lon:
        raise ErreurJeu(400, "Coordonnées invalides.")
    return lat, lon


def repondre(joueur_id, partie_id, lat=None, lon=None) -> dict:
    with base.connexion() as c:
        p = _partie(c, partie_id, joueur_id)
        if p["mode"] == "exploration":
            raise ErreurJeu(400, "Pas de réponse à donner en mode Exploration.")
        m = _manche(c, p)
        if m["repondu_le"] is None and _regler_si_expiree(c, p, m):
            # réponse arrivée trop tard : la manche vaut 0 point, on le montre au joueur
            p = _partie(c, partie_id, joueur_id)
            return _resultat(p, _manche(c, p)) | {"total": p["total"], "statut": p["statut"]}
        if m["repondu_le"] is not None:
            raise ErreurJeu(409, "Cette manche a déjà sa réponse.")
        if lat is None or lon is None:
            pas_de_repere = True
        else:
            lat, lon = _coordonnees(lat, lon)
            pas_de_repere = False
        ecoule = bool(p["chrono"]) and horloge.maintenant() >= m["debut_le"] + p["chrono"] - 1.5
        nouveaux = _enregistrer(c, p, m, None if pas_de_repere else lat, None if pas_de_repere else lon,
                                ecoule and pas_de_repere)
        p = _partie(c, partie_id, joueur_id)
        return _resultat(p, _manche(c, p)) | {"total": p["total"], "statut": p["statut"], "nouveaux_succes": nouveaux}


def reveler(joueur_id, partie_id) -> dict:
    """Mode Exploration : montre où l'on est, sans score."""
    with base.connexion() as c:
        p = _partie(c, partie_id, joueur_id)
        if p["mode"] != "exploration":
            raise ErreurJeu(400, "Seul le mode Exploration permet de révéler le lieu.")
        m = _manche(c, p)
        if m["repondu_le"] is not None:
            raise ErreurJeu(409, "Le lieu est déjà révélé.")
        c.execute("UPDATE manches SET repondu_le=? WHERE partie_id=? AND numero=?",
                  (horloge.maintenant(), p["id"], m["numero"]))
        return _resultat(p, _manche(c, p)) | {"nouveaux_succes": progression.lieu_revele(c, p["id"])}


def suivante(joueur_id, partie_id) -> None:
    with base.connexion() as c:
        p = _partie(c, partie_id, joueur_id)
        m = _manche(c, p)
        _regler_si_expiree(c, p, m)
        p = _partie(c, partie_id, joueur_id)
        m = _manche(c, p)
        if m["repondu_le"] is None:
            raise ErreurJeu(409, "Réponds d'abord à cette manche.")
        if p["statut"] == "terminee":
            raise ErreurJeu(409, "La partie est terminée.")
        numero = p["manche"] + 1
        liste = json.loads(p["lieux_json"])
        if p["nb_manches"]:
            lieu = liste[numero - 1]
        else:
            lieu = _lieux(lieux_mod.tirer_un, p["carte"], {l["id"] for l in liste[-20:]}, random.SystemRandom())
            liste.append(lieu)
            c.execute("UPDATE parties SET lieux_json=? WHERE id=?", (_json(liste), p["id"]))
        c.execute("UPDATE parties SET manche=? WHERE id=?", (numero, p["id"]))
        c.execute("INSERT INTO manches (partie_id, numero, lieu_json, debut_le) VALUES (?,?,?,?)",
                  (p["id"], numero, _json(lieu), horloge.maintenant()))


def recap(joueur_id, partie_id) -> dict:
    with base.connexion() as c:
        p = _partie(c, partie_id, joueur_id)
        if p["statut"] != "terminee":
            raise ErreurJeu(403, "Le récapitulatif n'est disponible qu'à la fin de la partie.")
        manches = [_resultat(p, m) for m in c.execute(
            "SELECT * FROM manches WHERE partie_id=? AND repondu_le IS NOT NULL ORDER BY numero", (p["id"],))]
        out = {"partie": {"id": p["id"], "mode": p["mode"], "carte": cartes.publique(cartes.carte(p["carte"])),
                          "defi_id": p["defi_id"]},
               "total": p["total"], "maximum": score.POINTS_MAX * (p["nb_manches"] or 0), "manches": manches}
        if p["defi_id"]:
            out["classement"] = infos_defi(joueur_id, p["defi_id"])["classement"]
        return out
