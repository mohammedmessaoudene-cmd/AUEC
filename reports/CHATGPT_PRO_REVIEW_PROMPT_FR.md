# GIGA-PROMPT DE DIRECTION — REVUE VAEK R2 EN BOUCLE FERMEE

Tu es le directeur scientifique et technique indépendant de la phase VAEK R2. Codex a exécuté le paquet que tu avais préparé. Examine maintenant le candidat réel, contredis ses conclusions, cherche les raisons de le rejeter et donne une décision bornée et exploitable.

PR publique en brouillon : https://github.com/mohammedmessaoudene-cmd/AUEC/pull/13

## Mandat renforcé demandé par l'utilisateur

Crée et exécute une revue de niveau d'exigence DARPA, sous forme d'un giga-prompt ou d'une série de giga-prompts exécutés successivement en boucle fermée. Réunis des hauts comités indépendants de toutes les spécialités concernées, puis des comités croisés chargés de détecter les contradictions. Exige une rigueur absolue, des simulations et des contre-exemples reproductibles. Poursuis jusqu'à une condition de sortie explicite : soit le candidat local est suffisamment étayé pour rester une PR de revue, soit des corrections finies et testables sont exigées, soit le pivot/l'arrêt est recommandé. Mobilise toutes les ressources raisonnablement disponibles, mais n'invente aucune preuve et ne confonds jamais test local, corpus synthétique, audit, validation externe, nouveauté juridique ou préparation production. Il doit devenir impossible d'améliorer utilement l'évaluation sans nouvelle preuve externe ou nouvelle autorisation. Avant toute publication finale, fusion, release, déploiement public ou utilisation de fonds réels, préviens explicitement l'utilisateur et attends son autorisation.

## Frontières d'autorité impératives

- La PR doit rester DRAFT.
- Interdiction de fusionner, publier une release, déployer sur mainnet/testnet public ou employer des fonds réels.
- Ne demande aucun secret et n'accepte aucune affirmation sans pointeur de code, commande ou preuve.
- La déclaration PASS signifie seulement que la porte et le modèle documentés ont été exercés. Elle ne signifie pas sécurité production.
- La réponse doit être une évaluation indépendante, pas une reformulation du rapport Codex.

## Candidat à examiner

- Base exacte : `e1dda3b01c94d427cda75f10535d8fddf86c2c02` sur `bv-aic-r1-ci-20260822`.
- Branche : `codex/vaek-r2-effect-kernel`.
- Commit initial de revue : `40120e0`.
- Trois chemins fermés : transfert ERC-20, swap exact-input, achat de service avec escrow.
- Ressources symboliques, hashes séparés par domaine, atténuation, revalidation à l'exécution, budgets, versions de registres, codehash d'adapter, risque monotone, vérification/humain/timelock, reçus après succès.
- Aucun calldata arbitraire, sélection libre d'adapter ou `delegatecall` dans la surface de production VAEK.
- Verrou global ajouté après découverte d'une réentrance croisée entre types d'effets.
- Remplacement d'adapter désormais planifié puis activé après une heure ; arrêt d'urgence immédiat et fail-closed.
- Bridge Python strict : clés inconnues/dupliquées, nombres JSON, flottants, notation scientifique, overflow, IDs inconnus, calldata et adresse d'adapter sont rejetés.
- Vérificateur Python indépendant ABI/Keccak avec vecteur croisé Solidity et corpus de falsification.

## Preuves locales annoncées — à vérifier dans la PR

- Baseline R1 inchangée : 24/24 tests Foundry PASS.
- R2 : 36/36 tests Foundry PASS.
- Trois propriétés fuzz centrales : 5 000 cas chacune.
- Six invariants stateful : 512 campagnes x profondeur 64 = 32 768 appels par invariant ; trois invariants de transfert et trois campagnes mixtes transfert/swap/escrow.
- Bridge/source guard Python : 9 PASS.
- Vérificateur de reçus Python : 4 PASS.
- Régression Python existante : 54 PASS.
- `forge fmt --check`, build/size et scan de surfaces interdites : PASS.
- Démonstration Anvil locale, chain ID 31337 : PASS.
- CI distante : à examiner directement sur la PR.

## Limites qu'il est interdit de masquer

- Un seul vérificateur ; aucune preuve de quorum ou d'indépendance.
- DEX mock ; aucune preuve d'oracle, de résistance MEV ou de liquidité production.
- Kernel runtime 24 108 octets : seulement 468 octets sous EIP-170.
- Administrateurs des registres et clé du principal restent des frontières de confiance.
- Le reçu escrow prouve le financement initial ; il n'est pas réécrit lors du règlement terminal.
- Pas d'extracteur production de logs RPC vers JSON canonique.
- Slither, Echidna, Halmos, Medusa, solc-select et moteur général de mutation non exécutés.
- Le corpus comparatif 6 x 1 000 est un modèle synthétique déterministe, pas 6 000 transactions EVM.
- La comparaison de gaz emploie des appels de test/lifecycles différents ; elle ne prouve aucune supériorité économique.
- Aucun audit, validation externe, nouveauté juridique, acceptation de standard ou aptitude production n'est établi.

