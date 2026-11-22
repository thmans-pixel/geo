# Données du jeu

- `cartes.json` : les 6 cartes (zone, filtre de pays, diagonale pour le score).
- `graines.json` : lieux de démonstration (mode image « factice ») et centres des « Villes célèbres ».
- `fiches_pays.json` : fiches découverte (capitale, langues, sens de circulation, indices).
- `pays.geojson` : **contours des pays, à ajouter** (Natural Earth, domaine public). Nécessaire à la Série de
  pays et à `outils/generer_reserve.py`. Prendre la version 50 m (la 110 m n'a pas les petits pays) :

      curl -L -o serveur/donnees/pays.geojson \
        https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_countries.geojson

  Puis vérifier : `python3 outils/verifier_pays.py`.
