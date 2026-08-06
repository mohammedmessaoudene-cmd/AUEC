# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reference-runtime"))

from aiew_uc.canonical import digest_json  # noqa: E402
from aiew_uc.model import default_host_policy  # noqa: E402
from aiew_uc.runtime import UniversalRuntime  # noqa: E402


def manifest_copy() -> dict:
    return json.loads(
        (ROOT / "examples" / "hello_manifest.json").read_text(encoding="utf-8")
    )


def consequential_request(status: str = "fact") -> dict:
    action_digest = digest_json({"effect": "notify", "target": "bounded-test-sink"})
    return {
        "epistemicStatus": status,
        "independentlyValidated": True,
        "effectClass": "consequential",
        "consentRequired": True,
        "actionDigest": action_digest,
        "consentDigest": action_digest,
    }


class CoreSemanticCausalControls(unittest.TestCase):
    def test_nc_sem_01_host_allowlist_blocks_requested_operation(self) -> None:
        policy = default_host_policy()
        policy["allowedOps"].remove("hash.sha256")
        result = UniversalRuntime(policy).execute(manifest_copy())
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["error"]["code"], "E_OPERATION")

    def test_nc_sem_02_u0_claim_output_is_rejected(self) -> None:
        manifest = manifest_copy()
        manifest["nodes"][0]["output"]["epistemic"] = "claim"
        manifest["nodes"][0]["output"]["export"] = False
        result = UniversalRuntime().execute(manifest)
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["error"]["code"], "E_EPISTEMIC")

    def test_nc_sem_03_claim_never_authorizes_consequential_effect(self) -> None:
        policy = {"allowedEffectClasses": ["pure", "consequential"]}
        decision = UniversalRuntime().evaluate_authority(
            consequential_request("claim"),
            policy,
        )
        self.assertFalse(decision["authorized"])
        self.assertIn("E_AUTHORITY_EPISTEMIC", decision["reasons"])

    def test_authority_predicate_accepts_bounded_positive_case(self) -> None:
        policy = {"allowedEffectClasses": ["pure", "consequential"]}
        decision = UniversalRuntime().evaluate_authority(
            consequential_request("fact"),
            policy,
        )
        self.assertTrue(decision["authorized"])
        self.assertEqual(decision["reasons"], [])

    def test_authority_predicate_requires_independent_validation(self) -> None:
        request = consequential_request("fact")
        request["independentlyValidated"] = False
        decision = UniversalRuntime().evaluate_authority(
            request,
            {"allowedEffectClasses": ["consequential"]},
        )
        self.assertFalse(decision["authorized"])
        self.assertIn("E_AUTHORITY_VALIDATION", decision["reasons"])

    def test_authority_predicate_binds_consent_to_action_digest(self) -> None:
        request = consequential_request("fact")
        request["consentDigest"] = digest_json({"different": True})
        decision = UniversalRuntime().evaluate_authority(
            request,
            {"allowedEffectClasses": ["consequential"]},
        )
        self.assertFalse(decision["authorized"])
        self.assertIn("E_AUTHORITY_CONSENT", decision["reasons"])

    def test_authority_predicate_respects_host_effect_policy(self) -> None:
        decision = UniversalRuntime().evaluate_authority(
            consequential_request("fact"),
            {"allowedEffectClasses": ["pure"]},
        )
        self.assertFalse(decision["authorized"])
        self.assertIn("E_AUTHORITY_EFFECT", decision["reasons"])


if __name__ == "__main__":
    unittest.main()
