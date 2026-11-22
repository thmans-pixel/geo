# Où suis-je ?

Un jeu de géolocalisation façon GeoGuessr, en français, pour jouer en famille et entre amis.

**Modes** : Classique (5 manches), Défi du jour, Défi à partager par lien, Série de pays, Exploration.
(Comptes, statistiques, cartes personnalisées puis multijoueur arrivent dans les étapes 2 à 4 de la spec.)

## Essayer tout de suite (sans compte Google, sans rien payer)

    pip install -r requirements.txt
    python3 -m uvicorn serveur.app:app --port 8000

Ouvrir http://localhost:8000 : les images sont des fonds de couleur (mode « factice »), mais toutes les
règles, les scores, les défis et la carte fonctionnent.

## Avec les vraies images Street View

1. Créer **deux** clés Google Maps Platform et régler un plafond de quota et un budget avec coupure avant d'ouvrir le site :
   - clé navigateur (`OUSUISJE_GOOGLE_KEY`) : restreinte à l'adresse du site et à l'API Maps JavaScript seule ;
   - clé serveur (`OUSUISJE_GOOGLE_KEY_OUTIL`) : API Street View Static/Metadata seule, jamais montrée au navigateur.
2. Ajouter les contours de pays : voir `serveur/donnees/LISEZMOI.md`.
3. Remplir les réserves de lieux : `OUSUISJE_GOOGLE_KEY_OUTIL=… python3 outils/generer_reserve.py --toutes`
4. Lancer : `OUSUISJE_IMAGES=google OUSUISJE_GOOGLE_KEY=… python3 -m uvicorn serveur.app:app --port 8000`
