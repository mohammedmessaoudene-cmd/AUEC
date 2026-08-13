# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations

import hashlib
import json
import re
import unittest
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
AOS_RECEIPTS = ROOT / "evidence" / "upstream" / "aos-anchors-verify"
CHECKSUM_LINE = re.compile(r"([0-9a-f]{64})  ([^\r\n]+)")


def read_checksum_index() -> dict[str, str]:
    records: dict[str, str] = {}
    for line in (AOS_RECEIPTS / "SHA256SUMS.txt").read_text(
        encoding="utf-8"
    ).splitlines():
        match = CHECKSUM_LINE.fullmatch(line)
        if match is None:
            raise AssertionError(f"malformed SHA256SUMS line: {line!r}")
        digest, name = match.groups()
        if PurePosixPath(name).name != name or name in records:
            raise AssertionError(f"unsafe or duplicate SHA256SUMS name: {name!r}")
        records[name] = digest
    return records


class ProvenanceConsistencyTests(unittest.TestCase):
    def test_public_record_snapshot_matches_machine_readable_ledger(self) -> None:
        ledger = json.loads(
            (ROOT / "UPSTREAM_CONTRIBUTIONS.json").read_text(encoding="utf-8")
        )
        expected = ledger["auecPublicRecord"]["repositorySnapshot"]
        self.assertRegex(expected, r"^[0-9a-f]{40}$")

        markdown = (ROOT / "UPSTREAM_CONTRIBUTIONS.md").read_text(encoding="utf-8")
        section = re.search(
            r"^## Public AUEC record\s*$\n(?P<body>.*?)(?=^## |\Z)",
            markdown,
            flags=re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(section, "missing Public AUEC record section")
        snapshots = re.findall(
            r"^- repository snapshot checked: `([0-9a-f]{40})`;\s*$",
            section.group("body"),
            flags=re.MULTILINE,
        )
        self.assertEqual(snapshots, [expected])

    def test_aos_checksum_index_is_exact_and_valid(self) -> None:
        records = read_checksum_index()
        expected_names = {
            path.name
            for path in AOS_RECEIPTS.iterdir()
            if path.is_file() and path.name != "SHA256SUMS.txt"
        }
        self.assertEqual(set(records), expected_names)
        for name, expected_digest in records.items():
            actual = hashlib.sha256((AOS_RECEIPTS / name).read_bytes()).hexdigest()
            self.assertEqual(actual, expected_digest, name)

    def test_every_indexed_json_receipt_is_documented(self) -> None:
        records = read_checksum_index()
        readme = (AOS_RECEIPTS / "README.md").read_text(encoding="utf-8")

        # README.md is checksum-index metadata; JSON entries are evidence receipts.
        receipt_names = sorted(name for name in records if name.endswith(".json"))
        self.assertGreater(len(receipt_names), 0)
        for name in receipt_names:
            payload = json.loads((AOS_RECEIPTS / name).read_text(encoding="utf-8"))
            self.assertIsInstance(payload, dict, name)
            self.assertIn("schema", payload, name)
            self.assertIn(f"`{name}`", readme, name)


if __name__ == "__main__":
    unittest.main()
