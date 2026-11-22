# Où suis-je ? — jeu de géolocalisation (GeoGuessr maison)

Jeu navigateur : Starlette + SQLite côté serveur, JavaScript sans framework côté navigateur.
Spec de référence : `docs/specs/001-jeu-geoguessr.md`. Tout le texte visible est en français.

## Lancer et tester
- Essai sans rien payer : `OUSUISJE_IMAGES=factice python3 -m uvicorn serveur.app:app --port 8000`
- Tests : `python3 -m pytest tests -q` (les tests `test_ui.py` ont besoin de Chrome et de playwright).
- Variables : `OUSUISJE_ENTETE`, `OUSUISJE_ADMIN`, `OUSUISJE_SECRET_PROXY`, `OUSUISJE_URL_CONNEXION`, `OUSUISJE_COMPTE_ESSAI` (comptes, voir README), `OUSUISJE_IMAGES` (factice|google), `OUSUISJE_GOOGLE_KEY` (navigateur), `OUSUISJE_GOOGLE_KEY_OUTIL` (serveur), `OUSUISJE_BASE`, `OUSUISJE_PAYS`, `OUSUISJE_RESERVES`.

## Règles à ne jamais casser
1. **Le serveur décide de tout** : score, distance, pays, éliminations. Le navigateur n'envoie que le point cliqué.
2. **Aucune coordonnée du lieu n'est envoyée avant la réponse** (ni `lat`/`lon`, ni `pays`). Seul l'identifiant de panorama
   Street View part avec l'image (indispensable pour l'afficher ; risque accepté dans la spec).
   `tests/test_api.py::test_pas_de_coordonnees_avant_la_reponse` le garde ; ne l'affaiblis pas.
3. Pas de clé, mot de passe ou secret dans le dépôt. La clé Google se met dans l'environnement du service.
4. Rien ne se paie sans plafond : Street View se limite côté Google (critère 31). Ne jamais charger d'image
   Street View en dehors d'une manche jouée.
5. Enfants : pas d'e-mail, pas de mot de passe stocké (comptes = comptes YunoHost), chat jamais enregistré.
6. Les contours de pays viennent de `serveur/donnees/pays.geojson` (voir `serveur/donnees/LISEZMOI.md`).

7. **Identité = en-tête du reverse proxy** (`serveur/identite.py`). Jamais de route d'inscription, de mot de passe ou d'e-mail.
   Les POST de compte et d'administration exigent `X-Requete: ou-suis-je` ; les routes `/api/admin/*` vérifient `OUSUISJE_ADMIN`.
   Les classements ne montrent que des comptes, jamais des invités.

## Pièges connus
- `ISO_A2` vaut `-99` pour la France et la Norvège dans Natural Earth : `geo._code` lit `ISO_A2_EH` d'abord.
- L'horloge passe par `serveur/horloge.py` (les tests la remplacent) ; ne pas appeler `time.time()` ailleurs.
- Le défi du jour change à minuit **heure de Paris**.
- Pas de `httpx` ici : `tests/client.py` appelle l'application ASGI directement.
