---
numero: 001
titre: Jeu de géolocalisation façon GeoGuessr (solo, défis, multijoueur)
depot: autre (nouveau dépôt, nom proposé thmans-pixel/geo)
statut: en cours
date: 2026-11-22
---

# 001 — Jeu de géolocalisation façon GeoGuessr

Titre de travail : **« Où suis-je ? »** — adresse proposée : `geo.izicraft.fr`.

## Le besoin, en une phrase
Thibault veut une appli « type GeoGuessr » jouable dans le navigateur, avec **toutes les fonctionnalités
possibles**, le **multijoueur** et **plusieurs modes de jeu**, pour jouer en famille et entre amis.

## Ce que ça change pour qui
- Léo / Arthur : un jeu de géographie à jouer seuls, contre papa ou entre eux en ligne. Après chaque manche,
  une fiche découverte du pays (drapeau, langue, sens de circulation, indices pour le reconnaître).
- Thibault (parent, admin) : héberge le jeu sur thnas, crée les cartes personnalisées (ex. « La Drôme »),
  crée les comptes YunoHost des joueurs réguliers, surveille le quota d'images.
- Les amis / autres parents : jouent en invité par lien de défi ou code de salon, ou avec un compte YunoHost créé par Thibault.

Décisions de Thibault (2026-11-22) : images **Google Street View** ; jeu en **invité ouvert**, comptes par
**compte YunoHost** (pas d'inscription sur le site) ; **chat libre** dans les salons, ouvert à tous ceux
qui y sont entrés avec le code ; nom « Où suis-je ? », `geo.izicraft.fr`, dépôt `thmans-pixel/geo`.

## Hors périmètre
- Appli mobile native (le site s'adapte au téléphone, c'est tout).
- Paiement, abonnement, publicité.
- Messages privés entre joueurs et chat en dehors d'un salon (le chat n'existe que dans un salon en cours).
- Prise de photos par les joueurs eux-mêmes.
- Classement mondial ouvert à n'importe quel inscrit d'Internet.
- Mode « devine le drapeau » ou quiz hors image de rue.
- Lien avec MindCraft (possible plus tard dans une spec à part).

## Les modes de jeu

| Mode | Joueurs | Principe |
|---|---|---|
| **Classique** | solo | 5 manches sur une carte, jusqu'à 5 000 points par manche selon la distance. |
| **Défi partagé** | solo, asynchrone | Un joueur crée une partie, partage un lien : tout le monde joue les **mêmes 5 lieux**, classement du défi. |
| **Défi du jour** | solo | Mêmes 5 lieux pour tous chaque jour, une seule tentative, classement du jour. |
| **Série de pays** | solo | Deviner le pays (clic sur la carte) ; la série continue tant qu'on a juste. Record personnel. |
| **Partie entre amis** | 2–10, temps réel | Salon avec code ; l'hôte choisit carte, contraintes, chrono ; tout le monde joue la même manche en même temps. |
| **Duel** | 1 contre 1 ou équipes 2 contre 2 | 6 000 points de vie chacun. À chaque manche, le moins précis perd l'écart de score × multiplicateur (×1 aux manches 1–4, puis +0,5 par manche). Dès que le premier a répondu, l'autre a 15 s. |
| **Bataille royale – distance** | 3–10 | Chaque manche, le plus loin est éliminé. |
| **Bataille royale – pays** | 3–10 | Deviner le pays, 3 essais par manche ; qui échoue perd une vie (3 vies). Dernier en vie gagne. |
| **Exploration** | solo | Pas de score : on se balade, on révèle le lieu quand on veut, fiche découverte. Idéal pour Arthur. |

**Contraintes** réglables pour tous les modes à score : *Libre* (se déplacer, tourner, zoomer),
*Sans déplacement*, *Figé* (ni déplacement, ni rotation, ni zoom). **Chrono** par manche : aucun, 10 s, 30 s,
60 s, 2 min, 5 min.

