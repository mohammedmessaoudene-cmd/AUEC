# AUEC 0.36.0-prestandard — pre-release notes

Status: **pre-standard research release; not production ready**.

This candidate adds three isolated core-semantic causal controls. Mutations
that bypass the host-operation allowlist, admit a `claim` into U0, or treat a
`claim` as authority each make the corresponding safety test red; restoration
returns it to green. A pure authorization predicate performs no external
effect. Finite models check 345 declared cases with no counterexample.

Executed results remain scoped to their recorded profiles. The A2A matrix is
incomplete, and the candidate has no external security certification,
independent implementation proof, provider-authorized pilot result or adopted
standard status.

Licensing is assigned by path:

- AGPL-3.0-only for the runtime, gateway and tightly coupled executable code;
- Apache-2.0 for separable schemas, TCK, SDK and bindings;
- CC BY 4.0 for the specification, report and narrative documentation.

Repository: <https://github.com/mohammedmessaoudene-cmd/AUEC>

Release: <https://github.com/mohammedmessaoudene-cmd/AUEC/releases/tag/v0.36.0-prestandard>

Zenodo version DOI: <https://doi.org/10.5281/zenodo.21815335>. This record is
created through `New version` from the historical
<https://doi.org/10.5281/zenodo.21796636> record.
