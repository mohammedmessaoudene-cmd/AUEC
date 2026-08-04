# A2A upstream EB-2026-08-02

Le `main` officiel et le commit BUILD-20 sont toujours
`5996b79f9cefa6fc390980e383e358a66fb9e49e`. Le TCK a été exécuté inchangé :

```text
JSON-RPC  : 79 succès, 1 échec, 185 ignorés
HTTP+JSON : 76 succès, 2 échecs, 187 ignorés
stderr SUT/TCK : 0 octet
```

Les échecs `CORE-SEND-003` et `ResponseNotRead` sont conservés. L'issue #202 et
les PR #203, #207 et #213 étaient encore ouvertes. Aucun patch local n'est
appelé officiel.

Verdict : `NO_GO_OFFICIAL_A2A_CONFORMANCE`.
