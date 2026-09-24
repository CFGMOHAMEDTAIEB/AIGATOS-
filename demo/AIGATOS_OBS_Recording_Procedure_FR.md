# Procédure OBS Studio — AIGATOS

OBS Studio et FFmpeg ne sont pas présents dans l'environnement actuel. Cette procédure permet une capture sûre dès qu'OBS est installé avec l'autorisation du propriétaire de la machine.

## 1. Préparer les services

1. Démarrer PostgreSQL et Redis avec `infrastructure\compose.yaml`.
2. Démarrer FastAPI sur `127.0.0.1:8000`.
3. Démarrer Celery avec `--pool=solo`.
4. Démarrer Vite sur `127.0.0.1:5173`.
5. Vérifier les invariants PostgreSQL avant toute capture.

## 2. Préparer le navigateur

1. Utiliser un profil propre sans compte personnel visible.
2. Régler la fenêtre à 1920×1080 et le zoom à 100 %.
3. Masquer favoris, extensions et panneaux latéraux.
4. Ouvrir `http://127.0.0.1:5173/` pour la vidéo jury ou la route `/workflows/cde0930e-b80a-447f-8ccc-92c6d97b11ba/interaction` pour la vidéo agentique.
5. Fermer les outils développeur et tout terminal.

## 3. Configurer OBS

1. Créer une scène `AIGATOS_BROWSER_ONLY`.
2. Ajouter une source **Capture de fenêtre** ciblant uniquement le navigateur.
3. Ne pas utiliser **Capture d'écran**, qui pourrait exposer des notifications.
4. Canvas et sortie : 1920×1080.
5. Fréquence : 30 fps.
6. Enregistrement : MKV pendant la capture, puis **Fichier → Remuxer les enregistrements** vers MP4.
7. Encodeur : H.264 matériel si disponible, sinon x264.
8. Débit recommandé : 4 500 à 6 000 kb/s ; audio AAC 160 kb/s uniquement si une narration humaine est enregistrée.
9. Désactiver le son système. Conserver seulement le microphone autorisé.
10. Dossier temporaire : `D:\AIGATOS\demo\temp`.

## 4. Enregistrer

1. Faire un test de 20 secondes et contrôler texte, curseur et cadrage.
2. Suivre exactement `AIGATOS_Demo_Jury_Script_FR.md` ou `AIGATOS_Agentic_Workflow_Narration_FR.md`.
3. Sur Agent Interaction, utiliser Replay, Pause et les étapes locales. Ne jamais utiliser Approve/Reject.
4. À la fin, arrêter l'enregistrement avant d'afficher une autre application.

## 5. Finaliser

1. Remuxer vers le fichier MP4 demandé dans `D:\AIGATOS\demo`.
2. Regarder la vidéo intégralement.
3. Vérifier les invariants avant/après et l'absence de secret.
4. Calculer le hash : `Get-FileHash -Algorithm SHA256 -LiteralPath '<MP4>'`.
5. Inspecter les propriétés média avec OBS ou `ffprobe` si FFmpeg devient disponible.
6. Arrêter FastAPI, Celery et Vite démarrés pour la capture.

