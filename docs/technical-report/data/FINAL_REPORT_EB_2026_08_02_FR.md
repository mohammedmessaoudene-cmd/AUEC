# AIEW EB-2026-08-02 — rapport final

## Verdict

```text
GO_OFFICIAL_MCP_DRAFT_APPLICABLE_EVIDENCE_CHECKPOINT

PASS_OFFICIAL_MCP_2025_11_25_ACTIVE
PASS_OFFICIAL_MCP_2026_07_28_ACTIVE
PASS_OFFICIAL_MCP_DRAFT_APPLICABLE
PASS_OFFICIAL_NEGATIVE_CONTROLS_4_OF_4
PASS_BUILD-20_BUILD-21_NO_REGRESSION

NO_GO_OFFICIAL_A2A_CONFORMANCE
NO_GO_EXTERNAL_INTEROP_CANDIDATE
NO_GO_U2_PRODUCTION_SECURITY
NO_GO_PRODUCTION
NO_CLAIM_STANDARD_ADOPTION
NO_CLAIM_DARPA_CERTIFICATION
LEGAL_NOVELTY_UNKNOWN
```

## Admission BUILD-21

L'archive BUILD-21 mesure 123 091 023 octets et son SHA-256
`e0367940c89ee91a19af95e7bc40ea4ce1fa658e1f0dbd3a3e0e626a84409269`
correspond au rapport final et au rapport de contre-exécution fournis. Elle
contient 187 entrées, 186 fichiers manifestés, sans doublon, chemin dangereux,
symlink ni erreur CRC. Deux extractions vierges ont chacune passé manifeste
186/186 et gate 7/7.

Le sidecar physique demandé par le contrat n'était pas joint à côté du ZIP.
Cette absence reste explicitement enregistrée ; aucun sidecar fictif n'a été
utilisé.

## MCP officiel

Les runners npm 0.1.16 et 0.2.0-alpha.10 ont été rematérialisés depuis leurs
lockfiles exacts avec Node 24.18.0. Les deux `npm ci` passent et rapportent zéro
vulnérabilité.

```text
Active 2025-11-25 : 39/39 PASS
Active 2026-07-28 : 22/22 PASS
Draft  2026-07-28 : 85/85 PASS
```

Aucun fichier `expected-failures`, aucun patch du runner et aucune mutation du
SUT probatoire n'ont été utilisés. Les stderr SUT sont vides.

La comparaison exacte avec BUILD-20 confirme un seul changement :
`sep-2243-server-accepts-whitespace-header-value` passe de rouge à vert. Les 84
autres checks restent verts.

## Falsification

Sur quatre copies jetables séparées, le runner officiel devient rouge quand :

1. `aiew.execute_manifest` est remis en première position ;
2. le trim OWS est désactivé ;
3. InputRequiredResult est désactivé ;
4. le runtime d'abonnement est cassé tout en restant annoncé.

Résultat : 4/4 mutations officiellement détectées. Le PASS draft est donc
falsifiable et causal.

## A2A

Le `main` upstream est encore le commit
`5996b79f9cefa6fc390980e383e358a66fb9e49e`.

```text
JSON-RPC  : 79 succès, 1 échec, 185 ignorés
HTTP+JSON : 76 succès, 2 échecs, 187 ignorés
```

Les échecs connus du TCK restent préservés. Aucune variante patchée n'est
présentée comme officielle.

## OS et indépendance

Windows 11 build 26200 a exécuté nativement la campagne. Le probe WSL2 est
bloqué par `HCS_E_HYPERV_NOT_INSTALLED`; aucune preuve conteneurisée n'est
promue en VM/bare metal. Aucun macOS réel n'était disponible.

Restent également bloqués : organisation clean-room distincte, builder
indépendant signé, transparency log, red-team externe, pilote fournisseur
autorisé, hôte U2 production-grade et adoption normative.

## Conclusion

EB-2026-08-02 ferme enfin la porte MCP que BUILD-21 ne pouvait pas exécuter :

> Le SUT BUILD-21 scellé passe le draft officiel applicable 85/85 avec quatre
> contrôles négatifs officiels causalement rouges. Ce résultat est une preuve
> officielle MCP étroite ; il ne transforme pas A2A, les trois OS, les audits
> externes ou la production en preuves acquises.
