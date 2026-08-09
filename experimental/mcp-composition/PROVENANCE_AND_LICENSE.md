# Provenance and license

The files under `experimental/mcp-composition/` were authored within AUEC as a
clean-room implementation relative to the TypeScript reference and are licensed
under Apache-2.0 according to `LICENSE_MAP.csv`. This is source-provenance
separation, not organizationally independent validation.

The clean-room Python verifier was implemented from the public normative prose
of the open SEP-3004 proposal pinned in `UPSTREAM_PINS.json`, before comparison
with the reference implementation.

`sep3004_vectors.py` adapts the published Apache-2.0 fixture values and
expected C-REC-1…7 dispositions from:

- repository: `notboatanchor/gif`;
- pinned commit: `e1f02a95506e81e7766c3ba3a684ecad7cfff12f`;
- path: `mcp-server/conformance/audit-record-contract/vectors.ts`;
- original notice: Copyright 2026 Notboatanchor Labs LLC.

The evaluator and verifier logic are not copied from the TypeScript reference.
The adapted fixture file retains the original copyright attribution and notes
that it is a Python adaptation.

At the pinned repository state, new MCP specification and code contributions
are licensed Apache-2.0, documentation excluding specifications is CC BY 4.0,
and older contributions may retain MIT during the project's licensing
transition. This spike does not redistribute those upstream files.

AI assistance was used and is disclosed in `README.md`. Internal review roles
are not external reviewers or endorsements.
