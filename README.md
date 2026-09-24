# AIGATOS — phases 1 et 2

API FastAPI pour les véhicules, ECU, packages logiciels et campagnes OTA. Les campagnes restent en statut `draft`. Aucune route de déploiement ou action critique n'est présente.

## Prérequis

Windows 11, PowerShell, Python 3.11+, Docker Desktop en mode conteneurs Linux. Le code, l'environnement Python, les caches, les données PostgreSQL et les futurs volumes sont sous `D:\AIGATOS`. Les ports locaux sont 55432 pour PostgreSQL et 6379 pour Redis. Les identifiants inclus sont réservés au développement local.

Docker Desktop conserve son disque d'images et de conteneurs sur C: avec l'autorisation de l'utilisateur. Les bind mounts du projet restent sur D:. Contrôler l'espace libre de C: avant et après chaque téléchargement d'image ; arrêter sous 8 Go.

## Installation Python

Chaque bloc commence à `D:\AIGATOS` et vérifie ce répertoire avant les commandes du projet.

```powershell
Set-Location -LiteralPath 'D:\AIGATOS'
if ((Get-Location).Path -ne 'D:\AIGATOS') { throw 'Répertoire incorrect' }
$env:TMP = 'D:\AIGATOS\data'
$env:TEMP = 'D:\AIGATOS\data'
$env:PIP_CACHE_DIR = 'D:\AIGATOS\data\pip-cache'
$env:PYTHONPYCACHEPREFIX = 'D:\AIGATOS\data\pycache'
$env:PYTHONPATH = 'D:\AIGATOS\backend'
if ((Get-Location).Path -ne 'D:\AIGATOS') { throw 'Répertoire incorrect' }
if (-not (Test-Path -LiteralPath 'D:\AIGATOS\.venv')) { py -m venv 'D:\AIGATOS\.venv' }
if ((Get-Location).Path -ne 'D:\AIGATOS') { throw 'Répertoire incorrect' }
& 'D:\AIGATOS\.venv\Scripts\python.exe' -m pip install -e 'D:\AIGATOS\backend[test]'
```

## PostgreSQL et migration

Cette commande réutilise l'image déjà présente et écrit les données de PostgreSQL dans `D:\AIGATOS\docker-data\postgres`. Le bind mount Redis pointe vers `D:\AIGATOS\docker-data\redis` ; `docker-data\minio` est réservé.

```powershell
Set-Location -LiteralPath 'D:\AIGATOS'
if ((Get-Location).Path -ne 'D:\AIGATOS') { throw 'Répertoire incorrect' }
docker compose -p aigatos -f '.\infrastructure\compose.yaml' config --quiet
if ((Get-Location).Path -ne 'D:\AIGATOS') { throw 'Répertoire incorrect' }
docker compose -p aigatos -f '.\infrastructure\compose.yaml' up -d --wait --pull never postgres
if ((Get-Location).Path -ne 'D:\AIGATOS') { throw 'Répertoire incorrect' }
$env:PYTHONPYCACHEPREFIX = 'D:\AIGATOS\data\pycache'
$env:PYTHONPATH = 'D:\AIGATOS\backend'
& 'D:\AIGATOS\.venv\Scripts\alembic.exe' -c 'D:\AIGATOS\backend\alembic.ini' upgrade head
```

La commande suivante démarre aussi Redis une fois son image présente :

```powershell
Set-Location -LiteralPath 'D:\AIGATOS'
if ((Get-Location).Path -ne 'D:\AIGATOS') { throw 'Répertoire incorrect' }
docker compose -p aigatos -f '.\infrastructure\compose.yaml' up -d --wait
```

## Tests et API

