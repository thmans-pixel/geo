"""Salons multijoueur en temps réel (étape 3 : Partie entre amis, Duel, équipes, Batailles royales, spectateurs, chat).

Tout vit en mémoire : un salon disparaît quand tout le monde est parti, et le chat n'est jamais écrit
nulle part (ni base, ni journaux). Le serveur décide de tout ; le navigateur n'envoie que son clic.

La logique est indépendante du transport : une « liaison » est n'importe quel objet qui a
`async envoyer(dict)` et `async fermer()`. Le WebSocket est branché dans `app.py`.
"""
import asyncio
import random
import re
import secrets
import unicodedata

from . import config, horloge, quota
from .jeu import cartes, fiches, geo, lieux as lieux_mod, score
from .jeu.moteur import TOLERANCE_PAYS_KM, ErreurJeu, _carte, _lieux, _pays, _reglages

ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"      # sans I, L, O, 0, 1 : pas de confusion à l'oral
LONGUEUR_CODE = 6
MAX_JOUEURS = 10
MAX_SPECTATEURS = 20
MAX_SALONS = 200
MAX_SALONS_PAR_HOTE = 2
NB_MANCHES = 5
DELAI_RECONNEXION_S = 60
DELAI_SALON_VIDE_S = 600
DELAI_REPONSE_TARDIVE_S = 3       # une réponse en vol à la fin du chrono est encore acceptée
MODES = {
    "amis":        {"nom": "Partie entre amis", "min": 2, "max": 10},
    "duel":        {"nom": "Duel", "min": 2, "max": 4},
    "br_distance": {"nom": "Bataille royale — distance", "min": 3, "max": 10},
    "br_pays":     {"nom": "Bataille royale — pays", "min": 3, "max": 10},
}
PV_DEPART = 6000
DELAI_ADVERSAIRE_S = 15            # Duel : temps laissé aux autres dès la première réponse
MULTIPLICATEUR_PAR_MANCHE = 0.5    # Duel : ×1 aux manches 1 à 4, puis +0,5 par manche
VIES_BR_PAYS = 3
ESSAIS_BR_PAYS = 3
CHAT_MAX = 200
CHAT_DELAI_S = 1.0


def _nettoyer_chat(texte) -> str:
    t = re.sub(r"\s+", " ", str(texte or ""))            # retours à la ligne et tabulations deviennent des espaces
    t = "".join(c for c in t if unicodedata.category(c) not in ("Cc", "Cf", "Co", "Cs"))
    return t.strip()


class Membre:
    def __init__(self, cle, pseudo, role):
        self.cle = cle                       # privé : compte ou cookie, jamais envoyé aux autres
        self.id = secrets.token_hex(3)       # public : sert à désigner un membre dans les messages
        self.pseudo, self.role = pseudo, role
        self.liaison = None
        self.deconnecte_le = None
        self.dernier_message = 0.0

    @property
    def connecte(self):
        return self.liaison is not None


