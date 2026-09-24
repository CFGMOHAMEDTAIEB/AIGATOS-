# Checklist d'enregistrement — démonstration jury AIGATOS

## Avant l'enregistrement

- [ ] Fermer notifications, messageries, applications personnelles et gestionnaires de mots de passe.
- [ ] Vérifier Docker Desktop, PostgreSQL et Redis.
- [ ] Démarrer FastAPI, Celery `--pool=solo` et Vite sur les adresses locales documentées.
- [ ] Vérifier les neuf endpoints de lecture et le téléchargement du PDF v2.
- [ ] Vérifier : workflow `WAITING_FOR_HUMAN_APPROVAL`, approval `PENDING`, campagne `draft`, Canary 3 `pending`, `actions_executed=0`.
- [ ] Utiliser un profil navigateur propre, 1920×1080, zoom 100 %, favoris masqués.
- [ ] Vérifier qu'aucun onglet ne contient `.env`, `kaggle.json`, une console ou un dossier `secrets`.
- [ ] Faire un parcours à blanc avec les scripts de narration.

## Pendant l'enregistrement

- [ ] Capturer exclusivement la fenêtre du navigateur.
- [ ] Garder un curseur visible et des déplacements lents.
- [ ] Ne cliquer ni Approve ni Reject.
- [ ] Ne déclencher ni génération LLM, ni simulation, ni recommandation, ni Canary 3.
- [ ] Ne montrer aucun terminal, chemin personnel, header Authorization ou valeur de clé.
- [ ] Laisser les chargements se terminer avant chaque mouvement.
- [ ] Utiliser uniquement des transitions simples.

## Après l'enregistrement

- [ ] Regarder la vidéo complète à vitesse normale.
- [ ] Vérifier lisibilité, cadrage, absence de notifications et absence de secrets.
- [ ] Vérifier les quatre identifiants de démonstration.
- [ ] Vérifier la synchronisation des titres et sous-titres.
- [ ] Vérifier à nouveau tous les invariants PostgreSQL.
- [ ] Confirmer que Replay n'a émis que des requêtes GET.
- [ ] Contrôler durée, résolution 1920×1080, 30 fps, H.264 et AAC si une narration humaine est ajoutée.
- [ ] Contrôler la taille : moins de 200 Mo pour la vidéo jury, moins de 150 Mo pour la vidéo agentique.
- [ ] Calculer le SHA-256 de chaque MP4.
- [ ] Arrêter tous les services temporaires.

