# Contributing

This repository publishes a research pre-standard. Issues and contributions
are welcome when they preserve the evidence and licensing boundaries below.

## Principles

- Preserve transport neutrality in the AUEC core.
- Treat MCP, A2A, HTTP and browser integration as bindings.
- Prefer deterministic and falsifiable behavior.
- Never weaken the manifest executor merely to satisfy a conformance fixture.
- Add a regression test for every defect.
- Separate official conformance results from local mirrors or patched harnesses.
- State all unsupported claims and blocked gates.

## Pull-request requirements

A pull request should include:

1. problem statement and threat impact;
2. normative text change, if any;
3. implementation change;
4. positive and negative tests;
5. compatibility analysis;
6. update to `CHANGELOG.md`;
7. evidence that no private key, credential or local absolute path was added.

## Developer commands

```bash
export PYTHONPATH="$PWD/reference-runtime"
python -m unittest discover -s tests -v
python -m compileall -q reference-runtime
```

Material reference-runtime contributions are not accepted into a commercially
relicensable set until a human-approved contributor agreement grants sufficient
rights. A DCO alone is not represented as automatically sufficient for
proprietary relicensing. See `CONTRIBUTOR_RIGHTS_POLICY.md` and
`CLA_REVIEW_REQUIRED.md`.
