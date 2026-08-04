# Path-specific licensing

This repository is intentionally multi-licensed by directory. Reuse must follow
the license attached to the files actually reused.

Zenodo metadata uses the record-level identifier `other-open` ("Other
(Open)") because Zenodo applies one record-level selection to all deposited
files. That metadata choice does not grant a new license and does not replace
the path-specific licenses below. `LICENSE_MAP.csv` and the license notices in
each file or directory remain authoritative.

| Scope | License |
| --- | --- |
| `reference-runtime/**` | AGPL-3.0-only |
| `tests/**` | AGPL-3.0-only |
| `examples/run_example.py` | AGPL-3.0-only |
| `schemas/**`, `tck/**`, `sdk/**`, `bindings/**` | Apache-2.0 |
| standalone `examples/*.json` | Apache-2.0 |
| `scripts/**`, `.github/**` | Apache-2.0 |
| `docs/**`, `standards/**`, `evidence/**` | CC BY 4.0 |
| root narrative and metadata files | CC BY 4.0 unless stated otherwise |
| `LICENSES/**` | the corresponding unmodified license text |

The AGPL does not automatically relicense unrelated infrastructure. Its
application depends on the actual covered program and manner of combination or
modification. This file is an engineering routing notice, not legal advice.

A commercial alternative may be offered only for files whose rights are
demonstrably controlled by Mohammed Messaoudene. No commercial permission is
granted here, no third-party right is offered, and no file is presently listed
as commercially relicensable.

The names AIEW, AUEC, the logo, and any compatibility label are governed
separately from the copyright licenses. See `TRADEMARKS.md`.
