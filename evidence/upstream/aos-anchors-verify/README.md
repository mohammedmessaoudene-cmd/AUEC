# AOS anchors-verifier evidence receipts

Status: **project-controlled v0.4-v0.8 evidence indexed; T2 remains open**.

This evidence-only candidate records four distinct sources without combining
their evidentiary weight:

1. AUEC/Codex-controlled v0.4 separator receipts covering CR, VT, FF, FS, GS,
   RS, NEL, U+2028 and U+2029 across the three environments named in the
   receipt.
2. Bounded factual summaries of AOS maintainer comments reporting reproduction
   of the v0.4 CR defect, its v0.5 correction and attribution, and a separate
   v0.5 T2 matrix.
3. An exact project-controlled rerun of the corrected public T1/T3 gist against
   the pinned v0.6 verifier and stream, reconciled with the earlier archived
   project class receipts.
4. An exact project-controlled authentication and bounded reproduction campaign
   for the public v0.8 tag, including historical controls, differential results,
   challenge findings, and a bounded receipt for the maintainer's release
   comment.

The exact v0.5 tag was exercised on Windows Python 3.11, 3.12 and 3.14 and on
Linux WSL1 Python 3.10. All 36 separator attacks failed closed with a digest
mismatch. The project reconstruction of the eight described T2 mutations plus
baseline produced the expected semantic classes on all four runtimes. Baseline
and the unattested-tip mutation remain `VERIFY PARTIAL` with 18 of 24 lines
attested.

The exact v0.8 tag was authenticated as a lightweight tag at commit
`15f2b50a77b78a0857d3c7e697726373406cd0ef`. Five project-controlled Windows
and WSL runtime matrices reproduced 16/16 self-tests per runtime and the honest
stream at 25 lines, 18 attested, `VERIFY PARTIAL`, exit 3. The bounded challenge
matrix reproduced documentation/raw-byte, schema-type, cross-parser, and Git
identity reproducibility/TOCTOU gaps. It did not demonstrate acceptance of
altered attested bytes, unauthorized Git history, trust-anchor confusion, or a
security bypass. macOS was not tested.

## Files

- `v0.4-nine-separator-receipts.json`: project-controlled v0.4 receipt;
- `maintainer-confirmation-and-t2-report.json`: bounded summary of maintainer
  comments [`5247993630`](https://github.com/aos-standard/catalog/issues/1#issuecomment-5247993630)
  and [`5248157822`](https://github.com/aos-standard/catalog/issues/1#issuecomment-5248157822);
- `project-v0.5-t2-reconstruction.json`: bounded project-controlled v0.5
  separator and T2 reconstruction result;
- `t1-t3-corrected-gist-reproduction.json`: exact pinned-gist hashes, outputs,
  T3 result, and bounded T1 class reconciliation without vendoring the gist;
- `v0.8-tag-and-object-receipt.json`: exact lightweight-tag, commit, tree, blob,
  and raw-byte identities from project-controlled, GET-only acquisition;
- `v0.8-project-controlled-rerun.json`: five-runtime self-test, honest-stream,
  historical T2, and separator-control results;
- `v0.8-differential-v0.7.json`: bounded v0.7/v0.8 object and behavioral
  comparison, including the limits of producer/verifier parity evidence;
- `v0.8-challenge-matrix.json`: minimized H1-H7 findings and their explicit
  nonsecurity boundaries;
- `v0.8-maintainer-comment.json`: bounded factual summary and hash receipt for
  public maintainer comment `5274195840`, without vendoring its raw body;
- `SHA256SUMS.txt`: hashes of the files in this directory at this preparation
  snapshot.

## Claim boundary

- The maintainer reported that the described v0.5 T2 constructions held.
- The project-controlled reconstruction observed the same semantic classes for
  the eight explicitly described mutations plus an unmodified baseline.
- Eight mutations were explicitly described; the ninth reported construction
  may be the baseline or an unlisted mutation.
- Exact maintainer T2 artifacts were not linked, so an exact artifact diff is
  unavailable.
- `VERIFY PARTIAL` is not `VERIFY OK`; the unattested tip remains outside the
  18-line attested prefix.
- T2 remains open. No formal proof, adoption, endorsement, or independent AUEC
  validation is claimed.
- The maintainer did not report reproducing all nine project v0.4 separator
  cases.
- The T1/T3 gist reproduction is project-controlled. Its author is marked
  association `NONE` in the AOS issue, and no AOS maintainer disposition on
  T1/T3 is claimed.
- The observed T3 whole result is `VERIFY PARTIAL`, not `VERIFY OK`. The T1
  statement is limited to the tested current retrospective append construction
  and is not an absolute cryptographic impossibility claim.
- The v0.8 rerun and challenge matrix are project-controlled evidence, not
  independent validation of AOS or AUEC.
- The reproduced v0.8 gaps are bounded documentation, schema,
  interoperability, and reproducibility gaps. No security impact was
  demonstrated.
- Producer/verifier parity remains maintainer-reported because the public v0.8
  tag does not include the exporter required for an independent parity rerun.
- The v0.8 string-valued `asset_id` narrowing does not close the observed
  non-string schema-type gap. The accepted non-string values did not become
  records.
- `line_count:true` had integer-equivalent semantics to `1` and covered the
  same record; it did not attest additional or different bytes.
- All live Git references observed during the bounded v0.8 matrix resolved to
  authorized history; no actual race or unauthorized-history acceptance was
  demonstrated.

No raw AOS source, stream, sidecar, secret, token or private archive is included
here.

## License and attribution

This project-authored evidence compilation is offered under CC BY 4.0 to the
extent the project controls copyright in the compilation. Third-party facts,
names, repositories and independently authored material remain subject to
their original rights and terms. Compatibility and evidence work imply no AOS,
MCP or Linux Foundation affiliation or endorsement.
