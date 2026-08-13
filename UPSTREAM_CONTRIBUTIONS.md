# Upstream contributions ledger

This ledger indexes public AUEC-related contributions authored by Mohammed
Messaoudene. It records chronology and current disposition; it does not claim
adoption, endorsement, partnership, ownership of ideas or methods, or
independent validation of AUEC.

Live statuses were checked at `2026-08-13T02:35:32Z`. The bounded AOS evidence
receipts integrated below extend through `2026-08-12T23:59:12Z`. Both may
change at the linked upstream artifacts.

## MCP routing discussion

- artifact: [MCP Discussion #3202](https://github.com/modelcontextprotocol/modelcontextprotocol/discussions/3202);
- focused follow-up: [discussion comment `17946421`](https://github.com/modelcontextprotocol/modelcontextprotocol/discussions/3202#discussioncomment-17946421);
- contribution: narrowed the candidate work to a host-owned
  requested-to-effective authority delta and decision basis rather than a new
  receipt or wire primitive;
- status: public routing discussion; no MCP adoption or acceptance claimed.

## MCP SEP-3004 evidence thread

- initial evidence: [comment `5228991875`](https://github.com/modelcontextprotocol/modelcontextprotocol/pull/3004#issuecomment-5228991875);
- vector contribution report: [comment `5232012364`](https://github.com/modelcontextprotocol/modelcontextprotocol/pull/3004#issuecomment-5232012364);
- bounded third-party fixture acknowledgement: [comment `5234927696`](https://github.com/modelcontextprotocol/modelcontextprotocol/pull/3004#issuecomment-5234927696);
- contribution: `CG-DELTA-LOSS-01`, requested-to-effective authority-delta
  analysis, and a bounded report of the Tersign vector work;
- upstream snapshot discussed: `377f8d260ded5b6854871b2ce3c73621ffcaef1d`;
- status: SEP PR open and unmerged; public evidence contribution, with no MCP
  acceptance, sponsorship, or normative-field claim.

## Tersign evidence-record-conformance

- artifact: [merged PR #5](https://github.com/tersignhq/evidence-record-conformance/pull/5);
- base snapshot: `46ad663b90805a2e526ef3cd28c3f70762883125`;
- contribution head: `2f6bef0dc531ce9e1a8ae1dc3cef6704ec2b5df5`;
- CI synthetic merge: `c02389542d2307740278709216e026a70a75b43f`;
- signed final merge: `79632084d94ba9841baa0f000ffd6c31ec22b3e2`;
- shared synthetic/final tree: `08890c3483b3e8dfee9e2fc9bb385414497c9112`;
- contribution: structural decision-evidence binding vectors `p19`, `n27`, and
  `n28`, plus their generator and documentation;
- external CI: [workflow `31337102263`, attempt 2](https://github.com/tersignhq/evidence-record-conformance/actions/runs/31337102263/attempts/2)
  completed conformance and cross-implementation successfully against the
  synthetic PR merge ref before merge;
- maintainer evidence: [comment `5252217382`](https://github.com/tersignhq/evidence-record-conformance/pull/5#issuecomment-5252217382)
  reports an independent rerun and review, recorded separately from the CI
  logs;
- status: external CI passed, maintainer-reported rerun/review obtained, and
  the structural contribution merged;
- explicit limits: this establishes the narrow structural property only. It
  does not independently validate AUEC, producer truth, semantic authority
  reduction, an MCP field/canonicalization, or MCP adoption.

## AOS anchors verifier

- artifact: [issue #1 comment `5242963828`](https://github.com/aos-standard/catalog/issues/1#issuecomment-5242963828);
- maintainer fix report: [comment `5247993630`](https://github.com/aos-standard/catalog/issues/1#issuecomment-5247993630);
- maintainer T2 report: [comment `5248157822`](https://github.com/aos-standard/catalog/issues/1#issuecomment-5248157822);
- T1/T3 correction and exact construction: [comment `5257449945`](https://github.com/aos-standard/catalog/issues/1#issuecomment-5257449945)
  and [pinned gist revision `4690a69c...`](https://gist.github.com/wowlegend/8045315e2651d7bcbf1acbb45ee5325d/4690a69c08605271844a58e8e1b9436585a50c28);
- v0.8 maintainer release and attribution report: [comment `5274195840`](https://github.com/aos-standard/catalog/issues/1#issuecomment-5274195840);
- v0.4 snapshot: tag `anchors-verify-v0.4`, commit
  `44c40ba4fd6a12aa19c419e440a2f69512e99acc`;
- v0.5 snapshot reported for bounded reconstruction: tag
  `anchors-verify-v0.5`, commit
  `3602e695d32167876871578b975031bc7b0331c7`;
- v0.6 T1/T3 snapshot: tag `anchors-verify-v0.6`, commit
  `e86a08673daa6e1ea2a4ab152c7690a0d268d8e6`;
- v0.8 snapshot: lightweight tag `anchors-verify-v0.8`, commit
  `15f2b50a77b78a0857d3c7e697726373406cd0ef`, tree
  `89d7a250db6544b190e23a6663361c303429ced8`;
- project contribution: minimal reproducer and nine project-controlled v0.4
  separator receipts with the same `VERIFY PARTIAL` disposition;
- maintainer disposition: the v0.4 CR defect was reproduced, corrected in
  v0.5 and credited; a separate described T2 matrix reportedly held;
- explicit limits: the maintainer did not report reproducing all nine project
  v0.4 separator cases, the exact T2 artifacts were not linked, `PARTIAL` is
  not `OK`, and T2 remains open;
- project reconstruction: four project-controlled runtimes reproduced the
  expected semantic classes for the eight described T2 mutations plus the
  baseline; 36 separator attacks failed closed, while baseline and the
  unattested tip remained `PARTIAL` at 18/24 lines;
- exact gist reproduction: Windows and Linux/WSL produced byte-identical
  output and the five published digest prefixes. The T3 binding accepted 25 of
  26 lines with two forged rows inside the attested prefix, while the whole
  result remained `VERIFY PARTIAL`. The corrected T1 classes match the prior
  archived project receipts: two `PARTIAL` outcomes and three `VerifyError`
  outcomes;
- evidence status: the bounded receipts are published in
  `evidence/upstream/aos-anchors-verify/`; this is project evidence, not
  independent validation or an exact diff against unlinked maintainer
  artifacts. The gist author is marked association `NONE` in the AOS issue;
  no AOS maintainer disposition on T1/T3 is claimed, and the T1 statement is
  limited to the tested current retrospective append construction.
- v0.8 exact rerun: five project-controlled runtime matrices on Windows and
  WSL reproduced the pinned tag self-tests at 16/16 per runtime and the honest
  stream at 25 lines, 18 attested, `VERIFY PARTIAL`, exit 3. Historical T2
  dispositions matched 11/11 and nine separator mutations failed closed;
  macOS was not tested.
- v0.8 bounded challenge result: documentation/raw-byte, schema-type,
  cross-parser interoperability, and Git-identity reproducibility/TOCTOU gaps
  were reproduced. No acceptance of altered attested bytes, unauthorized Git
  history, trust-anchor confusion, or security bypass was demonstrated in the
  bounded matrix.
- exact limits: the v0.8 `asset_id` collision closure applies to string values,
  while tested non-string values remained a schema-type gap. `line_count:true`
  produced `VERIFY OK` with integer-equivalent semantics to `1` and covered the
  same one record; it did not attest different bytes. Mutable Git references
  expose a reproducibility and potential TOCTOU gap, but all live references
  observed resolved to authorized history. Producer/verifier parity remains
  maintainer-reported because the public tag does not include the exporter.
- attribution: AOS authored and published the v0.8 implementation. Mohammed
  Messaoudene directed the question and project-controlled causal tests.
  OpenAI ChatGPT and Codex assisted with campaign design, execution, analysis,
  and evidence organization; Mohammed remains responsible for these public
  claims and the release decision.

## Public AUEC record

- repository snapshot checked: `cefcae95b1401b5365a3bceec621b181b549980e`;
- historical release: [`v0.35.0-prestandard`](https://github.com/mohammedmessaoudene-cmd/AUEC/releases/tag/v0.35.0-prestandard), Zenodo record [`21796636`](https://zenodo.org/records/21796636);
- current release: [`v0.36.0-prestandard`](https://github.com/mohammedmessaoudene-cmd/AUEC/releases/tag/v0.36.0-prestandard), Zenodo record [`21815335`](https://zenodo.org/records/21815335);
- concept DOI: [`10.5281/zenodo.21796635`](https://doi.org/10.5281/zenodo.21796635);
- version DOI: [`10.5281/zenodo.21815335`](https://doi.org/10.5281/zenodo.21815335).

These records identify published versions. They do not change the disposition
of any upstream contribution listed above.

The v0.36 DOI record predates the v0.8 receipts added here. It does not claim
that these receipts are included in that release, and it is not a complete
top-level title/artifact/hash binding for this later evidence.

## Public author identifiers

- GitHub: [`mohammedmessaoudene-cmd`](https://github.com/mohammedmessaoudene-cmd);
- ORCID: [`0009-0007-4665-2548`](https://orcid.org/0009-0007-4665-2548);
- AUEC release DOI: [`10.5281/zenodo.21815335`](https://doi.org/10.5281/zenodo.21815335).

For machine-readable IDs, URLs, snapshots, and boundaries, see
`UPSTREAM_CONTRIBUTIONS.json`.
