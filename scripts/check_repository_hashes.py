# SPDX-License-Identifier: Apache-2.0
"""Regenerate the repository hash manifest and compare it byte for byte."""

from __future__ import annotations

import difflib
import tempfile
from pathlib import Path

from generate_hashes import MANIFEST_NAME, generate_manifest


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    committed = ROOT / MANIFEST_NAME
    if not committed.is_file():
        print(f"REPOSITORY HASH AUDIT FAIL: missing {MANIFEST_NAME}")
        return 1

    with tempfile.TemporaryDirectory(prefix="auec-repository-hashes-") as temp:
        generated = Path(temp) / "HASHES.generated"
        records = generate_manifest(ROOT, generated)
        expected = committed.read_text(encoding="utf-8").splitlines(keepends=True)
        actual = generated.read_text(encoding="utf-8").splitlines(keepends=True)

    if expected != actual:
        print("REPOSITORY HASH AUDIT FAIL: committed manifest is stale")
        print(
            "".join(
                difflib.unified_diff(
                    expected,
                    actual,
                    fromfile=MANIFEST_NAME,
                    tofile="HASHES.generated",
                )
            ),
            end="",
        )
        return 1

    print(
        "REPOSITORY HASH AUDIT PASS: "
        f"{records} records; generated manifest is byte-identical"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
