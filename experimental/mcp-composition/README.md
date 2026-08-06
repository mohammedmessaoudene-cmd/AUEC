# MCP authority-composition spike

Status: **experimental, draft-aligned, non-conformant**

This isolated experiment tests whether the AUEC authority boundary can operate
as validator logic near the open Interceptors proposal while composing with
authenticated declaration inputs and a separate audit-record construction.

```bash
make demo-mcp-composition
python -m unittest discover -s experimental/mcp-composition/tests -v
```

The experiment performs no network request and no consequential action. It
uses synthetic fixtures, fixed upstream commit pins and disposable source
mutants.

The non-negotiable boundary is:

```text
signature != authority
trust label != authority
annotation != authority
audit record != authority
claim != authority
```

Only the host policy can grant effective authority. An authenticated
declaration can narrow the evaluated risk, never widen the host policy. The
audit record is emitted after the decision and cannot affect it.

The adapter mirrors the broad shape of the open SEP-2624 `ValidationResult`
using its `info` field for profile-specific evidence. It does not implement an
MCP transport, JWS verification, RFC 8785, or official conformance.

AI assistance disclosure: OpenAI Codex assisted with the implementation,
tests, analysis and drafting. Mohammed Messaoudene reviewed the executed
evidence and remains responsible for the contribution.
