# External fixture cross-run and vector contribution

## Pinned source

- repository: `tersignhq/evidence-record-conformance`;
- commit: `46ad663b90805a2e526ef3cd28c3f70762883125`;
- tree: `0bb14fc71c2a5470b8a8349ba7ba3bd8c9f47a7f`;
- license: Apache-2.0;
- exact Git blobs: p18 `d0f56b9…`, n25 `2eeae70…`, n26 `52104df…`.

The packaged preflight snapshots preserved the evaluated inputs and expectations
but were reformatted and had shortened descriptions. The executed cross-run
therefore consumed the repository blobs with `git cat-file`, not the snapshots
or CRLF-filtered checkout bytes.

## Executed results

- unchanged pinned suite: 44/44 Python, 44/44 TypeScript;
- unchanged differential: 252 cases, 208 off-corpus, 0 divergence;
- AUEC adapter cross-run: p18 valid, n25 reject, n26 reject — 3/3;
- contribution commit: `c23a985c51b99cf8ec71aebf5af9f53aa34747cc`;
- contribution suite: 47/47 Python, 47/47 TypeScript;
- contribution differential: 299 cases, 252 off-corpus, 0 divergence;
- deterministic regeneration: 48 generated artifacts, byte-identical;
- second clean-clone application and complete rerun: pass.

## Evidence tiers

1. Tersign authored and versioned p18/n25/n26: third-party-authored fixtures.
2. AUEC/Codex executed the documented adapter: project-controlled execution over external
   fixtures, not independent validation.
3. [Tersign PR #5](https://github.com/tersignhq/evidence-record-conformance/pull/5)
   is open as a draft. GitHub Actions run
   [31318111163](https://github.com/tersignhq/evidence-record-conformance/actions/runs/31318111163)
   is `action_required` with zero jobs because first-time-contributor execution
   awaits maintainer approval. This is not a CI pass.
4. Third-party human review and merge have not occurred.

The new vectors test canonical object binding only. They do not choose a future
MCP field, prove producer truth or policy correctness, establish historical
position, or claim MCP conformance, acceptance, standardization, certification
or production readiness.

AI-assistance disclosure: OpenAI ChatGPT and Codex assisted with implementation,
testing, analysis and drafting. Mohammed Messaoudene reviewed the executed
evidence and remains responsible.