**Cartes** livrées : Monde, Europe, France, Auvergne-Rhône-Alpes, Drôme–Ardèche, Villes célèbres,
plus les **cartes personnalisées** créées par Thibault dans l'éditeur.

## Critères d'acceptation
Chacun se vérifie par un test automatique ou par une manipulation précise.

### Étape 1 — Le jeu solo
1. [ ] Quand je lance une partie Classique sur « Monde », alors je vois une image de rue à 360° et une
   mini-carte où poser mon repère, et le bouton « Valider » ne s'active qu'une fois le repère posé.
   — *Vérification :* manipulation dans le navigateur.
2. [x] Quand je valide, alors l'écran de manche montre ma réponse, le vrai lieu, une ligne entre les deux,
   la distance en km (ou m sous 1 km) et les points. — *Vérification :* manipulation.
3. [x] Le score suit `5000 × e^(−10 × d / D)` (d = distance, D = diagonale de la carte), arrondi, et vaut
   5 000 sous 25 m ; il est calculé **par le serveur**, jamais par le navigateur.
   — *Vérification :* test automatique sur des distances connues (0 m, 25 m, D/10, D).
4. [x] Le navigateur ne reçoit les coordonnées du lieu qu'**après** la réponse du joueur.
   — *Vérification :* test automatique de l'API + lecture de l'onglet Réseau pendant une manche.
5. [ ] En contrainte *Sans déplacement*, les flèches de déplacement sont absentes ; en *Figé*, rotation et
   zoom sont aussi bloqués. — *Vérification :* manipulation sur les trois contraintes.
6. [x] Quand le chrono arrive à zéro sans repère, la manche vaut 0 point ; avec un repère posé, il est
   validé automatiquement. — *Vérification :* test automatique + manipulation à 10 s.
7. [x] En fin de partie, un récapitulatif montre les 5 manches sur une carte et le total sur 25 000.
   — *Vérification :* manipulation.
8. [x] « Défi partagé » produit un lien ; deux personnes qui l'ouvrent jouent les mêmes 5 lieux dans le même
   ordre et voient le classement du défi. — *Vérification :* test automatique + deux navigateurs.
9. [x] Le défi du jour change à minuit (heure de Paris), est identique pour tous, et ne se joue qu'une fois
   par joueur. — *Vérification :* test automatique avec une horloge simulée.
10. [x] En Série de pays, une réponse juste incrémente la série, une fausse l'arrête et montre le bon pays ;
    le pays est déterminé par le serveur à partir de contours de pays embarqués (aucun service extérieur).
    — *Vérification :* test automatique sur une liste de points connus (Valence → France, Genève → Suisse…).
11. [ ] Après chaque manche, la fiche découverte du pays s'affiche (drapeau, capitale, langue, sens de
    circulation, 2–3 indices visuels). — *Vérification :* manipulation sur 3 pays.
12. [x] Le mode Exploration n'affiche aucun score et révèle le lieu sur demande. — *Vérification :* manipulation.
13. [ ] Le jeu est jouable sur téléphone (image plein écran, mini-carte repliable).
    — *Vérification :* manipulation sur un téléphone ou l'affichage mobile du navigateur.
14. [ ] Tout le texte est en français. — *Vérification :* relecture de l'interface.

