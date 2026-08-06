# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_hash_generator():
    path = ROOT / "scripts" / "generate_hashes.py"
    spec = importlib.util.spec_from_file_location("auec_generate_hashes", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RepositoryHashTests(unittest.TestCase):
    def test_manifest_and_alternate_output_are_never_self_hashed(self) -> None:
        module = load_hash_generator()
        with tempfile.TemporaryDirectory(prefix="auec-hash-test-") as temp:
            root = Path(temp)
            (root / "payload.txt").write_text("payload\n", encoding="utf-8")
            (root / "CHANGELOG.md").write_text("changes\n", encoding="utf-8")
            (root / "bindings.txt").write_text("bindings\n", encoding="utf-8")
            (root / ".ruff_cache").mkdir()
            (root / ".ruff_cache" / "cache").write_text("transient\n", encoding="utf-8")
            (root / module.MANIFEST_NAME).write_text("stale\n", encoding="utf-8")
            generated = root / "HASHES.generated"

            records = module.generate_manifest(root, generated)
            manifest = generated.read_text(encoding="utf-8")
            paths = [line.split("  ", 1)[1] for line in manifest.splitlines()]

        self.assertEqual(records, 3)
        self.assertIn("  payload.txt\n", manifest)
        self.assertNotIn(module.MANIFEST_NAME, manifest)
        self.assertNotIn("HASHES.generated", manifest)
        self.assertEqual(paths, sorted(paths))


if __name__ == "__main__":
    unittest.main()