class Salon:
    def __init__(self, code, hote_cle, carte_id, contrainte, chrono, mode="amis"):
        self.code, self.hote_cle, self.mode = code, hote_cle, mode
        self.carte_id, self.contrainte, self.chrono = carte_id, contrainte, chrono
        self.membres: dict[str, Membre] = {}      # clé privée → membre
        self.bannis: set[str] = set()
        self.muets: set[str] = set()              # clés rendues muettes : le muet survit à une déconnexion
        self.verrouille = False                   # plus aucune nouvelle personne ne peut entrer
        self.chat_actif = True
        self.equipes: dict[str, str] = {}         # Duel : clé → « A » ou « B »
        self.cree_le = self.derniere_activite = horloge.maintenant()
        self._chats: list[dict] = []              # messages à envoyer au prochain diffuser(), jamais gardés
        self._remettre_a_zero()

    def _remettre_a_zero(self):
        self.phase = "attente"                    # attente | manche | resultat | fin
        self.lieux, self.numero, self.debut_le = [], 0, 0.0
        self.reponses: dict[str, dict] = {}
        self.resultat = None
        self.totaux: dict[str, int] = {}          # Partie entre amis
        self.participants: list[str] = []         # clés des joueurs au lancement, dans l'ordre d'arrivée
        self.noms: dict[str, dict] = {}           # clé → {id, pseudo} (même pour qui est parti)
        self.pv: dict[str, int] = {}              # Duel : points de vie par côté (clé en 1 contre 1, « A »/« B » en équipes)
        self.vies: dict[str, int] = {}            # Bataille royale « pays »
        self.elimines: list[tuple[str, int]] = [] # (clé, numéro de manche), dans l'ordre
        self.gagnants: list[str] = []
        self.echeance = None                      # Duel : fin forcée de la manche après la première réponse
        self.variante = None                      # Duel : « 1v1 » ou « 2v2 »

    # ------------------------------------------------------------ membres
    def joueurs(self):
        return [m for m in self.membres.values() if m.role == "joueur"]

    def hote(self) -> Membre | None:
        return self.membres.get(self.hote_cle)

    def _max_joueurs(self):
        return MODES[self.mode]["max"]

    def rejoindre(self, cle, pseudo, role_souhaite, liaison) -> Membre:
        if cle in self.bannis:
            raise ErreurJeu(403, "Tu as été exclu de ce salon.")
        m = self.membres.get(cle)
        if m is None:
            if self.verrouille:
                raise ErreurJeu(403, "L'hôte a verrouillé ce salon.")
            pris = {x.pseudo for x in self.membres.values()}
            base_pseudo, n = pseudo, 1
            while pseudo in pris:                   # pas deux personnes du même nom : on ne peut pas se faire passer pour une autre
                n += 1
                pseudo = f"{base_pseudo[:16]} ({n})"
            role = role_souhaite
            if role == "joueur" and (self.phase != "attente" or len(self.joueurs()) >= self._max_joueurs()):
                role = "spectateur"          # partie commencée ou salon plein : on peut regarder
            if role == "spectateur" and sum(1 for x in self.membres.values() if x.role == "spectateur") >= MAX_SPECTATEURS:
                raise ErreurJeu(409, "Ce salon est complet.")
            m = self.membres[cle] = Membre(cle, pseudo, role)
            self._equilibrer_equipes()
        elif m.liaison is not None:
            # même personne dans un deuxième onglet : le nouveau remplace l'ancien
            ancienne, m.liaison = m.liaison, None
            try:
                asyncio.get_running_loop().create_task(_fermer(ancienne))
            except RuntimeError:
                pass
        m.liaison, m.deconnecte_le = liaison, None
        self.derniere_activite = horloge.maintenant()
        return m

    def deconnecter(self, membre, liaison):
        if membre.liaison is liaison:
            membre.liaison, membre.deconnecte_le = None, horloge.maintenant()
            self.derniere_activite = horloge.maintenant()

    def _retirer(self, membre):
        self.membres.pop(membre.cle, None)
        if membre.liaison is not None:
            try:
                asyncio.get_running_loop().create_task(_fermer(membre.liaison))
            except RuntimeError:
                pass
            membre.liaison = None
        if membre.cle == self.hote_cle:
            reste = [m for m in self.membres.values() if m.connecte] or list(self.membres.values())
            joueurs = [m for m in reste if m.role == "joueur"]
            heritier = (joueurs or reste or [None])[0]
            if heritier:
                self.hote_cle = heritier.cle
                self.muets.discard(heritier.cle)
        if self.phase == "attente":
            self.equipes.pop(membre.cle, None)      # en partie, les équipes restent figées (le côté d'un parti reste lisible)
            self.totaux.pop(membre.cle, None)
            self._equilibrer_equipes()
        elif membre.cle in self.participants and membre.cle not in [c for c, _ in self.elimines]:
            # une personne qui part en pleine partie : abandon
            if self.mode == "br_distance" or self.mode == "br_pays":
                self.elimines.append((membre.cle, self.numero))
            self._verifier_fin_partie()

    # ------------------------------------------------------------ équipes (Duel)
    def _equilibrer_equipes(self):
        """Chaque joueur a une équipe A ou B, réparties à égalité tant que possible."""
        if self.phase != "attente":
            return
        joueurs = [m.cle for m in self.joueurs()]
        self.equipes = {c: e for c, e in self.equipes.items() if c in joueurs}
        for c in joueurs:
            if c not in self.equipes:
                a = sum(1 for e in self.equipes.values() if e == "A")
                self.equipes[c] = "A" if a <= len(self.equipes) - a else "B"

    def _cote(self, cle):
        """Qui perd des points de vie : la personne en 1 contre 1, l'équipe en 2 contre 2."""
        return cle if self.variante == "1v1" else self.equipes[cle]

    # ------------------------------------------------------------ actions
    def _exiger_hote(self, membre):
        if membre.cle != self.hote_cle:
            raise ErreurJeu(403, "Seul l'hôte peut faire ça.")

    async def traiter(self, membre, msg):
        if not isinstance(msg, dict) or not isinstance(msg.get("t"), str):
            raise ErreurJeu(400, "Message invalide.")
        t = msg["t"]
        if self.membres.get(membre.cle) is not membre:
            raise ErreurJeu(403, "Tu n'es plus dans ce salon.")
        self.derniere_activite = horloge.maintenant()
        if t == "chat":
            self._chat(membre, msg.get("texte"))
        elif t == "repondre":
            self._repondre(membre, msg.get("lat"), msg.get("lon"))
        elif t == "regler":
            self._exiger_hote(membre); self._regler(msg)
        elif t == "lancer":
            self._exiger_hote(membre); self._lancer()
        elif t == "suivante":
            self._exiger_hote(membre); self._suivante()
        elif t == "rejouer":
            self._exiger_hote(membre); self._rejouer()
        elif t == "role":
            self._changer_role(membre, msg)
        elif t == "equipe":
            self._exiger_hote(membre); self._changer_equipe(msg)
        elif t == "chat_actif":
            self._exiger_hote(membre)
            if not isinstance(msg.get("valeur"), bool):
                raise ErreurJeu(400, "Valeur invalide.")
            self.chat_actif = msg["valeur"]
        elif t == "muet":
            self._exiger_hote(membre)
            cible = self._cible(msg.get("id"))
            if not isinstance(msg.get("valeur"), bool):
                raise ErreurJeu(400, "Valeur invalide.")
            if cible is membre:
                raise ErreurJeu(400, "Tu ne peux pas te rendre muet toi-même.")
            (self.muets.add if msg["valeur"] else self.muets.discard)(cible.cle)
        elif t == "verrouiller":
            self._exiger_hote(membre)
            if not isinstance(msg.get("valeur"), bool):
                raise ErreurJeu(400, "Valeur invalide.")
            self.verrouille = msg["valeur"]
        elif t == "exclure":
            self._exiger_hote(membre)
            cible = self._cible(msg.get("id"))
            if cible is membre:
                raise ErreurJeu(400, "Tu ne peux pas t'exclure toi-même.")
            self.bannis.add(cible.cle)
            liaison = cible.liaison
            self._retirer(cible)
            if liaison is not None:
                try:
                    await asyncio.wait_for(liaison.envoyer({"t": "exclu"}), 2)
                except Exception:
                    pass
                await _fermer(liaison)
            self._verifier_fin_manche()
        else:
            raise ErreurJeu(400, "Message inconnu.")
        await self.diffuser()

    def _cible(self, ident) -> Membre:
        for m in self.membres.values():
            if m.id == ident:
                return m
        raise ErreurJeu(404, "Personne ne porte ce numéro dans le salon.")

    def _regler(self, msg):
        if self.phase != "attente":
            raise ErreurJeu(409, "Les réglages ne changent plus une fois la partie lancée.")
        carte_id = msg.get("carte", self.carte_id)
        contrainte, chrono = msg.get("contrainte", self.contrainte), msg.get("chrono", self.chrono)
        mode = msg.get("mode", self.mode)
        _carte(carte_id); _reglages(contrainte, chrono)
        if not isinstance(mode, str) or mode not in MODES:
            raise ErreurJeu(400, "Mode inconnu.")
        if len(self.joueurs()) > MODES[mode]["max"]:
            raise ErreurJeu(409, f"Trop de joueurs pour ce mode ({MODES[mode]['max']} au plus) : "
                                 "passe des personnes en spectateurs.")
        self.carte_id, self.contrainte, self.chrono, self.mode = carte_id, contrainte, chrono, mode
        self._equilibrer_equipes()

    def _changer_role(self, membre, msg):
        """Passer joueur ↔ spectateur avant le lancement (chacun pour soi ; l'hôte pour tout le monde)."""
        if self.phase != "attente":
            raise ErreurJeu(409, "On ne change plus de rôle une fois la partie lancée.")
        cible = self._cible(msg.get("id")) if msg.get("id") else membre
        if cible is not membre:
            self._exiger_hote(membre)
        role = msg.get("role")
        if role not in ("joueur", "spectateur"):
            raise ErreurJeu(400, "Rôle inconnu.")
        if role == "joueur" and cible.role != "joueur" and len(self.joueurs()) >= self._max_joueurs():
            raise ErreurJeu(409, "Il n'y a plus de place de joueur dans ce mode.")
        if role == "spectateur" and cible.role != "spectateur" and \
                sum(1 for x in self.membres.values() if x.role == "spectateur") >= MAX_SPECTATEURS:
            raise ErreurJeu(409, "Plus de place de spectateur.")
        cible.role = role
        self._equilibrer_equipes()

    def _changer_equipe(self, msg):
        if self.phase != "attente" or self.mode != "duel":
            raise ErreurJeu(409, "Les équipes se règlent avant un Duel.")
        cible = self._cible(msg.get("id"))
        if cible.role != "joueur" or msg.get("equipe") not in ("A", "B"):
            raise ErreurJeu(400, "Équipe invalide.")
        self.equipes[cible.cle] = msg["equipe"]

    def _lancer(self):
        if self.phase != "attente":
            raise ErreurJeu(409, "La partie est déjà lancée.")
        joueurs = self.joueurs()
        regle = MODES[self.mode]
        if len(joueurs) < regle["min"]:
            raise ErreurJeu(409, f"Il faut au moins {regle['min']} joueurs pour ce mode.")
        variante = None
        if self.mode == "duel":
            if len(joueurs) == 2:
                variante = "1v1"
            elif len(joueurs) == 4 and sorted(self.equipes[m.cle] for m in joueurs) == ["A", "A", "B", "B"]:
                variante = "2v2"
            else:
                raise ErreurJeu(409, "Un Duel se joue à 2 (1 contre 1) ou à 4 en 2 équipes de 2.")
        if self.mode == "br_pays":
            _pays()                                  # 503 si les contours de pays manquent
        if self.mode == "amis":
            lieux = _lieux(lieux_mod.tirer, self.carte_id, NB_MANCHES, random.SystemRandom())
        else:
            lieux = []
        equipes = dict(self.equipes)
        self._remettre_a_zero()
        self.equipes, self.variante, self.lieux = equipes, variante, lieux
        self.participants = [m.cle for m in joueurs]
        self.noms = {m.cle: {"id": m.id, "pseudo": m.pseudo} for m in joueurs}
        if self.mode == "amis":
            self.totaux = {c: 0 for c in self.participants}
        elif self.mode == "duel":
            self.pv = {self._cote(c): PV_DEPART for c in self.participants}
        elif self.mode == "br_pays":
            self.vies = {c: VIES_BR_PAYS for c in self.participants}
        try:
            self._demarrer_manche()
        except ErreurJeu:
            self._remettre_a_zero()
            self.equipes = equipes
            raise

    def _demarrer_manche(self):
        # chaque personne présente (joueurs et spectateurs) charge l'image : on les compte toutes
        quota.consommer(max(1, sum(1 for m in self.membres.values() if m.connecte)))
        if self.mode != "amis":
            deja = {l["id"] for l in self.lieux}
            try:
                if len(deja) >= len(lieux_mod.charger(self.carte_id)):
                    raise ErreurJeu(503, "Plus de lieux sur cette carte.")      # on ne rejoue jamais un lieu déjà vu
                self.lieux.append(_lieux(lieux_mod.tirer_un, self.carte_id, deja, random.SystemRandom()))
            except ErreurJeu:
                if not self.numero:
                    raise
                self._terminer_partie()               # plus de lieux à proposer
                return
        self.numero += 1
        self.phase, self.debut_le, self.reponses, self.resultat = "manche", horloge.maintenant(), {}, None
        self.echeance = None

    def _suivante(self):
        if self.phase != "resultat":
            raise ErreurJeu(409, "La manche n'est pas terminée.")
        self._demarrer_manche()

    def _rejouer(self):
        if self.phase != "fin":
            raise ErreurJeu(409, "La partie n'est pas terminée.")
        equipes = dict(self.equipes)
        self._remettre_a_zero()
        self.equipes = equipes
        self._equilibrer_equipes()

    # ------------------------------------------------------------ qui joue cette manche
    def _actifs(self) -> list[Membre]:
        """Les joueurs encore en lice (présents dans le salon, non éliminés), dans l'ordre d'arrivée."""
        elim = {c for c, _ in self.elimines}
        return [self.membres[c] for c in self.participants if c in self.membres and c not in elim]

    def _est_elimine(self, cle):
        return any(c == cle for c, _ in self.elimines)

    def _fini(self, cle) -> bool:
        r = self.reponses.get(cle)
        return bool(r) and (r.get("fini", True))

    def _marge(self):
        """Marge pour les réponses en vol : 1 s quand c'est le compte à rebours de 15 s du Duel qui décide, 3 s sinon."""
        chrono_fin = self.debut_le + self.chrono if self.chrono else None
        if self.echeance is not None and (chrono_fin is None or self.echeance <= chrono_fin):
            return 1.0
        return DELAI_REPONSE_TARDIVE_S

    def _delai_fin(self):
        """Heure à laquelle la manche se termine d'elle-même (sans la marge de réponses en vol), ou None."""
        fins = []
        if self.chrono:
            fins.append(self.debut_le + self.chrono)
        if self.echeance is not None:
            fins.append(self.echeance)
        return min(fins) if fins else None

    # ------------------------------------------------------------ réponses
    def _repondre(self, membre, lat, lon):
        if self.phase != "manche":
            raise ErreurJeu(409, "Pas de manche en cours.")
        if membre.role != "joueur" or membre.cle not in self.participants:
            raise ErreurJeu(403, "Les spectateurs ne jouent pas.")
        if self._est_elimine(membre.cle):
            raise ErreurJeu(403, "Tu es éliminé : tu regardes la suite.")
        if self._fini(membre.cle):
            raise ErreurJeu(409, "Tu as déjà répondu.")
        now = horloge.maintenant()
        fin = self._delai_fin()
        if fin is not None and now > fin + self._marge():
            raise ErreurJeu(409, "Trop tard.")
        if (isinstance(lat, bool) or isinstance(lon, bool) or not isinstance(lat, (int, float))
                or not isinstance(lon, (int, float)) or not (-90 <= lat <= 90 and -180 <= lon <= 180)):
            raise ErreurJeu(400, "Point invalide.")
        lat, lon = float(lat), float(lon)
        if self.mode == "br_pays":
            self._repondre_pays(membre, lat, lon, now)
        else:
            self.reponses[membre.cle] = {"lat": lat, "lon": lon, "le": now}
            if self.mode == "duel" and self.echeance is None:
                self.echeance = now + DELAI_ADVERSAIRE_S      # les autres ont 15 s dès la première réponse
        self._verifier_fin_manche()

    def _repondre_pays(self, membre, lat, lon, now):
        lieu = self.lieux[self.numero - 1]
        r = self.reponses.setdefault(membre.cle, {"essais": [], "trouve": False, "fini": False, "le": now})
        code = _pays().code_du_point(lat, lon, TOLERANCE_PAYS_KM)
        r["essais"].append({"lat": lat, "lon": lon, "pays": code})
        if code is not None and code == lieu["pays"]:
            r["trouve"], r["fini"], r["le"] = True, True, now
        elif len(r["essais"]) >= ESSAIS_BR_PAYS:
            r["fini"] = True

    def _verifier_fin_manche(self):
        if self.phase != "manche":
            return
        actifs = self._actifs()
        if not actifs:
            self._terminer_partie()
            return
        presents = [m for m in actifs if m.connecte]
        if presents and all(self._fini(m.cle) for m in presents):
            self._clore_manche()

    def _verifier_fin_partie(self):
        """Une personne est partie en pleine partie : y a-t-il encore une partie ?"""
        if self.phase not in ("manche", "resultat"):
            return
        if self.mode == "duel":
            restants = {self._cote(c) for c in self.participants if c in self.membres}
            if len(restants) < 2:
                self.gagnants = [self.noms[c]["id"] for c in self.participants if c in self.membres]
                self.phase = "fin"
        elif self.mode in ("br_distance", "br_pays"):
            vivants = self._actifs()
            if len(vivants) <= 1:
                self.gagnants = [m.id for m in vivants]
                self.phase = "fin"
        else:
            if not self._actifs():
                self.phase = "fin"
        if self.phase == "manche":
            self._verifier_fin_manche()

    def _terminer_partie(self):
        if self.mode in ("br_distance", "br_pays") and not self.gagnants:
            self.gagnants = [m.id for m in self._actifs()]
        elif self.mode == "duel" and not self.gagnants and self.pv:
            meilleur = max(self.pv.values())          # plus de lieux : le plus de points de vie l'emporte
            self.gagnants = [self.noms[c]["id"] for c in self.participants if self.pv[self._cote(c)] == meilleur]
        self.phase = "fin"

    # ------------------------------------------------------------ fin de manche, mode par mode
    def _clore_manche(self):
        lieu = self.lieux[self.numero - 1]
        if self.mode == "amis":
            presents = [c for c in self.participants if c in self.membres]
            lignes = self._lignes_distance(lieu, presents)
            for l, c in zip(lignes, presents):
                self.totaux[c] += l["points"]
            lignes.sort(key=lambda x: -x["points"])
            extra = {}
            fin = self.numero >= NB_MANCHES
        elif self.mode == "duel":
            lignes, extra, fin = self._clore_duel(lieu)
        elif self.mode == "br_distance":
            lignes, extra, fin = self._clore_br_distance(lieu)
        else:
            lignes, extra, fin = self._clore_br_pays(lieu)
        self.resultat = {"numero": self.numero, "lieu": {"lat": lieu["lat"], "lon": lieu["lon"], "pays": lieu["pays"]},
                         "fiche": fiches.fiche(lieu["pays"]), "reponses": lignes, **extra}
        self.echeance = None
        self.phase = "fin" if fin else "resultat"

    def _lignes_distance(self, lieu, cles) -> list[dict]:
        diag = cartes.carte(self.carte_id)["diagonale_km"]
        lignes = []
        for c in cles:
            nom = self.noms.get(c) or {"id": self.membres[c].id, "pseudo": self.membres[c].pseudo}
            r = self.reponses.get(c)
            if r:
                d = geo.distance_m(lieu["lat"], lieu["lon"], r["lat"], r["lon"])
                pts = score.points(d, diag)
            else:
                d, pts = None, 0
            lignes.append({"id": nom["id"], "pseudo": nom["pseudo"], "lat": r["lat"] if r else None,
                           "lon": r["lon"] if r else None, "distance_m": d, "points": pts})
        return lignes

    def _multiplicateur(self, numero):
        return 1.0 if numero <= 4 else 1.0 + MULTIPLICATEUR_PAR_MANCHE * (numero - 4)

    def _nom_cote(self, cote):
        if self.variante == "1v1":
            return self.noms[cote]["pseudo"]
        return "Équipe " + cote

    def _clore_duel(self, lieu):
        presents = [c for c in self.participants if c in self.membres]
        lignes = self._lignes_distance(lieu, presents)
        pts_par_cle = dict(zip(presents, (l["points"] for l in lignes)))
        # la meilleure réponse de chaque côté compte
        par_cote = {}
        for c in presents:
            par_cote[self._cote(c)] = max(par_cote.get(self._cote(c), 0), pts_par_cle[c])
        cotes = sorted(self.pv)
        mult = self._multiplicateur(self.numero)
        a, b = (par_cote.get(cotes[0], 0), par_cote.get(cotes[1], 0)) if len(cotes) == 2 else (0, 0)
        avant = dict(self.pv)
        perdant, degats = None, 0
        if a != b:
            perdant = cotes[1] if a > b else cotes[0]
            degats = int(round(abs(a - b) * mult))
            self.pv[perdant] = max(0, self.pv[perdant] - degats)
        fin = any(v <= 0 for v in self.pv.values())
        if fin:
            gagnant = max(self.pv, key=lambda k: self.pv[k])
            self.gagnants = [self.noms[c]["id"] for c in self.participants if self._cote(c) == gagnant]
        for l, c in zip(lignes, presents):
            l["equipe"] = self.equipes.get(c)
        extra = {"duel": {"cotes": [{"id": k, "nom": self._nom_cote(k), "points": par_cote.get(k, 0),
                                     "pv_avant": avant[k], "pv": self.pv[k]} for k in cotes],
                          "perdant": perdant, "degats": degats, "multiplicateur": mult}}
        return sorted(lignes, key=lambda x: -x["points"]), extra, fin

    def _clore_br_distance(self, lieu):
        actifs = self._actifs()
        cles = [m.cle for m in actifs]
        lignes = self._lignes_distance(lieu, cles)

        def pire(i):          # le plus loin ; sans réponse = infiniment loin ; à égalité, le dernier arrivé dans le salon
            d = lignes[i]["distance_m"]
            return (float("inf") if d is None else d, i)
        sortant = max(range(len(cles)), key=pire)
        self.elimines.append((cles[sortant], self.numero))
        lignes[sortant]["elimine"] = True
        reste = [m for m in self._actifs()]
        fin = len(reste) <= 1
        if fin:
            self.gagnants = [m.id for m in reste]
        lignes.sort(key=lambda x: (x["distance_m"] is None, x["distance_m"] or 0))
        return lignes, {"elimine": self.noms[cles[sortant]]["id"]}, fin

    def _clore_br_pays(self, lieu):
        actifs = self._actifs()
        lignes, perdants = [], []
        for m in actifs:
            r = self.reponses.get(m.cle) or {"essais": [], "trouve": False}
            essais = r["essais"]
            if not r["trouve"]:
                perdants.append(m.cle)
            dernier = essais[-1] if essais else None
            lignes.append({"id": m.id, "pseudo": m.pseudo, "lat": dernier["lat"] if dernier else None,
                           "lon": dernier["lon"] if dernier else None, "distance_m": None, "points": 0,
                           "trouve": r["trouve"], "essais": len(essais)})
        if perdants and len(perdants) == len(actifs):
            # tout le monde a échoué : si cela éliminerait tout le monde, la partie s'arrête sur une égalité
            if all(self.vies[c] <= 1 for c in perdants):
                for c in perdants:
                    self.vies[c] = 0
                for l, m in zip(lignes, actifs):
                    l["vies"] = 0
                self.gagnants = [m.id for m in actifs]
                return lignes, {}, True
        for l, m in zip(lignes, actifs):
            if m.cle in perdants:
                self.vies[m.cle] -= 1
                if self.vies[m.cle] <= 0:
                    self.elimines.append((m.cle, self.numero))
                    l["elimine"] = True
            l["vies"] = self.vies[m.cle]
        reste = self._actifs()
        fin = len(reste) <= 1
        if fin:
            self.gagnants = [m.id for m in reste]
        lignes.sort(key=lambda x: (not x["trouve"], x["essais"]))
        return lignes, {}, fin

    # ------------------------------------------------------------ chat (jamais enregistré)
    def _chat(self, membre, texte):
        if not self.chat_actif and membre.cle != self.hote_cle:
            raise ErreurJeu(403, "L'hôte a coupé le chat.")
        if membre.cle in self.muets:
            raise ErreurJeu(403, "L'hôte t'a rendu muet.")
        t = _nettoyer_chat(texte)
        if not t:
            raise ErreurJeu(400, "Message vide.")
        if len(t) > CHAT_MAX:
            raise ErreurJeu(400, f"Message trop long ({CHAT_MAX} caractères au plus).")
        now = horloge.maintenant()
        if now - membre.dernier_message < CHAT_DELAI_S:
            raise ErreurJeu(429, "Doucement : un message par seconde.")
        membre.dernier_message = now
        self._chats.append({"t": "chat", "id": membre.id, "de": membre.pseudo, "texte": t})

    # ------------------------------------------------------------ temps qui passe
    def tick(self) -> bool:
        """À appeler régulièrement. Renvoie True si l'état a changé (il faut alors diffuser)."""
        now, change = horloge.maintenant(), False
        for m in list(self.membres.values()):
            if m.deconnecte_le is not None and now - m.deconnecte_le > DELAI_RECONNEXION_S:
                self._retirer(m)
                change = True
        if change:
            self._verifier_fin_manche()
        fin = self._delai_fin()
        if self.phase == "manche" and fin is not None and now >= fin + self._marge():
            self._clore_manche()
            change = True
        return change

    def expire(self) -> bool:
        if not self.membres:
            return horloge.maintenant() - self.derniere_activite > DELAI_SALON_VIDE_S
        return not any(m.connecte for m in self.membres.values()) and \
            horloge.maintenant() - self.derniere_activite > DELAI_SALON_VIDE_S

    # ------------------------------------------------------------ ce que chacun voit
    def _classement_final(self) -> list[dict]:
        """Le classement de fin des modes à éliminations ou à points de vie."""
        def ligne(cle, detail, rang=None):
            n = self.noms.get(cle) or {"id": "", "pseudo": "?"}
            return {"id": n["id"], "pseudo": n["pseudo"], "detail": detail}
        if self.mode == "duel":
            cotes = sorted(self.pv, key=lambda k: -self.pv[k])
            if self.variante == "1v1":
                return [ligne(k, f"{self.pv[k]} PV") for k in cotes]
            return [{"id": k, "pseudo": self._nom_cote(k) + " (" + ", ".join(
                self.noms[c]["pseudo"] for c in self.participants if self._cote(c) == k) + ")",
                "detail": f"{self.pv[k]} PV"} for k in cotes]
        gagnants = [c for c in self.participants if self.noms[c]["id"] in self.gagnants]
        sortis = [c for c, _ in reversed(self.elimines) if c not in gagnants]
        out = [ligne(c, "vainqueur" if len(gagnants) == 1 else "à égalité") for c in gagnants]
        num = dict(self.elimines)
        out += [ligne(c, f"éliminé à la manche {num[c]}") for c in sortis]
        return out

    def etat_pour(self, membre) -> dict:
        carte = cartes.carte(self.carte_id)
        manche = None
        jeu = self.mode != "amis"
        if self.phase == "manche":
            fin = self._delai_fin()
            restant = None if fin is None else max(0.0, fin - horloge.maintenant())
            # jamais lat/lon/pays avant la fin de la manche ; seul l'identifiant d'image part (comme en solo)
            manche = {"numero": self.numero, "image": self.lieux[self.numero - 1]["image"], "temps_restant": restant,
                      "a_repondu": self._fini(membre.cle), "compte_a_rebours": self.echeance is not None}
            if self.mode == "br_pays":
                r = self.reponses.get(membre.cle) or {"essais": [], "trouve": False}
                manche["essais"] = {"restants": ESSAIS_BR_PAYS - len(r["essais"]), "trouve": r["trouve"],
                                    "dernier": ({"pays": fiches.fiche(r["essais"][-1]["pays"])["nom"] if r["essais"][-1]["pays"] else None,
                                                 "juste": r["trouve"]} if r["essais"] else None)}
        classement = []
        if self.mode == "amis":
            classement = sorted(((self.totaux.get(m.cle, 0), m.pseudo, m.id) for m in self.joueurs() if m.cle in self.totaux),
                                reverse=True)
        en_cours = self.phase != "attente"
        membres = []
        for m in self.membres.values():
            e = {"id": m.id, "pseudo": m.pseudo, "role": m.role, "connecte": m.connecte,
                 "hote": m.cle == self.hote_cle, "muet": m.cle in self.muets,
                 "a_repondu": self._fini(m.cle) if self.phase == "manche" and m.cle in self.participants else None,
                 "total": self.totaux.get(m.cle) if m.cle in self.totaux else None,
                 "elimine": self._est_elimine(m.cle), "participant": m.cle in self.participants and en_cours}
            if self.mode == "duel":
                e["equipe"] = self.equipes.get(m.cle) if (m.role == "joueur") else None
            if self.mode == "br_pays" and m.cle in self.vies:
                e["vies"] = self.vies[m.cle]
            membres.append(e)
        duel = None
        if self.mode == "duel" and en_cours:
            duel = {"variante": self.variante, "multiplicateur": self._multiplicateur(self.numero + (1 if self.phase != "manche" else 0)),
                    "cotes": [{"id": k, "nom": self._nom_cote(k), "pv": self.pv[k],
                               "membres": [self.noms[c]["id"] for c in self.participants if self._cote(c) == k]}
                              for k in sorted(self.pv)]}
        return {
            "t": "etat", "code": self.code, "mode": self.mode, "phase": self.phase,
            "moi": {"id": membre.id, "role": membre.role, "hote": membre.cle == self.hote_cle, "muet": membre.cle in self.muets,
                    "elimine": self._est_elimine(membre.cle),
                    "equipe": self.equipes.get(membre.cle) if self.mode == "duel" else None},
            "reglages": {"carte": cartes.publique(carte), "contrainte": self.contrainte, "chrono": self.chrono,
                         "mode": self.mode, "nb_manches": NB_MANCHES if self.mode == "amis" else None,
                         "modes": {k: v["nom"] for k, v in MODES.items()},
                         "vies": VIES_BR_PAYS, "essais": ESSAIS_BR_PAYS},
            "chat_actif": self.chat_actif, "verrouille": self.verrouille,
            "membres": membres,
            "manche": manche,
            "duel": duel,
            "resultat": self.resultat if self.phase in ("resultat", "fin") else None,
            "classement": [{"id": i, "pseudo": p, "total": t} for t, p, i in classement],
            "fin_partie": ({"gagnants": self.gagnants, "classement": self._classement_final()}
                           if self.phase == "fin" and jeu else None),
        }

    async def diffuser(self):
        chats, self._chats = self._chats, []
        envois = []
        for m in list(self.membres.values()):
            if m.liaison is None:
                continue
            for c in chats:
                envois.append(_envoyer(self, m, m.liaison, c))
            envois.append(_envoyer(self, m, m.liaison, self.etat_pour(m)))
        if envois:
            await asyncio.gather(*envois)


