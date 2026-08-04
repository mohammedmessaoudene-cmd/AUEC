# MCP officiel EB-2026-08-02

Les runners publiés ont été matérialisés depuis leurs lockfiles exacts avec
Node 24.18.0. `npm ci` a réussi pour les deux arbres et a rapporté zéro
vulnérabilité. Aucun runner, scénario ou résultat attendu n'a été modifié.

| Profil | Runner | Scénarios | SUCCESS | FAILURE | INFO |
|---|---:|---:|---:|---:|---:|
| active 2025-11-25 | 0.1.16 | 30 | 39 | 0 | 1 |
| active final 2026-07-28 | 0.2.0-alpha.10 | 20 | 22 | 0 | 1 |
| draft 2026-07-28 | 0.2.0-alpha.10 | 19 | 85 | 0 | 0 |

Tous les stderr SUT sont vides. La condition locale exacte est satisfaite :

```text
PASS_OFFICIAL_MCP_DRAFT_APPLICABLE
```

Comparaison BUILD-20/BUILD-21 : les 85 checks sont identiques ; seul
`sep-2243-server-accepts-whitespace-header-value` passe de FAILURE à SUCCESS.
Aucun autre check ne régresse.
