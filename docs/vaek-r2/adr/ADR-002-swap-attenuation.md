# ADR-002 — Swap attenuation ambiguity

Status: accepted for R2.

Reducing `maxInput` while automatically reducing `minOutput` can weaken price protection or change intent. R2 therefore never performs that two-dimensional transformation automatically.

- Identity fields and quote commitment remain identical.
- `maxInput` may be reduced only when `minOutput` remains equal or becomes stricter.
- If this makes the trade infeasible, the result is `ESCALATE`, not silent repair.
- A principal approval binds the exact authorization hash for any manually accepted narrowed swap.

