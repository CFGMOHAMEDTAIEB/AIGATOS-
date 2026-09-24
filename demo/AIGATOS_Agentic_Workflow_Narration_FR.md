# Narration française — Interaction et maturité des agents

Durée cible : 4 min 30 s. Ce texte est destiné à une narration humaine ; aucune voix synthétique n'est générée.

## 00:00–00:20 — Titre

« AIGATOS organise l'investigation d'un incident OTA autour de cinq agents spécialisés. Cette démonstration repose sur des données simulées et s'arrête obligatoirement avant toute décision opérationnelle. »

## 00:20–00:50 — Maturité

« L'échelle interne va de M0, concept, à M5, validation en production automobile. Les cinq agents sont au niveau M4 : ils sont implémentés, testés, intégrés, persistants et démontrés de bout en bout sur le simulateur. M4 n'est ni une certification officielle, ni un niveau ISO, ni une validation sur véhicule réel. Aucun agent n'est présenté comme M5. »

## 00:50–01:20 — Monitoring Agent

« Monitoring reçoit les événements de Canary 2. Il lit trente véhicules, observe vingt-quatre succès, six échecs et trois rollbacks. Le taux d'échec de vingt pour cent atteint le seuil configuré. L'agent transmet l'incident, les cohortes de succès et d'échec, ainsi que les identifiants des preuves enregistrées. »

## 01:20–01:50 — Log Analysis Agent

« Log Analysis ne raisonne pas librement sur les logs. Il applique des règles de normalisation, construit les timelines par véhicule et regroupe les séquences d'échec. Trois véhicules HW_REV_B partagent la signature MEMORY_LAYOUT_MISMATCH à l'étape MEMORY_VALIDATION. Trois autres échecs concernent la batterie, le réseau et le stockage. »

## 01:50–02:25 — Correlation Agent

« Correlation compare les cohortes en succès et en échec. Les trois véhicules HW_REV_B échouent, contre trois échecs sur vingt-sept véhicules HW_REV_A. Le risk ratio observé est sept, avec un intervalle de confiance à quatre-vingt-quinze pour cent de 2,455 à 19,957. Cette association statistique ne prouve pas une causalité. »

## 02:25–03:05 — RCA Agent

« RCA combine les règles métier, les corrélations et les preuves validées. Il classe plusieurs hypothèses et fait émerger une incompatibilité probable entre HW_REV_B et BatteryManager 2.4.0. Le score déterministe reste exactement 0,620644. Ses composantes sont visibles : association, support, cohérence de l'erreur, cohérence de l'étape et couverture des preuves. Aucun LLM ne calcule ce score ou ne choisit seul la cause racine. »

## 03:05–03:40 — Decision Agent

« Decision transforme l'hypothèse principale en quatre recommandations autorisées. Elles restent toutes proposées et non exécutées. L'agent vérifie les politiques de sécurité et prépare une demande humaine PENDING. Il ne possède aucun exécuteur OTA. »

## 03:40–04:10 — État partagé et contrôle humain

« L'état partagé est sauvegardé après chaque étape. Les preuves circulent par identifiant sans être copiées ni modifiées. Le workflow s'arrête exactement à WAITING_FOR_HUMAN_APPROVAL. Canary 3 reste pending et les contrôles de décision restent désactivés dans cette démonstration. »

## 04:10–04:30 — Conclusion

« Cinq agents terminés, zéro retry, aucune erreur, deux cent cinquante-neuf événements liés, zéro preuve invalide et zéro action exécutée. AIGATOS automatise l'investigation, pas la décision finale. »