```powershell
Set-Location -LiteralPath 'D:\AIGATOS'
if ((Get-Location).Path -ne 'D:\AIGATOS') { throw 'Répertoire incorrect' }
$env:TMP = 'D:\AIGATOS\data'
$env:TEMP = 'D:\AIGATOS\data'
$env:PYTHONPYCACHEPREFIX = 'D:\AIGATOS\data\pycache'
$env:PYTHONPATH = 'D:\AIGATOS\backend'
& 'D:\AIGATOS\.venv\Scripts\python.exe' -m pytest -q 'D:\AIGATOS\backend\tests'
if ((Get-Location).Path -ne 'D:\AIGATOS') { throw 'Répertoire incorrect' }
& 'D:\AIGATOS\.venv\Scripts\alembic.exe' -c 'D:\AIGATOS\backend\alembic.ini' check
if ((Get-Location).Path -ne 'D:\AIGATOS') { throw 'Répertoire incorrect' }
& 'D:\AIGATOS\.venv\Scripts\uvicorn.exe' app.main:app --host 127.0.0.1 --port 8000
```

Documentation interactive : http://127.0.0.1:8000/docs. Santé : http://127.0.0.1:8000/api/v1/health.

Les ressources `/api/v1/vehicles`, `/api/v1/ecus`, `/api/v1/software-packages` et `/api/v1/campaigns` exposent `POST`, `GET` (liste et détail), `PATCH` et `DELETE`. Les listes acceptent `offset` et `limit` (1 à 100). La suppression d'une ressource utilisée renvoie 409. Les références absentes renvoient 404. La validation des champs renvoie 422.

La phase 1 couvre uniquement l'API CRUD et l'infrastructure. Le frontend, le ML, les agents et les workflows de déploiement restent hors de la phase 2.


## Phase 2 — simulation OTA (sans déploiement réel)

La simulation crée exactement 100 véhicules et un ECU BatteryManager par véhicule. La seed rend reproductibles l'affectation des scénarios et les résultats. Les étapes Canary portent sur 10, 30 puis 60 véhicules. Chaque étape s'arrête en attente d'évaluation ; une approbation documentée et une commande **advance** séparée sont nécessaires pour la suivante. Un rejet bloque la progression. La campagne reste en statut `draft`.

Les événements sont validés par Pydantic puis enregistrés dans PostgreSQL. La machine à états normale suit `IDLE → ELIGIBILITY_CHECK → DOWNLOADING → VERIFYING_PACKAGE → INSTALLING → MEMORY_VALIDATION → REBOOTING → HEALTH_CHECK → SUCCESS`. Un échec suit `FAILED → ROLLBACK → RESTORED`. `rollback_count` compte seulement les rollbacks nécessaires après le début de l'installation ; les échecs précoces produisent un événement de restauration simulée sans modification logicielle.

Dans la démonstration, le package est **BatteryManager 2.4.0**. Les ECU `HW_REV_B` ont une probabilité configurable (0,9 par défaut) de produire `MEMORY_LAYOUT_MISMATCH` à `MEMORY_VALIDATION`. Les autres révisions réussissent majoritairement. Aucun LLM ou agent n'intervient.

### Services et espace disque

Docker Desktop peut conserver son disque virtuel sur C: avec l'autorisation donnée pour cette phase. Les bind mounts PostgreSQL et Redis, les logs Celery et les fichiers du projet restent sur D:. Avant et après chaque téléchargement Docker, contrôler C: et arrêter si moins de 8 Go restent :

```powershell
Set-Location -LiteralPath 'D:\AIGATOS'
if ((Get-Location).Path -ne 'D:\AIGATOS') { throw 'Répertoire incorrect' }
$before = (Get-PSDrive -Name C).Free
if ($before -lt 8GB) { throw 'Moins de 8 Go libres sur C:' }
docker compose -p aigatos -f '.\infrastructure\compose.yaml' pull redis
if ((Get-Location).Path -ne 'D:\AIGATOS') { throw 'Répertoire incorrect' }
$after = (Get-PSDrive -Name C).Free
if ($after -lt 8GB) { throw 'Moins de 8 Go libres sur C:' }
docker compose -p aigatos -f '.\infrastructure\compose.yaml' up -d --wait --pull never postgres redis
if ((Get-Location).Path -ne 'D:\AIGATOS') { throw 'Répertoire incorrect' }
docker compose -p aigatos -f '.\infrastructure\compose.yaml' exec -T redis redis-cli PING
```

