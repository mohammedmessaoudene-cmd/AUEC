# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import copy
import json
import random
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from authority_validator import (  # noqa: E402
    ContractError,
    canonical_json_bytes,
    evaluate_authority,
    load_fixture,
    to_sep3004_record,
    verify_sep3004_record,
)
from composition_demo import build_report  # noqa: E402
from mutation_harness import run_mutations  # noqa: E402


class CompositionTests(unittest.TestCase):
    def test_all_fixtures_match_expected_verdict(self) -> None:
        fixtures = json.loads(
            (ROOT / "fixtures" / "cases.json").read_text(encoding="utf-8")
        )
        for name, definition in fixtures.items():
            with self.subTest(name=name):
                result = evaluate_authority(load_fixture(name))
                self.assertEqual(bool(definition["expectedValid"]), result["valid"])

    def test_six_mutants_turn_red_then_restore(self) -> None:
        results = run_mutations()
        self.assertEqual(6, len(results))
        for result in results:
            self.assertEqual("GREEN", result["baseline"])
            self.assertEqual("RED_EXPECTED", result["mutant"])
            self.assertEqual("GREEN", result["restoration"])

    def test_mutants_leave_no_temporary_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            run_mutations(parent)
            self.assertEqual([], list(parent.iterdir()))

    def test_canonicalization_is_key_order_independent(self) -> None:
        randomizer = random.Random(44045)
        baseline = {"alpha": 1, "beta": {"x": True, "y": ["a", "b"]}, "gamma": None}
        expected = canonical_json_bytes(baseline)
        for _ in range(1000):
            items = list(baseline.items())
            randomizer.shuffle(items)
            self.assertEqual(expected, canonical_json_bytes(dict(items)))

    def test_float_and_non_finite_numbers_are_rejected(self) -> None:
        for value in (1.5, float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value):
                with self.assertRaises(ContractError):
                    canonical_json_bytes({"value": value})

    def test_one_byte_action_change_invalidates_consent(self) -> None:
        request = load_fixture("positive_consequential")
        request["action"]["arguments"]["value"] = "fixturf"
        result = evaluate_authority(request)
        self.assertFalse(result["valid"])
        self.assertEqual("E_CONSENT_DIGEST", result["info"]["reasonCode"])

    def test_policy_narrowing_is_monotonic(self) -> None:
        request = load_fixture("positive_consequential")
        self.assertTrue(evaluate_authority(request)["valid"])
        request["hostPolicy"]["allowedEffects"] = ["read"]
        result = evaluate_authority(request)
        self.assertFalse(result["valid"])
        self.assertEqual("E_HOST_EFFECT", result["info"]["reasonCode"])

    def test_audit_record_never_changes_authority(self) -> None:
        request = load_fixture("positive_pure")
        baseline = evaluate_authority(request)
        request["auditRecord"] = {"event_hash": "sha256:attacker-controlled"}
        with_record = evaluate_authority(request)
        self.assertEqual(baseline["valid"], with_record["valid"])
        self.assertTrue(with_record["info"]["auditInputIgnored"])

    def test_sep3004_mapping_is_post_decision_and_verifiable(self) -> None:
        request = load_fixture("positive_consequential")
        result = evaluate_authority(request)
        record = to_sep3004_record(
            result,
            action=request["action"],
            recorder_context={
                "eventId": "test-event-1",
                "occurredAt": "2026-08-06T00:00:00.000Z",
                "principalId": "test-principal",
                "previousHash": None,
                "purposeDeclared": "test",
            },
        )
        self.assertTrue(verify_sep3004_record(record))
        tampered = copy.deepcopy(record)
        tampered["outcome"] = "denied"
        self.assertFalse(verify_sep3004_record(tampered))

    def test_repeated_and_concurrent_results_are_identical(self) -> None:
        request = load_fixture("positive_authenticated_narrowing")
        expected = evaluate_authority(request)
        for _ in range(1000):
            self.assertEqual(expected, evaluate_authority(request))
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: evaluate_authority(request), range(64)))
        self.assertTrue(all(result == expected for result in results))
        self.assertEqual(1, threading.active_count())

    def test_demo_evidence_matches_live_report(self) -> None:
        expected = json.loads(
            (ROOT / "evidence" / "composition-results.json").read_text(encoding="utf-8")
        )
        self.assertEqual(expected, build_report())

    def test_runtime_has_no_network_or_process_imports(self) -> None:
        source = (ROOT / "authority_validator.py").read_text(encoding="utf-8")
        for marker in (
            "import socket",
            "import urllib",
            "import requests",
            "import subprocess",
            "import os",
            "shell=True",
            "eval(",
            "exec(",
        ):
            self.assertNotIn(marker, source)

    def test_upstream_pins_are_exact(self) -> None:
        pins = json.loads((ROOT / "UPSTREAM_PINS.json").read_text(encoding="utf-8"))
        self.assertEqual(
            "3a2760642010e30037231ef4d7586750b0654e65",
            pins["proposals"]["SEP-2624"]["headSha"],
        )
        self.assertEqual(
            "377f8d260ded5b6854871b2ce3c73621ffcaef1d",
            pins["proposals"]["SEP-3004"]["headSha"],
        )
        self.assertEqual(
            "8fd469a51f6bb58511591474a15f25a56d027bfa",
            pins["proposals"]["SEP-3140"]["headSha"],
        )


if __name__ == "__main__":
    unittest.main()
