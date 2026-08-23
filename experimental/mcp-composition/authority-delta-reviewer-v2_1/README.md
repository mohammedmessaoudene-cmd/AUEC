# Authority-Delta Reviewer V2.1 Core

Status: experimental external review profile; not normative MCP text.

## Question tested

At the pinned SEP-3004 head, can two distinct authority bases that produce the
same effective authority be distinguished in the currently registered
`caller-governance` protected representation?

The reviewer constructs two individually conforming records for one governed
event:

- Decision A requests `{read, write}`, the host allows `{read}`, and the
  effective set is `{read}`.
- Decision B requests `{read}`, the host allows `{read, write}`, and the
  effective set is `{read}`.

The registered protected bodies are byte-identical and have the same event
hash. Closed structured decision objects are different and produce different
SHA-256 commitments.

The current-head projection also checks the newly typed optional fields, the
absent-versus-`null` distinction, and canonical `sources_touched` strings. Those
rules change how recorded context is encoded but do not add the tested
requested/host-allowed/effective authority basis to the registration.

Bounded classification:
`SCHEMA_BACKED_REPRESENTATION_GAP_CONFIRMED`.

## Public scope

V2.1 accepts one form only:

`closed structured decision object + SHA-256 commitment`.

The root object, decision object, and typed nested objects are closed. The
`extensions` map is committed recursively and rejects empty keys. Timestamps
must be calendar-valid UTC RFC3339 values with exactly millisecond precision.
Operation intersections, authority deltas, budgets, list re-gating, anchor
identity/generations, admission, declaration authentication, reason codes, and
idempotency contract identity are recomputed or checked.

Digest-only, evidence-reference, effect-disposition, provider-truth,
retry/payment, and normative wire-design questions are outside this public
profile.

## Reproduce

Requirements:

- Node.js 20 or newer;
- Python 3.11 or newer;
- PowerShell 7 for the one-command Windows replay.

From this directory:

```powershell
pwsh -NoProfile -File ./demo/run-review.ps1
```

The command performs no network operation. It regenerates the exact corpus,
runs independent Node and Python implementations, checks cross-language parity,
reproduces the pinned current-head projection, runs the mutation and causal
controls, and writes receipts under `results/`.

Current sealed counts:

- 70 vectors across 18 two-sided families;
- 27 parser-hostile fixtures;
- 3 canonicalization known-answer tests;
- 4,096 unique mutations from 16 operators per implementation;
- 5 same-object and 1 same-file GREEN→RED→GREEN controls.

The deterministic ZIP builder is:

```powershell
python ./build/build_reviewer.py --root . --output ./MCP_AUTHORITY_DELTA_REVIEWER_V2_1_CORE_20260823.zip
```

## Upstream pin

- Repository: `modelcontextprotocol/modelcontextprotocol`
- Pull request: `#3004`
- Tested head: `1143d96f82ce9316e4e1675a3f6786902b9fe1ce`
- Tested tree: `9ab700212973ce9a9c873f040712759e7e1a93a1`
- Source SHA-256:
  `86742f170f1267ba9dd918ec85ea485252804500f70ce875f9241530d5488345`

The proposal remains upstream work under review. This artifact does not select
or request a normative representation.

## Responsibility and licensing

OpenAI ChatGPT and Codex substantially assisted implementation, testing,
analysis, and drafting. Mohammed Messaoudene reviewed the executed evidence and
remains responsible for the claims.

AUEC-authored implementation, vector, and build files in this experimental
directory are routed as Apache-2.0 by the repository license map. See
`PROVENANCE_AND_LICENSE.md`, `AI_ASSISTANCE.md`, and `NON_CLAIMS.md`.