Installer la dépendance Celery dans l'environnement situé sur D: :

```powershell
Set-Location -LiteralPath 'D:\AIGATOS'
if ((Get-Location).Path -ne 'D:\AIGATOS') { throw 'Répertoire incorrect' }
$env:TMP = 'D:\AIGATOS\data'
$env:TEMP = 'D:\AIGATOS\data'
$env:PIP_CACHE_DIR = 'D:\AIGATOS\data\pip-cache'
$env:PYTHONPYCACHEPREFIX = 'D:\AIGATOS\data\pycache'
$env:PYTHONPATH = 'D:\AIGATOS\backend'
& 'D:\AIGATOS\.venv\Scripts\python.exe' -m pip install -e 'D:\AIGATOS\backend[test]'
if ((Get-Location).Path -ne 'D:\AIGATOS') { throw 'Répertoire incorrect' }
& 'D:\AIGATOS\.venv\Scripts\alembic.exe' -c 'D:\AIGATOS\backend\alembic.ini' upgrade head
```

Dans un terminal PowerShell dédié, lancer le worker (journal unique sur D:) :

```powershell
Set-Location -LiteralPath 'D:\AIGATOS'
if ((Get-Location).Path -ne 'D:\AIGATOS') { throw 'Répertoire incorrect' }
$env:TMP = 'D:\AIGATOS\data'
$env:TEMP = 'D:\AIGATOS\data'
$env:PYTHONPYCACHEPREFIX = 'D:\AIGATOS\data\pycache'
$env:PYTHONPATH = 'D:\AIGATOS\backend'
$log = 'D:\AIGATOS\logs\celery-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.log'
& 'D:\AIGATOS\.venv\Scripts\celery.exe' -A app.celery_app:celery_app worker --pool=solo --concurrency=1 --loglevel=INFO --logfile=$log
```

### Démonstration contrôlée

Exécuter chaque commande ci-dessous séparément depuis `D:\AIGATOS`. Remplacer `<RUN_ID>` par l'identifiant retourné par `start`. Examiner `status` avant chaque évaluation. `evaluate` enregistre la décision de l'évaluateur ; elle **ne** lance pas l'étape suivante. `advance` est un acte manuel distinct. Omettre `--approve` pour rejeter.

```powershell
Set-Location -LiteralPath 'D:\AIGATOS'
if ((Get-Location).Path -ne 'D:\AIGATOS') { throw 'Répertoire incorrect' }
$env:PYTHONPATH = 'D:\AIGATOS\backend'
$env:PYTHONPYCACHEPREFIX = 'D:\AIGATOS\data\pycache'
& 'D:\AIGATOS\.venv\Scripts\python.exe' 'D:\AIGATOS\simulator\demo.py' start --seed 42 --probability 0.9
```

```powershell
Set-Location -LiteralPath 'D:\AIGATOS'
if ((Get-Location).Path -ne 'D:\AIGATOS') { throw 'Répertoire incorrect' }
$env:PYTHONPATH = 'D:\AIGATOS\backend'
$env:PYTHONPYCACHEPREFIX = 'D:\AIGATOS\data\pycache'
& 'D:\AIGATOS\.venv\Scripts\python.exe' 'D:\AIGATOS\simulator\demo.py' status '<RUN_ID>'
```

Après **validation humaine** de l'étape 1 :

