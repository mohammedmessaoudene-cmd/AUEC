# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reference-runtime"))

from aiew_uc.canonical import canonical_json_text, strict_json_loads
from aiew_uc.model import default_host_policy
from aiew_uc.runtime import UniversalRuntime
from aiew_uc.verification import verify_result


class PublicationSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = json.loads((ROOT / "examples" / "hello_manifest.json").read_text(encoding="utf-8"))

    def test_valid_manifest_executes_and_verifies(self) -> None:
        result = UniversalRuntime().execute(self.manifest)
        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(result["receiptCount"], 1)
        verify_result(result, self.manifest)

    def test_secret_export_is_rejected(self) -> None:
        manifest = json.loads(json.dumps(self.manifest))
        manifest["resources"]["message"]["classification"] = "secret"
        manifest["nodes"][0]["output"]["classification"] = "secret"
        result = UniversalRuntime().execute(manifest)
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["error"]["code"], "E_EGRESS_CLASSIFICATION")

    def test_duplicate_keys_are_rejected(self) -> None:
        with self.assertRaises(Exception):
            strict_json_loads('{"a":1,"a":2}')

    def test_float_is_rejected_by_canonical_contract(self) -> None:
        with self.assertRaises(Exception):
            canonical_json_text({"x": 1.5})

    def test_default_policy_is_local_and_pure(self) -> None:
        policy = default_host_policy()
        self.assertEqual(policy["allowedPlacements"], ["local"])
        self.assertEqual(policy["allowedEffects"], ["pure"])
        self.assertFalse(policy["allowClaimExport"])


if __name__ == "__main__":
    unittest.main()
