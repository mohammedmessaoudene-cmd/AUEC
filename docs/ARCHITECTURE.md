# Architecture

```text
Remote AI planner
        |
        | proposes signed/identified AUEC manifest
        v
Sovereign local user agent
  - parse and validate
  - intersect with host policy
  - classify data
  - choose permitted placement
  - enforce budgets and capabilities
        |
        +--> deterministic local runtime / WASI profile
        +--> approved edge service
        +--> approved cloud operation
        |
        v
Typed outputs + chained receipts + terminal digest
        |
        v
Remote AI verifies compact result and continues reasoning
```

## Layering

- **AIEW:** overall architecture and ecosystem concept.
- **AUEC:** transport-neutral execution contract.
- **Authoring layer:** optional JavaScript-like or declarative developer interface compiling to AUEC.
- **User agent:** local authority analogous to a browser.
- **Execution profiles:** U0 deterministic, later local-model or component profiles.
- **Bindings:** MCP, A2A, HTTP, browser and offline packages.

A binding cannot grant more authority than the local host policy.