```powershell
Set-Location -LiteralPath 'D:\AIGATOS'
if ((Get-Location).Path -ne 'D:\AIGATOS') { throw 'Répertoire incorrect' }
$env:PYTHONPATH = 'D:\AIGATOS\backend'
$env:PYTHONPYCACHEPREFIX = 'D:\AIGATOS\data\pycache'
& 'D:\AIGATOS\.venv\Scripts\python.exe' 'D:\AIGATOS\simulator\demo.py' evaluate '<RUN_ID>' 1 --approve --reviewer '<NOM>' --note 'Résultats examinés et étape 1 approuvée'
if ((Get-Location).Path -ne 'D:\AIGATOS') { throw 'Répertoire incorrect' }
& 'D:\AIGATOS\.venv\Scripts\python.exe' 'D:\AIGATOS\simulator\demo.py' advance '<RUN_ID>'
```

Répéter `status`, `evaluate '<RUN_ID>' 2 --approve --reviewer '<NOM>' --note '...'`, puis `advance '<RUN_ID>'` pour l'étape 3. Après examen de l'étape 3, utiliser `evaluate '<RUN_ID>' 3 --approve --reviewer '<NOM>' --note '...'`. Consulter le bilan :

```powershell
Set-Location -LiteralPath 'D:\AIGATOS'
if ((Get-Location).Path -ne 'D:\AIGATOS') { throw 'Répertoire incorrect' }
$env:PYTHONPATH = 'D:\AIGATOS\backend'
$env:PYTHONPYCACHEPREFIX = 'D:\AIGATOS\data\pycache'
& 'D:\AIGATOS\.venv\Scripts\python.exe' 'D:\AIGATOS\simulator\demo.py' report '<RUN_ID>'
if ((Get-Location).Path -ne 'D:\AIGATOS') { throw 'Répertoire incorrect' }
& 'D:\AIGATOS\.venv\Scripts\python.exe' -m pytest -q 'D:\AIGATOS\backend\tests'
```

API : `POST /api/v1/simulations`, `GET /api/v1/simulations/{id}`, `POST /api/v1/simulations/{id}/stages/{n}/evaluate`, `POST /api/v1/simulations/{id}/advance` et `GET /api/v1/simulations/{id}/vehicles/{vehicle_id}/timeline`.

## Phase 3A — modèles de référence et Monitoring Agent

La Phase 3A est strictement **Advisory**. Elle ne contient aucune route de déploiement, ne change jamais automatiquement d'étape Canary et n'appelle aucun LLM. La seed documentée est `20260922`.

Les entraînements lisent exclusivement les splits validés sous `D:\AIGATOS\datasets\processed`. Les trois datasets restent séparés. Les modèles retenus sont écrits sous `D:\AIGATOS\models`, et les métriques, matrices de confusion et courbes ROC/PR sous `D:\AIGATOS\reports\ml`.

```powershell
Set-Location -LiteralPath 'D:\AIGATOS'
$env:PYTHONPATH = 'D:\AIGATOS\backend;D:\AIGATOS'
$env:TEMP = 'D:\AIGATOS\data\tmp'
$env:TMP = 'D:\AIGATOS\data\tmp'
$env:MPLCONFIGDIR = 'D:\AIGATOS\data\matplotlib'
& 'D:\AIGATOS\.venv\Scripts\python.exe' -m pip install -e 'D:\AIGATOS\backend[test,ml]'
& 'D:\AIGATOS\.venv\Scripts\python.exe' -m ml.phase3a
```

La sélection utilise uniquement la validation et privilégie PR-AUC puis F1, sous un seuil opérationnel visant au maximum 5 % de faux positifs. Le test n'est lu qu'une fois pour le candidat retenu. Accuracy seule n'est jamais un critère de sélection.

- Engine Health : Dummy, régression logistique, Random Forest et HistGradientBoosting.
- Network Slicing : mêmes modèles, sans identifiants ni proxys post-échec.
- BETH : aucune classification supervisée de `evil`. `sus` sert uniquement à évaluer une baseline statistique et Isolation Forest, ajustés sans labels de test.

Les limites sont importantes : Network Slicing est proche du hasard sur le test ; BETH présente un distribution shift extrême (`evil` absent du train et de la validation, dominant dans le test) ; Engine Health ne contient ni identifiant véhicule ni temps exploitable. Ces modèles enrichissent une analyse, mais ne prouvent aucune cause OTA et ne peuvent autoriser aucune action.

