# AIEW/AUEC - verifiable hybrid AI execution

AUEC is a provider- and transport-neutral contract layer that binds remote AI
proposals to host-controlled authority. Its bounded contribution is the joint
treatment of capability and placement intersection, information-flow and
budget constraints, epistemic validation at the authorization boundary, and
portable tamper-evident execution receipts.

Status: `0.36.0-prestandard` research pre-release. This is a research pre-standard and reference
implementation. It is not an adopted standard, a production security
certification, or an endorsed project. The preserved A2A results remain
incomplete. Independent implementations, external security review, and
provider-authorized workload trials remain future evidence.

## Publication status

The historical public source AUEC `0.35.0-prestandard` remains available at
<https://github.com/mohammedmessaoudene-cmd/AUEC/releases/tag/v0.35.0-prestandard>.
Its Zenodo software deposit is identified by
<https://doi.org/10.5281/zenodo.21796636>.

Version `0.36.0-prestandard`, released at
<https://github.com/mohammedmessaoudene-cmd/AUEC/releases/tag/v0.36.0-prestandard>
and archived under <https://doi.org/10.5281/zenodo.21815335>, adds causal
mutation evidence for the U0 host-operation intersection and
epistemic-admission guards. It also includes a
pure authorization predicate that evaluates epistemic status, independent
validation, host effect policy, and action-bound consent without executing an
external effect.

## Mixed licensing by path

- `reference-runtime/`, runtime-coupled `tests/`, and
  `examples/run_example.py`: **AGPL-3.0-only**.
- `schemas/`, `tck/`, `sdk/`, `bindings/`, autonomous examples, build scripts,
  and repository automation: **Apache-2.0**.
- `docs/`, `standards/`, technical report, diagrams, governance, and narrative
  repository documentation: **CC BY 4.0**.

This is not a single-license repository. See `LICENSING.md`,
`LICENSE_MAP.csv`, and `THIRD_PARTY_NOTICES.md`. A commercial alternative may
be offered only for files whose copyrights are demonstrably controlled by
Mohammed Messaoudene. The AIEW and AUEC names and any compatibility label are
governed separately by `TRADEMARKS.md` and `CONFORMANCE_MARK_POLICY.md`.
The Zenodo candidate therefore uses the record-level identifier `other-open`;
this avoids falsely assigning one license to every deposited file and does not
override the per-path license map.

## Quick checks

```bash
PYTHONPATH=reference-runtime python -m unittest discover -s tests -v
python scripts/check_license_map.py
python scripts/check_claims.py
python scripts/scientific_release_gate.py
python scripts/style_audit.py
python scripts/public_release_gate.py
python scripts/run_core_semantic_mutations.py
python scripts/run_bounded_models.py
```

## Two-minute authority-boundary demo

Run the safe, deterministic demonstration with:

```bash
make demo-authority-boundary
```

It exercises three local controls: host-operation policy intersection, U0
epistemic admission, and the pure authorization predicate. Each guard is
disabled only inside a disposable copy, where the safety oracle must turn red;
restoration must return it to green. The command performs no consequential
action, accepts no untrusted shell input, and requires no network or
credentials. See `docs/DEMO_AUTHORITY_BOUNDARY.md`.

The technical report and reproducible sources are in
`docs/technical-report/`.