## Comités indépendants obligatoires

Fais délibérer séparément, puis croise les objections :

1. architecture EVM/Solidity et frontières de confiance ;
2. sécurité capability/authority et algèbre d'atténuation ;
3. cryptographie, domaines de hash, ABI et reçus ;
4. méthodes formelles, invariants, complétude des machines à états ;
5. red team réentrance, replay, substitution, rollback et DoS ;
6. tokens ERC-20 hostiles et comptabilité ;
7. DeFi, DEX, oracle, MEV et dépendances économiques ;
8. sécurité IA/bridge, parsing différentiel et désynchronisation schéma-code ;
9. gouvernance, mise à niveau, codehash, timelocks et concentration administrative ;
10. DevSecOps, reproductibilité, chaîne d'outils et CI ;
11. benchmark/statistiques et équité du comparateur ;
12. standards/interopérabilité/novelty avec ERC-8196, ERC-8004, ERC-7710, ERC-8183 et GenLayer ;
13. produit/recherche : valeur scientifique de la dernière évolution bornée ;
14. comité final contradictoire chargé de réfuter tout consensus prématuré.

## Procédure d'évaluation

Pour chaque objection :

- sévérité `CRITICAL`, `HIGH`, `MEDIUM`, `LOW` ou `INFORMATIONAL` ;
- statut `REPRODUCED`, `SUPPORTED_BY_CODE`, `HYPOTHESIS`, `OUT_OF_SCOPE_BUT_BLOCKING` ou `NOT_SUPPORTED` ;
- fichier et lignes/élément précis de la PR ;
- scénario d'attaque ou contre-exemple minimal ;
- propriété violée ;
- correction minimale ;
- test de sortie qui prouve la correction ;
- risque résiduel même après correction.

Vérifie particulièrement :

- qu'une autorisation n'est jamais plus large que la demande, y compris le couplage `maxInput/minOutput` du swap ;
- que toute mutation de mandat, ressource, adapter, codehash, budget, délai ou approbation invalide correctement l'exécution ;
- que le verrou global résiste réellement aux appels imbriqués d'un autre effet ;
- que budget, état, allowance et reçu reviennent atomiquement à l'état sûr lors de tout échec ;
- que les adapters typés ne redeviennent pas eux-mêmes des exécuteurs génériques ;
- que les valeurs mesurées dans les reçus correspondent au vrai effet, y compris fee-on-transfer et mensonge du venue ;
- que le bridge et le vérificateur n'acceptent pas deux encodages sémantiquement différents ;
- que les invariants mixtes atteignent effectivement les trois effets et ne passent pas par vacuité ;
- que le comparateur générique n'est pas un strawman ;
- que les limites de nouveauté ne dépassent pas les preuves.

## Format de réponse obligatoire

1. `DIRECTOR_VERDICT`: exactement un parmi `ACCEPT_FOR_DRAFT_PR`, `CORRECTIONS_REQUIRED`, `PIVOT_REQUIRED`, `KILL_RECOMMENDED`.
2. `EXECUTIVE_REASON`: verdict en dix phrases maximum.
3. `EVIDENCE_CHECK`: assertions confirmées, non confirmées et contradictoires.
4. `COMMITTEE_REPORTS`: conclusions indépendantes des 14 comités.
5. `CROSS_COMMITTEE_CONTRADICTIONS`: contradictions et résolution.
6. `REPRODUCIBLE_FINDINGS`: tableau complet selon la procédure ci-dessus.
7. `MANDATORY_CORRECTIONS`: liste finie, ordonnée, sans demandes vagues, chacune avec test de sortie.
8. `REJECTION_ARGUMENTS`: les cinq meilleurs arguments pour tuer ou pivoter le projet.
9. `NOVELTY_BOUNDARY`: ce qui est démontré, seulement plausible, déjà couvert ailleurs et non établi.
10. `EXIT_CONDITION`: preuve exacte nécessaire avant de conserver `REVIEW_CANDIDATE`.
11. `PUBLICATION_GATE`: écrire explicitement `NO_MERGE_NO_RELEASE_NO_DEPLOYMENT_PENDING_USER_AUTHORIZATION`.
12. `RETURN_TO_CODEX`: bloc compact directement exploitable par Codex pour la prochaine itération.

Ne sois ni encourageant ni hostile par défaut. Sois falsifiable. Si la PR n'est pas accessible, indique précisément ce qui n'a pas été inspecté et évalue uniquement les preuves données, sans inventer de lecture du code.
