# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reference-runtime"))
sys.path.insert(0, str(ROOT / "scripts"))

from aiew_uc.canonical import digest_json  # noqa: E402
from aiew_uc.model import default_host_policy  # noqa: E402
from aiew_uc.runtime import UniversalRuntime  # noqa: E402
from demo_authority_boundary import build_demo_payload  # noqa: E402


def _manifest() -> dict:
    return json.loads(
        (ROOT / "examples" / "hello_manifest.json").read_text(encoding="utf-8")
    )


class AuthorityBoundaryDemoTests(unittest.TestCase):
    def test_live_demo_matches_recorded_evidence(self) -> None:
        live = build_demo_payload()
        recorded = json.loads(
            (ROOT / "evidence" / "authority-boundary-demo.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(live, recorded)
        self.assertEqual(live["verdict"], "PASS")

    def test_output_exposes_no_private_path_or_credential_pattern(self) -> None:
        text = json.dumps(build_demo_payload(), sort_keys=True)
        forbidden = (
            r"[A-Za-z]:\\",
            r"/(?:home|Users|mnt)/",
            r"\b(?:ghp_|github_pat_|sk-)[A-Za-z0-9_-]{16,}",
            r"\b(?:playc|messaoudene)\\",
        )
        for pattern in forbidden:
            self.assertIsNone(re.search(pattern, text, flags=re.IGNORECASE))

    def test_temporary_copies_are_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auec-demo-test-") as parent:
            parent_path = Path(parent)
            payload = build_demo_payload(parent_path)
            self.assertEqual(payload["verdict"], "PASS")
            self.assertEqual(list(parent_path.iterdir()), [])

    def test_concurrent_demonstrations_are_identical(self) -> None:
        with ThreadPoolExecutor(max_workers=4) as pool:
            payloads = list(pool.map(lambda _: build_demo_payload(), range(4)))
        self.assertTrue(all(payload == payloads[0] for payload in payloads[1:]))

    def test_four_thousand_deterministic_safe_observations(self) -> None:
        policy = default_host_policy()
        policy["allowedOps"].remove("hash.sha256")
        claim_manifest = _manifest()
        claim_manifest["nodes"][0]["output"]["epistemic"] = "claim"
        claim_manifest["nodes"][0]["output"]["export"] = False
        action_digest = digest_json({"effect": "notify", "target": "bounded-test-sink"})
        authority_policy = {"allowedEffectClasses": ["pure", "consequential"]}
        fact_request = {
            "epistemicStatus": "fact",
            "independentlyValidated": True,
            "effectClass": "consequential",
            "consentRequired": True,
            "actionDigest": action_digest,
            "consentDigest": action_digest,
        }
        claim_request = {**fact_request, "epistemicStatus": "claim"}

        for _ in range(1000):
            operation = UniversalRuntime(policy).execute(_manifest())
            epistemic = UniversalRuntime().execute(claim_manifest)
            fact = UniversalRuntime().evaluate_authority(fact_request, authority_policy)
            claim = UniversalRuntime().evaluate_authority(
                claim_request, authority_policy
            )
            self.assertEqual(operation["error"]["code"], "E_OPERATION")
            self.assertEqual(epistemic["error"]["code"], "E_EPISTEMIC")
            self.assertTrue(fact["authorized"])
            self.assertFalse(claim["authorized"])


if __name__ == "__main__":
    unittest.main()