Le Monitoring Agent (`app.services.monitoring_agent`) calcule les taux par campagne et étape, analyse matériel/erreurs/étapes, applique des seuils configurables, crée un incident idempotent et relie les événements PostgreSQL de preuve. Un éventuel `anomaly_score` est un attribut consultatif de l'incident ; il ne modifie jamais campagne, simulation ou étape.

La Phase 3A s'arrête ici. Log Analysis Agent, Correlation Agent, RCA Agent, Decision Agent et toute intégration LLM restent hors périmètre.

## Phase 3B — workflow agentique déterministe

La Phase 3B utilise une machine à états Python explicite persistée dans PostgreSQL et exécutée par Celery : `MONITORING → LOG_ANALYSIS → CORRELATION → RCA → DECISION → WAITING_FOR_HUMAN_APPROVAL`. L'état est sauvegardé après chaque agent et l'historique structuré contient les entrées résumées, sorties, durées et erreurs. Les transitions sont idempotentes, les reprises sont bornées par un nombre maximal de retries, un timeout par agent et une garde anti-boucle.

Le workflow lit exclusivement les preuves PostgreSQL reliées à l'incident. Chaque observation et hypothèse référence des `evidence_id` validés. Les corrélations incluent effectifs, taux d'échec, risk ratio et intervalle de confiance à 95 %, avec la mention explicite qu'une corrélation ne prouve pas une causalité. Aucun raisonnement interne libre n'est stocké : seuls les résultats structurés, règles déclenchées, composantes de score et références de preuve sont conservés.

Le Decision Agent ne possède aucun exécuteur OTA. Il propose seulement `PAUSE_CAMPAIGN`, `EXCLUDE_INCOMPATIBLE_VEHICLES`, `ASSIGN_CORRECTIVE_PACKAGE` ou `REQUEST_ADDITIONAL_INVESTIGATION`, toutes avec `requires_human_approval=true` et `executed=false`. Approve/Reject exige un utilisateur, un timestamp avec fuseau et un commentaire ; une soumission répétée à l'identique est idempotente et ne lance aucune action.

Endpoints :

- `POST /incidents/{id}/investigations`
- `GET /workflows/{id}`
- `GET /workflows/{id}/history`
- `GET /incidents/{id}/evidence`
- `GET /incidents/{id}/hypotheses`
- `POST /workflows/{id}/retry`
- `POST /workflows/{id}/approve`
- `POST /workflows/{id}/reject`

Exemple de décision humaine (enregistrement uniquement, aucune action OTA) :

```json
{
  "user": "safety-reviewer",
  "timestamp": "2026-09-23T12:00:00+02:00",
  "comment": "Décision documentée après examen des preuves."
}
```

La Phase 3B n'importe ni LangGraph, ni SDK LLM, ni code de chargement des modèles Kaggle. `anomaly_score` doit rester `null`. Elle ne modifie jamais la campagne ou les étapes Canary et s'arrête avant toute intégration NVIDIA/LLM ou action corrective.

## Phase 4A — explication générative contrôlée

La Phase 4A explique uniquement les résultats structurés du workflow déterministe. Elle ne recalcule jamais `global_confidence`, ne crée aucune preuve, ne modifie aucune recommandation et ne possède aucun exécuteur OTA. La cause est toujours présentée comme probable. Le prompt courant est versionné `phase4a-v1`.

Le registre contient quatre adaptateurs paresseux : `nvidia`, `deepseek`, `google` et `kimi`. Seul le fournisseur nommé par `LLM_PROVIDER` est initialisé ; aucun fallback inter-fournisseur n'est autorisé. Le seul fallback automatique est le résumé déterministe local. Les paramètres sont chargés depuis le `.env` local ignoré par Git ; `.env.example` ne contient que des valeurs vides.

