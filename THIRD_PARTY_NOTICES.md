# Third-party notices

The reference runtime imports only Python standard-library modules at runtime.
Its build metadata references `setuptools` and `wheel`; they are build tools,
not vendored source in this repository.

The project interoperates with external protocols and standards including MCP,
A2A, WebAssembly, WASI, HTTP and JSON. Their names and specifications remain
the property of their respective holders; compatibility work implies no
affiliation or endorsement.

The present candidate does not include a complete source-origin history. This notice is therefore
an engineering inventory, not a legal clearance. Any copied or adapted
third-party code discovered later must retain its license and attribution and
be added to `THIRD_PARTY_COMPONENTS.csv`.
