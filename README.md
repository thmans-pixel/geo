# Où suis-je ?

Un jeu de géolocalisation façon GeoGuessr, en français, pour jouer en famille et entre amis.

**Modes** : Classique (5 manches), Défi du jour, Défi à partager par lien, Série de pays, Exploration.
**Comptes** : les comptes sont ceux de YunoHost (aucune inscription sur le site, aucun mot de passe stocké). Une fois connecté :
profil, statistiques, succès, niveaux, classements. L'administrateur dispose en plus d'un éditeur de cartes.
**Partie entre amis** : un salon avec un code à 6 caractères, 2 à 10 joueurs, spectateurs, chat écrit (jamais enregistré),
reconnexion en moins de 60 s. **Duel** (1 contre 1, ou 2 contre 2 en équipes : la meilleure réponse de chaque équipe compte) et **Batailles royales**
(« distance » : le plus loin est éliminé ; « pays » : 3 essais et 3 vies par personne) se choisissent dans le salon. (Mise en ligne : étape 4.)

## Essayer tout de suite (sans compte Google, sans rien payer)

    pip install -r requirements.txt
    python3 -m uvicorn serveur.app:app --port 8000

Ouvrir http://localhost:8000 : les images sont des fonds de couleur (mode « factice »), mais toutes les
règles, les scores, les défis et la carte fonctionnent.

## Salons en temps réel

Le temps réel passe par un WebSocket : `pip install -r requirements.txt` installe `websockets`, nécessaire à uvicorn.
Derrière nginx, la route `/ws/` doit laisser passer l'en-tête `Upgrade` (voir l'étape 4). Les salons vivent en mémoire :
un redémarrage du service les ferme. Un seul processus uvicorn (pas de `--workers`).
Lancer uvicorn avec `--no-access-log --ws-max-size 4096` (pas de journal d'accès, trames limitées) et jamais en `--log-level debug`
ou `trace`, qui écrivent le contenu des trames, donc le chat.

## Comptes (YunoHost)

Le site lit l'identifiant de la personne connectée dans un en-tête posé par le reverse proxy (SSO YunoHost).
- `OUSUISJE_ENTETE` : nom de l'en-tête (défaut `Remote-User`) ; `OUSUISJE_ADMIN` : identifiant de l'administrateur ;
  `OUSUISJE_URL_CONNEXION` : adresse du portail de connexion (défaut `/yunohost/sso/`).
- **L'application doit écouter sur 127.0.0.1 uniquement, derrière nginx, et nginx doit remplacer cet en-tête** :
  sinon n'importe qui pourrait se faire passer pour un compte. Le code ne croit l'en-tête que s'il arrive de 127.0.0.1 ;
  en plus, `OUSUISJE_SECRET_PROXY=<secret>` exige que nginx pose `X-Auth-Secret: <secret>` (recommandé).
- Essai local : `OUSUISJE_COMPTE_ESSAI=thibault OUSUISJE_ADMIN=thibault` (ignoré en mode `google`).

## Avec les vraies images Street View

1. Créer **deux** clés Google Maps Platform et régler un plafond de quota et un budget avec coupure avant d'ouvrir le site :
   - clé navigateur (`OUSUISJE_GOOGLE_KEY`) : restreinte à l'adresse du site et à l'API Maps JavaScript seule ;
   - clé serveur (`OUSUISJE_GOOGLE_KEY_OUTIL`) : API Street View Static/Metadata seule, jamais montrée au navigateur.
2. Ajouter les contours de pays : voir `serveur/donnees/LISEZMOI.md`.
3. Remplir les réserves de lieux : `OUSUISJE_GOOGLE_KEY_OUTIL=… python3 outils/generer_reserve.py --toutes`
4. Lancer : `OUSUISJE_IMAGES=google OUSUISJE_GOOGLE_KEY=… python3 -m uvicorn serveur.app:app --port 8000`