Variables principales : `LLM_ENABLED`, `LLM_PROVIDER`, `LLM_MODEL`, `NVIDIA_API_KEY`, `NVIDIA_BASE_URL`, `NVIDIA_MODEL`, `LLM_TEMPERATURE`, `LLM_TIMEOUT_SECONDS` et `LLM_MAX_RETRIES`. Les variantes `DEEPSEEK_*`, `GOOGLE_*` et `KIMI_*` restent configurables mais ne sont jamais initialisées lorsque NVIDIA est sélectionné. La température est bornée à 0,2 et les retries à deux maximum.

Endpoints :

- `POST /incidents/{id}/explanations`
- `GET /incidents/{id}/explanations/latest`
- `GET /explanations/{id}/audit`

La sortie JSON validée contient `incident_summary`, `probable_root_cause`, `confidence_interpretation`, `evidence_citations`, `alternative_hypotheses`, `recommended_next_steps`, `limitations`, `generated_at`, `model_name` et `prompt_version`. Chaque citation est vérifiée dans PostgreSQL et chaque recommandation doit déjà exister dans la liste déterministe autorisée. Les instructions éventuellement présentes dans les événements sont traitées comme données non fiables et retirées du contexte.

La démonstration du 23 septembre 2026 a tenté un seul appel `nvidia / z-ai/glm-5.3`. Le fournisseur a dépassé le timeout configuré ; le résultat stocké est donc `FALLBACK_TIMEOUT`, avec un résumé déterministe validé et le score inchangé `0.620644`. Aucune approbation ou action corrective n'a été exécutée.

## Phase 4B — génération et archivage du rapport

La Phase 4B génère un rapport HTML et PDF exclusivement depuis le workflow, l'incident et l'explication Phase 4A déjà validés. Elle n'initialise aucun provider LLM. Avant génération, elle exige `WAITING_FOR_HUMAN_APPROVAL`, une approbation `PENDING`, une campagne `draft`, Canary 3 `pending`, `anomaly_score=null`, le score déterministe `0.620644` et zéro recommandation exécutée.

Le template courant est `incident-report-v1.1`. Les valeurs injectées dans le HTML sont échappées. Le PDF inclut un avertissement indiquant que la corrélation ne prouve pas la causalité, une zone de décision humaine entièrement vide et les preuves PostgreSQL validées. Les artefacts sont enregistrés sous `D:\AIGATOS\reports\incidents` et leur chemin, version, template, date UTC et SHA-256 sont persistés dans `incident_reports`.

Endpoints :

- `POST /incidents/{id}/reports` avec `workflow_id` et `explanation_id` ;
- `GET /reports/{id}/pdf`.

Une entrée possédant le même hash d'entrée est renvoyée depuis le cache sans régénération. Une modification du template ou des données validées crée une version explicitement numérotée. Le PDF final de la démonstration est la version 2, produite après contrôle visuel des quatre pages.

## Phase 5 — interface Web AIGATOS

Le frontend React/TypeScript est situé dans `D:\AIGATOS\frontend`. Il utilise Material UI, React Router, TanStack Query et Recharts. Toutes les données proviennent de FastAPI : le navigateur n'accède jamais directement à PostgreSQL ou Redis. La projection `/api/v1/ui/*` est strictement en lecture seule et CORS n'autorise que `http://127.0.0.1:5173` et `http://localhost:5173`.

L'interface couvre le tableau de bord, les campagnes et leur progression Canary, le parc de véhicules, l'incident Phase 3, le workflow agentique, les recommandations, la validation humaine, les rapports et l'explication contrôlée. La région n'existant pas dans le schéma actuel, elle apparaît comme « Non renseignée ». Le mode démonstration ouvre un dialogue de confirmation mais désactive toujours l'envoi ; aucun appel aux endpoints `approve`, `reject`, `advance` ou de génération LLM n'est effectué.

### Démarrage local sous PowerShell

PostgreSQL et Redis :

```powershell
Set-Location -LiteralPath 'D:\AIGATOS'
docker compose -f 'D:\AIGATOS\infrastructure\compose.yaml' up -d postgres redis
```