async def _fermer(liaison):
    try:
        await liaison.fermer()
    except Exception:
        pass


async def _envoyer(salon, membre, liaison, message):
    try:
        await asyncio.wait_for(liaison.envoyer(message), 3)
    except Exception:
        salon.deconnecter(membre, liaison)       # liaison morte : le membre a 60 s pour revenir


class Gestionnaire:
    """Tous les salons en vie."""

    def __init__(self):
        self.salons: dict[str, Salon] = {}

    def creer(self, hote_cle, carte_id, contrainte="libre", chrono=0) -> Salon:
        _carte(carte_id); _reglages(contrainte, chrono)
        if len(self.salons) >= MAX_SALONS:
            raise ErreurJeu(503, "Trop de salons ouverts pour l'instant, réessaie dans quelques minutes.")
        if sum(1 for s in self.salons.values() if s.hote_cle == hote_cle) >= MAX_SALONS_PAR_HOTE:
            raise ErreurJeu(429, "Tu as déjà des salons ouverts : rejoins-en un ou attends qu'ils se ferment.")
        while True:
            code = "".join(secrets.choice(ALPHABET) for _ in range(LONGUEUR_CODE))
            if code not in self.salons:
                break
        self.salons[code] = Salon(code, hote_cle, carte_id, contrainte, chrono)
        return self.salons[code]

    def trouver(self, code) -> Salon:
        s = self.salons.get(str(code or "").strip().upper())
        if s is None:
            raise ErreurJeu(404, "Salon introuvable : vérifie le code.")
        return s

    async def passer_le_temps(self):
        for code, s in list(self.salons.items()):
            if s.expire():
                del self.salons[code]
                continue
            if s.tick():
                await s.diffuser()

    async def boucle(self):
        while True:
            await asyncio.sleep(0.5)
            try:
                await self.passer_le_temps()
            except Exception:
                pass


gestionnaire = Gestionnaire()
