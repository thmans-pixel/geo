# Mise en ligne de « Où suis-je ? » sur thnas (geo.izicraft.fr)

Rien de secret dans ce dossier. Les clés vont dans `/etc/ou-suis-je.env` (voir `ou-suis-je.env.exemple`).
Ce guide se déroule **une action à la fois**.

## 0. Ce qui n'a pas pu être essayé depuis le nuage
Vraies images Street View, vrai serveur WebSocket (`websockets`), vraie connexion YunoHost (SSOwat).
Les critères 1, 5, 11, 13, 14, 16, 20, 27, 30 et 31 de la spec se vérifient donc ici, à la main.

## 1. Google : clés et plafond (avant tout le reste)
1. Console Google Cloud : créer un projet « ou-suis-je », y activer la facturation avec un budget et des alertes (ex. 10 €).
   **Attention : un budget Google n'envoie que des alertes, il ne coupe rien.** Le seul vrai plafond est le quota journalier (point 4),
   réglé sous la limite gratuite ; le compteur du jeu n'est qu'indicatif (la clé navigateur est publique, un rechargement de page ne compte pas).
2. Activer **Maps JavaScript API** et **Street View Static API**.
3. Créer **deux clés** :
   - clé navigateur : restriction « Référents HTTP » = `https://geo.izicraft.fr/*`, API = Maps JavaScript seulement ;
   - clé serveur (outil de réserve) : restriction à l'API Street View Static, à n'utiliser qu'en ligne de commande.
4. **Plafond côté Google (le vrai garde-fou, critère 31)** : *API et services → Maps JavaScript API → Quotas* :
   limiter les « chargements de panorama » par jour à la valeur voulue. `OUSUISJE_PLAFOND_IMAGES` n'est que la ceinture en plus.
5. Quand le plafond est atteint, le jeu affiche « Plus d'images pour aujourd'hui, reviens demain. »

## 2. Installation
```
sudo useradd --system --home /opt/ou-suis-je ou-suis-je
sudo mkdir -p /opt/ou-suis-je /var/lib/ou-suis-je && sudo chown ou-suis-je: /var/lib/ou-suis-je
# copier le dépôt dans /opt/ou-suis-je, puis :
python3 -m venv /opt/ou-suis-je/venv && /opt/ou-suis-je/venv/bin/pip install -r /opt/ou-suis-je/requirements.txt
```
`websockets` fait partie de `requirements.txt` : sans elle les salons ne marchent pas.

## 3. Réserve de lieux
Avec la clé serveur : `OUSUISJE_GOOGLE_KEY_OUTIL=… python3 outils/generer_reserve.py --toutes`
(et déposer `serveur/donnees/pays.geojson`, voir `serveur/donnees/LISEZMOI.md`).

## 4. Service
1. `/etc/ou-suis-je.env` : copier l'exemple, remplir, `chmod 600`, propriétaire root. Générer le secret : `openssl rand -hex 32`.
2. Copier `ou-suis-je.service` dans `/etc/systemd/system/`, puis `systemctl enable --now ou-suis-je`.
3. Un seul processus (les salons sont en mémoire). Ne jamais ajouter `--workers`, ni `--log-level debug`.

## 5. Domaine et nginx (YunoHost)
1. Ajouter le domaine `geo.izicraft.fr` dans YunoHost (certificat Let's Encrypt).
2. Placer `nginx-geo.conf` dans `/etc/nginx/conf.d/geo.izicraft.fr.d/`, mettre le même secret que dans `/etc/ou-suis-je.env`, `nginx -t`, recharger.
3. Le jeu doit rester ouvert aux invités : l'accès ne doit pas être réservé aux comptes dans YunoHost (permission « visiteurs »).

## 6. Vérifications à la main
- **Journaux sans code de salon** : après une partie en salon, `journalctl -u ou-suis-je | grep -iE "ws/|salon"` et `grep -ri "salon=" /var/log/nginx/` ne doivent rien renvoyer (y compris les journaux de YunoHost pour le domaine).
- **En-tête truqué (critère 16, à faire AVANT d'ouvrir le site)** : depuis un navigateur non connecté, `curl -s -H 'Remote-User: <admin>' https://geo.izicraft.fr/api/moi` doit répondre « invité », et `curl -s -H 'Remote-User: <admin>' https://geo.izicraft.fr/api/admin/usage` doit être refusé. Si ça répond « connecté », **couper le site** et corriger nginx.
- Connecté avec un compte YunoHost : le pseudo et le niveau apparaissent.
- Deux joueurs dans un salon, l'un en 4G (critère 30) ; couper le réseau 10 s pendant une manche (critère 27).
- Plafond (critère 31) : mettre `OUSUISJE_PLAFOND_IMAGES=2`, jouer, voir le message, puis remettre la vraie valeur.
- Page « Éditeur de cartes » (administrateur) : affiche le nombre d'images du jour.

## 7. Effacer les données de quelqu'un
`OUSUISJE_BASE=… python3 outils/supprimer_compte.py <identifiant>` (compte) ou `… --invite <joueur_id>` (invité).
Les sauvegardes restic déjà faites gardent l'ancienne copie jusqu'à leur expiration.

## 8. Sauvegarde et vie privée
Sauvegarder `/var/lib/ou-suis-je/jeu.sqlite3`. Le chat n'est enregistré nulle part. Les vieilles parties sont purgées
chaque jour (invités 90 jours, comptes 365 jours). La page `/vie-privee.html` décrit cela aux joueurs.
