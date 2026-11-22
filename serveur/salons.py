"""Salons multijoueur en temps réel (étape 3, lot 1 : Partie entre amis, spectateurs, chat, reconnexion).

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

from . import horloge
from .jeu import cartes, fiches, geo, lieux as lieux_mod, score
from .jeu.moteur import ErreurJeu, _carte, _lieux, _reglages

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
        self.phase = "attente"                    # attente | manche | resultat | fin
        self.lieux, self.numero, self.debut_le = [], 0, 0.0
        self.reponses: dict[str, dict] = {}
        self.resultat = None
        self.totaux: dict[str, int] = {}
        self.cree_le = self.derniere_activite = horloge.maintenant()
        self._chats: list[dict] = []              # messages à envoyer au prochain diffuser(), jamais gardés

    # ------------------------------------------------------------ membres
    def joueurs(self):
        return [m for m in self.membres.values() if m.role == "joueur"]

    def hote(self) -> Membre | None:
        return self.membres.get(self.hote_cle)

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
            if role == "joueur" and (self.phase != "attente" or len(self.joueurs()) >= MAX_JOUEURS):
                role = "spectateur"          # partie commencée ou salon plein : on peut regarder
            if role == "spectateur" and sum(1 for x in self.membres.values() if x.role == "spectateur") >= MAX_SPECTATEURS:
                raise ErreurJeu(409, "Ce salon est complet.")
            m = self.membres[cle] = Membre(cle, pseudo, role)
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
        self.totaux.pop(membre.cle, None)

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
        _carte(carte_id); _reglages(contrainte, chrono)
        self.carte_id, self.contrainte, self.chrono = carte_id, contrainte, chrono

    def _lancer(self):
        if self.phase != "attente":
            raise ErreurJeu(409, "La partie est déjà lancée.")
        if len(self.joueurs()) < 2:
            raise ErreurJeu(409, "Il faut au moins 2 joueurs pour lancer la partie.")
        self.lieux = _lieux(lieux_mod.tirer, self.carte_id, NB_MANCHES, random.SystemRandom())
        self.totaux = {m.cle: 0 for m in self.joueurs()}
        self.numero = 0
        self.resultat = None
        self._demarrer_manche()

    def _demarrer_manche(self):
        self.numero += 1
        self.phase, self.debut_le, self.reponses, self.resultat = "manche", horloge.maintenant(), {}, None

    def _suivante(self):
        if self.phase != "resultat":
            raise ErreurJeu(409, "La manche n'est pas terminée.")
        self._demarrer_manche()

    def _rejouer(self):
        if self.phase != "fin":
            raise ErreurJeu(409, "La partie n'est pas terminée.")
        self.phase, self.lieux, self.numero, self.reponses, self.resultat, self.totaux = "attente", [], 0, {}, None, {}

    def _repondre(self, membre, lat, lon):
        if self.phase != "manche":
            raise ErreurJeu(409, "Pas de manche en cours.")
        if membre.role != "joueur" or membre.cle not in self.totaux:
            raise ErreurJeu(403, "Les spectateurs ne jouent pas.")
        if membre.cle in self.reponses:
            raise ErreurJeu(409, "Tu as déjà répondu.")
        now = horloge.maintenant()
        if self.chrono and now > self.debut_le + self.chrono + DELAI_REPONSE_TARDIVE_S:
            raise ErreurJeu(409, "Trop tard.")
        if (isinstance(lat, bool) or isinstance(lon, bool) or not isinstance(lat, (int, float))
                or not isinstance(lon, (int, float)) or not (-90 <= lat <= 90 and -180 <= lon <= 180)):
            raise ErreurJeu(400, "Point invalide.")
        self.reponses[membre.cle] = {"lat": float(lat), "lon": float(lon), "le": now}
        self._verifier_fin_manche()

    def _verifier_fin_manche(self):
        if self.phase != "manche":
            return
        actifs = [m for m in self.joueurs() if m.connecte and m.cle in self.totaux]
        if not actifs:
            if not [m for m in self.joueurs() if m.cle in self.totaux]:
                self._terminer_partie()            # plus personne ne joue
            return
        if all(m.cle in self.reponses for m in actifs):
            self._clore_manche()

    def _terminer_partie(self):
        self.phase = "fin"

    def _clore_manche(self):
        lieu = self.lieux[self.numero - 1]
        diag = cartes.carte(self.carte_id)["diagonale_km"]
        lignes = []
        for m in self.joueurs():
            if m.cle not in self.totaux:
                continue
            r = self.reponses.get(m.cle)
            if r:
                d = geo.distance_m(lieu["lat"], lieu["lon"], r["lat"], r["lon"])
                pts = score.points(d, diag)
            else:
                d, pts = None, 0
            self.totaux[m.cle] += pts
            lignes.append({"id": m.id, "pseudo": m.pseudo, "lat": r["lat"] if r else None,
                           "lon": r["lon"] if r else None, "distance_m": d, "points": pts})
        lignes.sort(key=lambda x: -x["points"])
        self.resultat = {"numero": self.numero, "lieu": {"lat": lieu["lat"], "lon": lieu["lon"], "pays": lieu["pays"]},
                         "fiche": fiches.fiche(lieu["pays"]), "reponses": lignes}
        self.phase = "fin" if self.numero >= NB_MANCHES else "resultat"

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
        if self.phase == "manche" and self.chrono and now >= self.debut_le + self.chrono + DELAI_REPONSE_TARDIVE_S:
            self._clore_manche()
            change = True
        return change

    def expire(self) -> bool:
        if not self.membres:
            return horloge.maintenant() - self.derniere_activite > DELAI_SALON_VIDE_S
        return not any(m.connecte for m in self.membres.values()) and \
            horloge.maintenant() - self.derniere_activite > DELAI_SALON_VIDE_S

    # ------------------------------------------------------------ ce que chacun voit
    def etat_pour(self, membre) -> dict:
        carte = cartes.carte(self.carte_id)
        manche = None
        if self.phase == "manche":
            restant = None
            if self.chrono:
                restant = max(0.0, self.debut_le + self.chrono - horloge.maintenant())
            # jamais lat/lon/pays avant la fin de la manche ; seul l'identifiant d'image part (comme en solo)
            manche = {"numero": self.numero, "image": self.lieux[self.numero - 1]["image"], "temps_restant": restant,
                      "a_repondu": membre.cle in self.reponses}
        classement = sorted(((self.totaux.get(m.cle, 0), m.pseudo, m.id) for m in self.joueurs() if m.cle in self.totaux),
                            reverse=True)
        return {
            "t": "etat", "code": self.code, "mode": self.mode, "phase": self.phase,
            "moi": {"id": membre.id, "role": membre.role, "hote": membre.cle == self.hote_cle, "muet": membre.cle in self.muets},
            "reglages": {"carte": cartes.publique(carte), "contrainte": self.contrainte, "chrono": self.chrono,
                         "nb_manches": NB_MANCHES},
            "chat_actif": self.chat_actif, "verrouille": self.verrouille,
            "membres": [{"id": m.id, "pseudo": m.pseudo, "role": m.role, "connecte": m.connecte,
                         "hote": m.cle == self.hote_cle, "muet": m.cle in self.muets,
                         "a_repondu": (m.cle in self.reponses) if self.phase == "manche" else None,
                         "total": self.totaux.get(m.cle) if m.cle in self.totaux else None}
                        for m in self.membres.values()],
            "manche": manche,
            "resultat": self.resultat if self.phase in ("resultat", "fin") else None,
            "classement": [{"id": i, "pseudo": p, "total": t} for t, p, i in classement],
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
