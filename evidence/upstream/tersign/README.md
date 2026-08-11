# Tersign structural evidence receipts

Status: **external CI, maintainer-reported rerun/review, and corpus merge
obtained for the narrow structural contribution**.

The contribution introduced `p19`, `n27`, and `n28` for the
`decision_evidence_binding` property. GitHub Actions workflow run
[`31337102263`, attempt 2](https://github.com/tersignhq/evidence-record-conformance/actions/runs/31337102263/attempts/2)
completed two successful jobs before merge:

- `conformance`: a 47-vector Python conformance pass exercising both verdicts,
  all 10 reject reasons, and all 10 vector kinds; `p19` was valid and `n27`
  and `n28` rejected with `binding_reject`;
- `cross-implementation`: all 47 vectors agreed across Python and TypeScript,
  and 299 differential cases, including 252 off-corpus cases, produced zero
  divergences.

The workflow tested synthetic merge commit
`c02389542d2307740278709216e026a70a75b43f`, whose tree is
`08890c3483b3e8dfee9e2fc9bb385414497c9112`. That tree is identical to the
tree of signed final merge commit
[`79632084d94ba9841baa0f000ffd6c31ec22b3e2`](https://github.com/tersignhq/evidence-record-conformance/commit/79632084d94ba9841baa0f000ffd6c31ec22b3e2).
The maintainer separately reported an independent rerun and review in
[comment `5252217382`](https://github.com/tersignhq/evidence-record-conformance/pull/5#issuecomment-5252217382).

## Files

- `ci-review-merge-receipt.json`: bounded machine-readable chronology and
  evidence-tier receipt;
- `SHA256SUMS.txt`: hashes of the files in this directory at this preparation
  snapshot.

## Claim boundary

These facts establish external CI, a maintainer-reported rerun/review, and
merge of this structural Tersign contribution. They do not independently
validate AUEC, producer truth, semantic authority reduction, an MCP field or
canonicalization, or MCP adoption.

No Tersign source, fixture, log archive, credential, or private package is
copied here.

## License and attribution

This project-authored evidence compilation is offered under CC BY 4.0 to the
extent the project controls copyright in the compilation. Tersign source,
fixtures, names, and independently authored material remain subject to their
original rights and terms.
