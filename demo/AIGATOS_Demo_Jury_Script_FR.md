# AIGATOS — Script de démonstration jury

Durée cible : 7 min 40 s. Format : 1920×1080, 30 fps. Aucune voix synthétique n'est incluse.

## 00:00–00:20 — Introduction

Écran titre :

- AIGATOS
- Plateforme Agentic AI de supervision OTA automobile
- Démonstration du prototype

Narration : « Cette démonstration présente AIGATOS, un prototype de supervision OTA automobile fondé sur des preuves persistées, une investigation multi-agent déterministe et une validation humaine obligatoire. »

## 00:20–01:00 — Tableau de bord

Afficher le tableau de bord et les indicateurs de flotte, de campagne, d'incident, de workflow et de santé des services.

Narration : « AIGATOS supervise des campagnes de mise à jour logicielle OTA. La plateforme centralise les événements, détecte les incidents et organise une investigation traçable avant toute décision humaine. Les données présentées proviennent d'une flotte simulée contrôlée. »

## 01:00–01:45 — Campagne Canary

Ouvrir la campagne BatteryManager 2.4.0. Montrer les trois étapes, les 30 véhicules de Canary 2, les 24 succès, 6 échecs et 3 rollbacks. Insister sur Canary 3 `pending`.

Narration : « La deuxième étape Canary atteint un taux d'échec de 20 %. AIGATOS bloque la progression et crée automatiquement un incident. La troisième étape ne démarre pas. »

## 01:45–02:30 — Véhicules et événements

Filtrer sur `HW_REV_B`, ouvrir un véhicule en échec et parcourir sa timeline jusqu'à `MEMORY_LAYOUT_MISMATCH` / `MEMORY_VALIDATION`.

Narration : « Chaque véhicule possède une chronologie détaillée. Les événements permettent d'identifier l'étape exacte et la signature de l'échec, sans modifier les données enregistrées. »

## 02:30–03:20 — Incident

Montrer 259 événements liés, 6 événements `FAILURE`, les erreurs normalisées, les evidence IDs et `anomaly_score` indisponible.

Narration : « L'incident conserve les preuves PostgreSQL utilisées par l'analyse. Aucun modèle Kaggle incompatible n'est appliqué aux événements OTA. »

## 03:20–04:30 — Workflow agentique

Ouvrir la vue Agent Interaction et utiliser Replay. Montrer Monitoring, Log Analysis, Correlation, RCA et Decision dans l'ordre, puis l'arrêt sur Human Approval.

Narration : « Le workflow coordonne cinq agents spécialisés. Tous ne sont pas des LLM. Les règles, statistiques et services Python assurent les calculs déterministes et la traçabilité. Le Replay restitue uniquement l'historique déjà enregistré. »

## 04:30–05:20 — Root Cause Analysis

Montrer `HW_REV_B : 3/3`, `HW_REV_A : 3/27`, le risk ratio `7.0`, l'IC 95 % `[2.455, 19.957]`, le score `0.620644` et ses cinq composantes.

Narration : « L'hypothèse principale indique une incompatibilité probable entre HW_REV_B et BatteryManager 2.4.0. Le système conserve un niveau de prudence : la corrélation ne prouve pas la causalité et la cohorte HW_REV_B reste limitée. »

## 05:20–05:55 — Recommandations

Afficher les quatre recommandations, chacune `PROPOSED` et `executed=false`, puis la page de validation en mode démonstration sans cliquer sur Approve ou Reject.

Narration : « AIGATOS propose des actions, mais ne les exécute jamais sans validation humaine. »

## 05:55–06:30 — Explication contrôlée

Montrer NVIDIA, `z-ai/glm-5.3`, `FALLBACK_TIMEOUT`, `DETERMINISTIC_FALLBACK` et le score inchangé.

Narration : « L'appel au modèle a dépassé le délai autorisé. Le fallback déterministe a maintenu le service sans modifier le score, les preuves ou les recommandations. Cette restitution n'est pas présentée comme une réponse produite par le LLM. »

## 06:30–07:10 — Rapport

Afficher la version 2, son SHA-256 et sa source. Ouvrir le PDF sans exposer de chemin local et parcourir ses quatre pages, dont la zone de validation humaine vide.

Narration : « La plateforme génère un rapport versionné et vérifiable. Il conserve les preuves, les limites de l'analyse et l'état de la validation humaine. »

## 07:10–07:40 — Conclusion

Retourner au dashboard. Afficher : 29 tests backend, 11 tests frontend, 40 tests réussis, zéro action OTA, Canary 3 `pending`.

Narration : « AIGATOS démontre une supervision OTA de bout en bout avec diagnostic multi-agent, preuves vérifiables et contrôle humain obligatoire. »

