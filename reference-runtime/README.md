# AUEC reference gateway

`auec-gateway` is an engineering-alpha implementation of the AIEW/AUEC
transport-neutral execution contract. It is staged under AGPL-3.0-only in this
offline prepublication candidate.

The deterministic AUEC U0 runtime is exposed through:

- MCP profiles at `POST /mcp`;
- A2A 1.0 JSON-RPC and HTTP+JSON bindings;
- transport-neutral execution at `POST /execute`;
- A2A Agent Card at `GET /.well-known/agent-card.json`;
- corresponding-source metadata at `GET /source`.

The same source metadata is available without starting a server:

```bash
python -m aiew_gateway --source-offer
```

Before an approved public build, set the exact release values:

```text
AUEC_SOURCE_RELEASE_URL
AUEC_SOURCE_REF
AUEC_SOURCE_ARCHIVE_SHA256
```

Modified builds must also set `AUEC_BUILD_MODIFIED=1` and a non-empty
`AUEC_MODIFICATION_NOTICE`; the runtime rejects a hidden modification state.
The `/source` route is an engineering compliance aid, not a legal opinion.

This package is not a production sandbox. It does not provide production
authentication, an audited U2/WASI host, external certification, independent
interoperability proof or complete A2A conformance.
