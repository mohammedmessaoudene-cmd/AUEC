# Contrôles négatifs officiels EB-2026-08-02

Chaque mutation est appliquée à une copie jetable distincte, avec capacités et
préconditions maintenues. Le SUT BUILD-21 probatoire reste immuable.

| Mutation | Scénario | Résultat muté |
|---|---|---:|
| remettre `aiew.execute_manifest` en première position | `http-header-validation` | 12 S / 1 F |
| désactiver le trim OWS | `http-header-validation` | 12 S / 1 F |
| désactiver InputRequiredResult | `input-required-result-basic-elicitation` | 0 S / 1 F |
| casser le runtime d'abonnement tout en l'annonçant | `server-stateless` | 26 S / 2 F / 2 W |

Les quatre runners retournent non-zéro et enregistrent des `FAILURE`.
Résultat causal : **4/4 PASS**.