### Étape 2 — Comptes, statistiques, cartes personnalisées
15. [ ] On peut jouer sans compte (invité avec un pseudo) ; un invité n'entre dans un salon qu'avec son
    **code**. Il n'y a **aucune inscription** sur le site : les comptes sont les **comptes YunoHost** de thnas,
    créés par Thibault. — *Vérification :* test automatique (aucune route d'inscription ; salon sans code → refus).
16. [ ] « Se connecter » passe par l'identification YunoHost ; le jeu ne stocke **aucun mot de passe**, seulement
    l'identifiant YunoHost et un pseudo d'affichage modifiable. — *Vérification :* connexion avec un compte
    YunoHost de test + lecture du schéma de la base.
17. [x] La page profil montre : parties jouées, meilleur score par carte, distance moyenne, record de Série
    de pays, pays les mieux et les moins bien reconnus, historique des 20 dernières parties.
    — *Vérification :* manipulation après quelques parties.
18. [x] Des succès se débloquent (ex. « 5 000 points sur une manche », « Série de 10 », « 50 pays trouvés »)
    et un niveau monte avec l'expérience. — *Vérification :* test automatique sur chaque succès.
19. [x] Classements entre comptes : par carte, défi du jour, record de série. — *Vérification :* manipulation.
20. [x] Dans l'éditeur, Thibault crée une carte en cliquant des lieux ou en traçant une zone ; le serveur ne
    garde que les points où une image existe, et la carte devient jouable dans tous les modes.
    — *Vérification :* créer « La Drôme » avec une zone, jouer une partie dessus.

### Étape 3 — Multijoueur en temps réel
21. [ ] L'hôte crée un salon, obtient un code à 6 caractères ; les autres le rejoignent avec ce code
    (compte ou invité) ; l'hôte règle mode, carte, contraintes, chrono puis lance.
    — *Vérification :* 3 navigateurs sur le même salon.
22. [ ] En Partie entre amis, tout le monde voit la même image en même temps ; à la fin de la manche, les
    repères de tous s'affichent avec un classement. — *Vérification :* 3 navigateurs.
23. [ ] Le Duel applique la règle des points de vie et du multiplicateur ; l'adversaire voit un compte à rebours
    de 15 s dès la première réponse. — *Vérification :* test automatique de la règle + 2 navigateurs.
24. [ ] Duel en équipes 2 contre 2 : c'est la meilleure réponse de chaque équipe qui compte.
    — *Vérification :* test automatique.
25. [ ] Bataille royale distance et pays : éliminations conformes aux règles du tableau ; les éliminés restent
    en spectateurs. — *Vérification :* test automatique + 3 navigateurs.
26. [ ] On peut rejoindre un salon en **spectateur** (voit tout, ne joue pas). — *Vérification :* manipulation.
27. [ ] Un joueur dont la connexion coupe moins de 60 s reprend sa place ; au-delà, il est retiré et la
    partie continue. — *Vérification :* couper le réseau d'un onglet 20 s puis 90 s.
28. [ ] Chaque salon a un **chat écrit libre** et des émoticônes, visibles seulement des personnes présentes
    dans le salon ; l'hôte peut couper le chat du salon, rendre muet un joueur ou l'exclure.
    — *Vérification :* 3 navigateurs + test automatique (un joueur muet ou exclu ne peut plus écrire).
29. [ ] Les messages du chat ne sont **enregistrés nulle part** (ni base, ni journaux) et disparaissent à la
    fermeture du salon ; longueur limitée à 200 caractères, 1 message par seconde au plus, liens non cliquables.
    — *Vérification :* test automatique + lecture de la base et des journaux après une partie.

### Étape 4 — Mise en ligne
30. [ ] Le jeu répond sur `https://geo.izicraft.fr` (thnas, YunoHost) et les salons fonctionnent depuis
    l'extérieur. — *Vérification :* partie à deux, dont un sur la 4G.
31. [ ] Un plafond d'images par jour est réglé côté fournisseur d'images ; une fois atteint, le jeu affiche
    « Plus d'images pour aujourd'hui, reviens demain » au lieu de planter, et **aucune facture** ne peut
    dépasser zéro. — *Vérification :* plafond réglé très bas en test, puis remis.

## Conception
- **Ce qui existe déjà et qu'on réutilise :** la recette d'elite27 et de tower — jeu navigateur servi par un
  serveur Python, site sur thnas derrière un sous-domaine izicraft.fr, parties en ligne avec code de partie.
- **Ce qu'on ajoute :**
  - **Serveur** Python (Starlette + WebSocket pour le temps réel, SQLite pour comptes, défis, scores, cartes).
    C'est lui qui tire les lieux, calcule distances, scores, pays et éliminations : le navigateur ne fait
    qu'afficher.
  - **Navigateur** : JavaScript sans framework ; image de rue par Google Street View (API JavaScript Maps) ;
    mini-carte maison sans dépendance (tuiles OpenStreetMap ; Leaflet n'a pu être ni téléchargé ni testé hors ligne).
  - **Réserves de lieux** : pour chaque carte, un script tire à l'avance des points dans la zone et garde
    ceux où une image existe (la vérification d'existence d'image Street View est gratuite et illimitée).
    Une partie pioche dans cette réserve : pas d'image noire, pas d'attente.
  - **Pays** : contours de pays Natural Earth (domaine public) simplifiés, embarqués ; test « point dans
    polygone » en Python pur. Fiches découverte dans un fichier JSON écrit à la main.
  - **Administration** (compte de Thibault) : éditeur de cartes, compteur d'images
    consommées, exclusion d'un compte. Est administrateur l'identifiant YunoHost désigné dans la configuration.
  - **Connexion** : identification YunoHost (SSO de thnas) ; le jeu reste accessible sans connexion pour les invités.
- **Choix écartés :**
  - Calcul du score dans le navigateur : trop facile à truquer, et le serveur en a besoin pour le multijoueur.
  - Images libres (Mapillary, Panoramax) : couverture trop trouée hors de France pour les modes Monde et pays.
  - Émoticônes seules dans les salons : Thibault préfère un vrai chat.

## Fichiers touchés (prévision)
- `serveur/app.py` — routes web, WebSocket des salons
- `serveur/jeu/` — score, tirage des lieux, règles des modes, détection du pays
- `serveur/salons.py` — salons temps réel, reconnexion, spectateurs
- `serveur/base.py` + `serveur/migrations/` — SQLite
- `serveur/donnees/pays.geojson`, `serveur/donnees/fiches_pays.json`, `serveur/donnees/cartes/`
- `outils/generer_reserve.py` + `outils/verifier_pays.py` — remplit les réserves / vérifie les contours de lieux d'une carte
- `web/` — pages, JS du jeu, de la carte, des salons, de l'éditeur, styles
- `tests/` — tests automatiques (score, pays, défis, duel, bataille royale, connexion, API)
- `CLAUDE.md`, `README.md` — conventions du dépôt, lancement, mise en ligne
- `deploiement/` — service systemd et réglages YunoHost pour thnas

## Risques
- **Enfants / vie privée :** Léo et Arthur auront un compte et joueront en ligne avec d'autres personnes →
  pas d'e-mail ni de mot de passe stockés par le jeu, comptes créés par Thibault seulement, pseudo seul visible, exclusion par l'hôte.
  **Relecture `gardien-enfants` obligatoire** avant validation. Rien ne part à une IA.
- **Chat libre et enfants :** un salon se rejoint avec un simple code et le jeu en invité est ouvert à tous :
  si un code circule, un inconnu peut écrire à Léo ou Arthur. Garde-fous prévus : chat limité au salon, hôte
  qui coupe / rend muet / exclut, rien d'enregistré, liens non cliquables. Thibault a choisi que tous les présents puissent
  écrire : le code du salon fait office d'invitation, à ne partager qu'avec des personnes connues.
- **Images de rue :** elles peuvent montrer n'importe quoi dans la rue (le fournisseur floute visages et
  plaques). Le mode « Villes célèbres » et les cartes perso limitent la surprise.
- **Coût :** Google Street View exige un compte de facturation avec carte bancaire ; sans plafond, un abus
  pourrait coûter cher → plafond journalier obligatoire (critère 31) et accès public limité au jeu invité.
- **Triche :** l'identifiant d'image envoyé au navigateur permet, avec des outils, de retrouver le lieu.
  Acceptable entre famille et amis ; ce n'est pas un jeu à enjeu.
- **thnas jugé instable (RAID 0) :** la base SQLite est petite ; l'ajouter à la sauvegarde restic existante.
- **Données / migrations :** nouvelle base, rien à migrer.
- **Contrat entre dépôts :** aucun.

## Étapes
1. Le jeu solo : Classique, contraintes, chrono, récap, Défi partagé, Défi du jour, Série de pays,
   Exploration, fiches pays, cartes livrées (critères 1–14). *Livré en 2 lots.*
2. Comptes, profils, statistiques, succès, classements, éditeur de cartes (critères 15–20).
3. Multijoueur temps réel : salons, Partie entre amis, Duel, équipes, Batailles royales, spectateurs,
   chat, émoticônes (critères 21–29). *Livré en 2 lots.*
4. Mise en ligne sur geo.izicraft.fr avec plafond d'images (critères 30–31).

## Questions ouvertes
(aucune)

## Livraison — étape 1 (jeu solo)
**Fait :** serveur (score, pays, chrono, défis, série, exploration), mini-carte, écrans, fiches de 57 pays,
6 cartes, 121 lieux de démonstration, générateur de réserve Street View, 42 tests (tous verts, mutations
volontaires détectées). Tous les modes de l'étape 1 sont livrés en un seul lot, pas deux.

**Écart à la spec :** mini-carte écrite à la main au lieu de Leaflet (non téléchargeable ici, donc intestable).

**Cochés** : 2, 3, 4, 6, 7, 8, 9, 10, 12 (le 2 et le 10 aussi vérifiés à la main par Thibault le 2026-11-23 :
score de 127 points pour 5 483 km sur Monde, clic aux États-Unis reconnu avec les vrais contours Natural Earth 50 m,
`verifier_pays.py` : 121 lieux sur 121 dans le bon pays). **Non cochés, à vérifier à la main :**
- 1 et 5 : vrai Street View (image 360°, flèches, rotation, zoom) — seul le mode « factice » a été testé.
- 11 : relire les fiches pays (contenu écrit de mémoire). 13 : essai sur un vrai téléphone. 14 : relecture du texte.

**Avant la mise en ligne (étape 4) :** deux clés Google distinctes avec plafond et budget ; limite de débit
nginx sur `/api/parties` et `/api/defis` ; cookie `Secure` ; page « Données et vie privée » et purge des
anciennes parties ; liste de pseudos refusés ou retrait d'une ligne du classement public (à décider) ;
en-têtes de sécurité. Relecture `gardien-enfants` faite sur l'étape 1 ; à refaire sur les étapes 2 et 3.

## Livraison — étape 2 (comptes, profil, éditeur)
**Fait :** identité par en-tête du SSO YunoHost (aucune inscription, aucun mot de passe ni e-mail stocké), pseudo
neutre « Joueur-NNNN » à la première connexion puis modifiable, profil (stats, 20 dernières parties, pays), 8 succès
et niveaux, classements entre comptes (par carte, défi du jour, série), éditeur de cartes réservé à l'administrateur
(points ou zone, vérification des images côté serveur, archivage), 56 tests verts. Relecture `gardien-enfants` faite :
usurpation de l'en-tête (corrigée : seulement depuis 127.0.0.1 + secret optionnel), cookie `joueur_id` forgé (corrigé),
pseudo par défaut sans l'identifiant (corrigé), pseudo des défis à jour (corrigé).

**Cochés :** 17, 18, 19, 20 (testés avec l'image factice). **Non cochés :**
- 15 : l'absence d'inscription est testée, mais le salon à code relève de l'étape 3.
- 16 : à vérifier sur thnas avec un vrai compte YunoHost (en-tête `Remote-User` posé par SSOwat, et vide pour un visiteur).
- 20 en vrai : créer « La Drôme » avec une zone et la clé Google serveur, jouer dessus.
- Non fait : exclusion d'un compte par l'administrateur ; compteur d'usage des images (étape 4).

**Avant la mise en ligne (étape 4), en plus de l'étape 1 :** exiger `X-Requete` sur tous les POST (jeu compris) ; liste de
pseudos refusés ou pseudos uniques ; suppression de compte et purge des parties ; migration de base atomique.

