# AUEC reference gateway

`auec-gateway` is the public engineering-alpha reference implementation of the
AIEW/AUEC transport-neutral execution contract. The covered runtime source is
published under `AGPL-3.0-only`.

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

Official release builds must set exact, version-specific values for:

```text
AUEC_SOURCE_RELEASE_URL
AUEC_SOURCE_REF
AUEC_SOURCE_ARCHIVE_SHA256
```

Local, development and modified builds must not impersonate an official
release. Modified builds must set `AUEC_BUILD_MODIFIED=1` and a non-empty
`AUEC_MODIFICATION_NOTICE`. When `AUEC_BUILD_MODIFIED=1`, the runtime rejects
an empty notice; it cannot detect an undisclosed code modification. The
`/source` route is an engineering compliance aid, not a legal opinion.

This package is not a production sandbox. It does not provide production
authentication, an audited U2/WASI host, external certification, independent
interoperability proof or complete A2A conformance.
