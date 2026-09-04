# Third-party notices

The reference runtime imports only Python standard-library modules at runtime.
Its build metadata references `setuptools` and `wheel`; they are build tools,
not vendored source in this repository.

The project interoperates with external protocols and standards including MCP,
A2A, WebAssembly, WASI, HTTP and JSON. Their names and specifications remain
the property of their respective holders; compatibility work implies no
affiliation or endorsement.

The experimental MCP composition directory includes a Python adaptation of the
23 SEP-3004 conformance fixture definitions published in
`notboatanchor/gif` at commit
`e1f02a95506e81e7766c3ba3a684ecad7cfff12f`. The source vectors are
Apache-2.0 and carry Copyright 2026 Notboatanchor Labs LLC. The adapted file
retains that notice; the Python verifier itself was independently implemented
from the normative SEP text.

The present candidate does not include a complete source-origin history. This notice is therefore
an engineering inventory, not a legal clearance. Any copied or adapted
third-party code discovered later must retain its license and attribution and
be added to `THIRD_PARTY_COMPONENTS.csv`.
