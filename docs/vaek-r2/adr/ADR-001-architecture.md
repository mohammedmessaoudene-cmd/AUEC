# ADR-001 — Kernel with typed adapters

Status: accepted for R2.

## Considered variants

| Variant | Boundary | Gas/size | Extensibility | Auditability | Decision |
|---|---|---|---|---|---|
| A. Monolithic typed kernel | Single contract | Fewer calls, largest runtime | Low | State coupling obscures adapter trust | Rejected |
| B. Kernel + typed adapter registry | Common authority, isolated effect plane | External-call overhead, smaller units | Medium | Explicit code-bound adapter boundary | Selected |
| C. Separate effect modules + authority engine | Most modular | Highest orchestration surface | High | Cross-module state/budget proofs are harder | Rejected for R2 |

Variant B provides one budget/replay/receipt state machine while keeping external integrations isolated and code-bound. The agent cannot name an adapter. No variant using executable bytes was considered admissible.

Consequences: adapter trust remains material; registry administration is privileged; typed integrations cost code and composability. These are measured and reported, not hidden.