Backend FastAPI :

```powershell
Set-Location -LiteralPath 'D:\AIGATOS'
$env:PYTHONPATH = 'D:\AIGATOS\backend'
$env:PYTHONPYCACHEPREFIX = 'D:\AIGATOS\data\pycache'
& 'D:\AIGATOS\.venv\Scripts\python.exe' -m uvicorn app.main:app --app-dir 'D:\AIGATOS\backend' --host 127.0.0.1 --port 8000
```

Worker Celery, dans un deuxième terminal :

```powershell
Set-Location -LiteralPath 'D:\AIGATOS'
$env:PYTHONPATH = 'D:\AIGATOS\backend'
$env:PYTHONPYCACHEPREFIX = 'D:\AIGATOS\data\pycache'
& 'D:\AIGATOS\.venv\Scripts\python.exe' -m celery -A app.celery_app:celery_app worker --pool=solo --loglevel=INFO
```

Frontend, dans un troisième terminal :

```powershell
Set-Location -LiteralPath 'D:\AIGATOS\frontend'
npm.cmd install
npm.cmd run dev -- --host 127.0.0.1
```

Vérifications :

```powershell
Set-Location -LiteralPath 'D:\AIGATOS\frontend'
npm.cmd test
npm.cmd run build
Set-Location -LiteralPath 'D:\AIGATOS'
$env:PYTHONPATH = 'D:\AIGATOS\backend'
& 'D:\AIGATOS\.venv\Scripts\python.exe' -m pytest -q 'D:\AIGATOS\backend\tests'
& 'D:\AIGATOS\.venv\Scripts\python.exe' -m alembic -c 'D:\AIGATOS\backend\alembic.ini' check
```

La Phase 5 reste consultative : aucune approbation, action corrective, exécution OTA, progression vers Canary 3 ou relance LLM n'est disponible depuis le frontend.

### Replay des interactions agentiques

La route `/workflows/{workflow_id}/interaction` présente une relecture animée et strictement locale du workflow persistant. Elle conserve l'ordre `Monitoring → Log Analysis → Correlation → RCA → Decision → Human Approval`, montre les entrées et sorties structurées, les champs transférés, l'état partagé et la traçabilité des preuves. Les commandes Replay, Pause, Précédent, Suivant, Recommencer et vitesse `0.5× / 1× / 2×` ne déclenchent aucune écriture : seules les API FastAPI en lecture (`GET`) sont utilisées.

Le niveau affiché est volontairement limité à **M4 — Advanced Simulation**. L'écran rappelle qu'il ne s'agit ni d'un déploiement automobile réel, ni d'un système certifié ISO, et qu'aucune maturité M5 n'est revendiquée.

Pour le workflow de démonstration :

```text
http://127.0.0.1:5173/workflows/cde0930e-b80a-447f-8ccc-92c6d97b11ba/interaction
```

### Démonstrations vidéo

Les scripts narratifs, la checklist de validation, la narration du Replay et la procédure OBS sont conservés dans `D:\AIGATOS\demo`. Le script `record-aigatos.mjs` automatise uniquement la navigation de lecture ; il bloque toute requête autre que `GET`, `HEAD` ou `OPTIONS`. Il enregistre d'abord un WebM temporaire sous `demo\temp`. La conversion MP4 nécessite un FFmpeg local et doit être réalisée sans installer d'outil sur `C:`.

Préparation optionnelle des outils de capture sur `D:` :

```powershell
Set-Location -LiteralPath 'D:\AIGATOS'
$env:PLAYWRIGHT_BROWSERS_PATH = 'D:\AIGATOS\demo\temp\ms-playwright'
npm.cmd install --prefix 'D:\AIGATOS\demo\temp\capture-tools' playwright
& 'D:\AIGATOS\demo\temp\capture-tools\node_modules\.bin\playwright.cmd' install chromium
```

Capture, après démarrage du backend et du frontend :

