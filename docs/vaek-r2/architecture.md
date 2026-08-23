# VAEK R2 frozen architecture

> RESEARCH PROTOTYPE — NOT AUDITED — NO PRODUCTION FUNDS

## Selected variant: kernel plus typed adapter registry

```text
untrusted JSON
  -> strict bridge + symbolic IDs
  -> VAEKKernel typed submit functions
  -> deterministic attenuation / risk / verification
  -> execution-time mandate + registry + adapter recheck
  -> kernel-selected typed adapter
  -> restricted external system
  -> requested / authorized / executed receipt
```

The Solidity experiment is isolated in `vaek-r2/`. `bv-aic-r1/` remains frozen.

## Components and boundaries

- `VAEKTypes`: closed enums and structs; no executable byte payload.
- `ResourceRegistry`: symbolic resource ID to typed address, active flag and global version.
- `AdapterRegistry`: effect type to active address, version and runtime code hash. Requests never contain these values.
- `RiskEngine`: pure monotone maximum of deterministic tiers; model concern may only raise the result.
- `VAEKKernel`: mandate, request lifecycle, effect-specific attenuation, verification/human binding, execution-time recomputation, replay lock, budgets and receipts.
- `ERC20TransferAdapter`, `BoundedSwapAdapter`, `ServiceEscrowAdapter`: separate typed interfaces and kernel-only entry points.
- `agent/bridge`: strict JSON compiler. It never executes output and never accepts an ABI, target, selector or adapter.
- `tools/receipt_verifier`: independent canonical receipt checker using public data/fixtures only.

## Frozen public surfaces

- `submitTransfer(header, request)` / `executeTransfer(executionId)`
- `submitSwapExactInput(header, request)` / `executeSwapExactInput(executionId)`
- `submitServicePurchase(header, request)` / `executeServicePurchase(executionId)`

Typed approval functions may narrow only declared scalar fields. A generic `submit(bytes)` or agent-facing `execute(address,bytes)` is forbidden.

## State and atomicity

Submission records a canonical request commitment. Authorization records a type-specific commitment and attenuation witness. Execution checks the current mandate, global resource version, adapter version/code hash, expiries, quote, verification and exact human approval. Budget is reserved before the adapter call; any revert rolls back state. A successful adapter result creates exactly one stored receipt and one event.

## Registry decision

R2 uses owner-controlled registry entries with explicit monotonically increasing global versions. Any registry mutation invalidates a pending authorization bound to the prior version. This is intentionally coarse. Production governance and fine-grained compatibility are outside scope.

## Receipt decision

R2 stores a compact receipt summary on-chain and emits the same commitment plus typed actual values. Canonical full documents remain off-chain and independently reproducible. This costs more than events-only but makes the verifier independent of a privileged indexer.