```powershell
Set-Location -LiteralPath 'D:\AIGATOS'
$env:PLAYWRIGHT_BROWSERS_PATH = 'D:\AIGATOS\demo\temp\ms-playwright'
node 'D:\AIGATOS\demo\record-aigatos.mjs' jury
node 'D:\AIGATOS\demo\record-aigatos.mjs' workflow
```

La procédure complète de narration, capture OBS, conversion en MP4, calcul SHA-256 et contrôles d'invariants figure dans `demo\AIGATOS_OBS_Recording_Procedure_FR.md`. Aucune vidéo ne doit être déclarée produite tant que le fichier MP4 final n'existe pas et n'a pas été vérifié.

## Mode Simulation Live

Le mode `live_simulation` transforme l'interface en laboratoire interactif tout en restant strictement simulé. Il crée une campagne, une flotte virtuelle et un historique isolés par `session_id`. Les données historiques ne sont jamais réécrites. La navigation Campagnes et Véhicules propose les vues Historique, Live et Toutes.

Configuration locale :

```powershell
$env:AIGATOS_OPERATION_MODE = 'live_simulation'
```

La page `http://127.0.0.1:5173/live-simulation` fournit un assistant en quatre étapes : campagne, flotte, injections et confirmation. Charger un preset ne crée rien ; l'opérateur doit explicitement créer la session, lancer la simulation, puis lancer l'investigation. Le preset jury utilise 30 véhicules et produit de façon déterministe 24 succès, 6 échecs et 3 rollbacks.

Endpoints :

- `GET /frontend/capabilities`
- `POST /live-simulations`
- `POST /live-simulations/{session_id}/start`
- `GET /live-simulations/{session_id}`
- `GET /live-simulations/{session_id}/events`
- `POST /live-simulations/{session_id}/investigation`
- `GET /live-simulations/{session_id}/workflow`
- `POST /live-simulations/{session_id}/decision`
- `GET /agent-maturity`

Toutes les écritures exigent un header `Idempotency-Key`. Chaque événement, incident et audit porte `source=LIVE_SIMULATION`, `environment=SIMULATED` et le `session_id`. Le workflow déterministe conserve l'ordre Monitoring, Log Analysis, Correlation, RCA et Decision, puis s'arrête à `WAITING_FOR_HUMAN_APPROVAL`.

La page `/agent-maturity` calcule les niveaux M0 à M4 depuis les preuves persistées. M5 est explicitement indisponible : aucune certification, autonomie automobile réelle ou exécution OTA n'est revendiquée. Une décision humaine Live peut uniquement être consignée dans la simulation ; elle renvoie toujours `executed=false` et ne crée aucune étape Canary 3.

Garde-fous permanents :

- `can_execute_real_ota=false` dans les capacités ;
- aucune route Live ne lance de LLM, de modèle Kaggle ou d'entraînement ;
- aucune progression automatique de campagne ou Canary ;
- toutes les recommandations restent consultatives et `PROPOSED` ;
- « Nouvelle session » réinitialise l'interface sans supprimer les sessions précédentes ;
- aucune clé API ou variable secrète n'est envoyée au frontend.

La démonstration jury reproductible, sans approbation, est disponible ici :

```powershell
Set-Location -LiteralPath 'D:\AIGATOS'
& 'D:\AIGATOS\.venv\Scripts\python.exe' 'D:\AIGATOS\demo\run_live_jury_demo.py'
```

Pour démarrer FastAPI dans ce mode :

```powershell
Set-Location -LiteralPath 'D:\AIGATOS'
$env:PYTHONPATH = 'D:\AIGATOS\backend'
$env:PYTHONPYCACHEPREFIX = 'D:\AIGATOS\data\pycache'
$env:AIGATOS_OPERATION_MODE = 'live_simulation'
& 'D:\AIGATOS\.venv\Scripts\python.exe' -m uvicorn app.main:app --app-dir 'D:\AIGATOS\backend' --host 127.0.0.1 --port 8000
```
#   A I G A T O S -  
 