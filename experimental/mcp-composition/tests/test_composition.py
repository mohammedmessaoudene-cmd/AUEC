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
    ActionBoundaryEmitter,
    ContractError,
    DEFAULT_CONTEXT,
    authority_delta,
    canonical_json_bytes,
    digest_json,
    evaluate_authority,
    intersect_authority,
    load_fixture,
    normalize_authority,
    to_sep3004_record,
    validate_authority_relation,
    verify_decision_evidence,
    verify_sep3004_record,
)
from adversarial_harness import run_adversarial  # noqa: E402
from composition_demo import build_report  # noqa: E402
from field_tribunal import assess_field_gap  # noqa: E402
from mutation_harness import run_mutations  # noqa: E402
from sep3004_cleanroom import (  # noqa: E402
    Sep3004Error,
    canonical_preimage,
    qualify_producer_trust,
)
from sep3004_vectors import KAT_HASH_2X, REC_BOTH, run_vectors  # noqa: E402


class CompositionTests(unittest.TestCase):
    def test_all_fixtures_match_expected_verdict(self) -> None:
        fixtures = json.loads(
            (ROOT / "fixtures" / "cases.json").read_text(encoding="utf-8")
        )
        for name, definition in fixtures.items():
            with self.subTest(name=name):
                result = evaluate_authority(load_fixture(name))
                self.assertEqual(bool(definition["expectedValid"]), result["valid"])

    def test_thirteen_mutants_turn_red_then_restore(self) -> None:
        results = run_mutations()
        self.assertEqual(13, len(results))
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

    def test_decision_evidence_carries_full_basis(self) -> None:
        result = evaluate_authority(load_fixture("positive_consequential"))
        evidence = result["decisionEvidence"]
        self.assertEqual("auec.authority-decision-evidence.v0", evidence["schema"])
        self.assertEqual(
            DEFAULT_CONTEXT.decision_authority_id, evidence["decisionAuthorityId"]
        )
        self.assertEqual(DEFAULT_CONTEXT.record_emitter_id, evidence["recordEmitterId"])
        self.assertEqual(DEFAULT_CONTEXT.principal_id, evidence["principalId"])
        self.assertEqual(DEFAULT_CONTEXT.policy_id, evidence["policy"]["id"])
        self.assertEqual(DEFAULT_CONTEXT.policy_version, evidence["policy"]["version"])
        self.assertEqual("allowed", evidence["verdict"])
        self.assertEqual(["ALLOW_HOST_POLICY"], evidence["reasonCodes"])
        verify_decision_evidence(evidence)

    def test_budget_and_placement_authority_are_monotonic(self) -> None:
        requested = normalize_authority(
            {
                "capabilities": ["read"],
                "effects": ["read"],
                "egress": ["none"],
                "placements": ["local", "edge"],
                "budgets": {"nodes": 10, "outputs": 8, "wallMs": 1000},
            }
        )
        host = normalize_authority(
            {
                "capabilities": ["read"],
                "effects": ["read"],
                "egress": ["none"],
                "placements": ["local"],
                "budgets": {"nodes": 4, "outputs": 8, "wallMs": 750},
            }
        )
        effective = intersect_authority(requested, host)
        validate_authority_relation(requested, host, effective)
        delta = authority_delta(requested, effective)
        self.assertEqual(["edge"], delta["removed"]["placements"])
        self.assertEqual(
            {"requested": 10, "effective": 4},
            delta["reducedBudgets"]["nodes"],
        )
        self.assertEqual(
            {"requested": 1000, "effective": 750},
            delta["reducedBudgets"]["wallMs"],
        )

    def test_inconsistent_delta_and_widening_are_rejected(self) -> None:
        result = evaluate_authority(load_fixture("positive_pure"))
        evidence = copy.deepcopy(result["decisionEvidence"])
        evidence["delta"] = {"removed": {}, "reducedBudgets": {}}
        with self.assertRaises(ContractError):
            verify_decision_evidence(evidence)
        evidence = copy.deepcopy(result["decisionEvidence"])
        evidence["effective"]["capabilities"] = ["administrator"]
        with self.assertRaises(ContractError):
            verify_decision_evidence(evidence)

    def test_policy_revision_is_committed(self) -> None:
        result = evaluate_authority(load_fixture("positive_pure"))
        original = result["decisionEvidence"]
        changed = copy.deepcopy(original)
        changed["policy"]["version"] = "2026-08-08-rev2"
        verify_decision_evidence(changed)
        self.assertNotEqual(digest_json(original), digest_json(changed))

    def test_boundary_rejects_wrong_action_principal_emitter_and_outcome(self) -> None:
        request = load_fixture("positive_pure")
        result = evaluate_authority(request)
        context = {
            "eventId": "boundary-test-1",
            "occurredAt": "2026-08-08T00:00:03.000Z",
            "previousHash": None,
            "purposeDeclared": "boundary negative cases",
        }
        emitter = ActionBoundaryEmitter(DEFAULT_CONTEXT.record_emitter_id)
        cases = (
            lambda: emitter.emit(
                result,
                observed_action={**request["action"], "tool": "changed"},
                observed_principal_id=DEFAULT_CONTEXT.principal_id,
                actual_outcome="allowed",
                recorder_context=context,
            ),
            lambda: emitter.emit(
                result,
                observed_action=request["action"],
                observed_principal_id="principal:changed",
                actual_outcome="allowed",
                recorder_context=context,
            ),
            lambda: ActionBoundaryEmitter("emitter:changed").emit(
                result,
                observed_action=request["action"],
                observed_principal_id=DEFAULT_CONTEXT.principal_id,
                actual_outcome="allowed",
                recorder_context=context,
            ),
            lambda: emitter.emit(
                result,
                observed_action=request["action"],
                observed_principal_id=DEFAULT_CONTEXT.principal_id,
                actual_outcome="denied",
                recorder_context=context,
            ),
        )
        for operation in cases:
            with self.subTest(operation=operation):
                with self.assertRaises(ContractError):
                    operation()

    def test_caller_cannot_set_decider_or_emitter_identity(self) -> None:
        for field in (
            "decisionAuthorityId",
            "recordEmitterId",
            "principalId",
            "decidedAt",
        ):
            request = load_fixture("positive_pure")
            request[field] = "attacker-controlled"
            result = evaluate_authority(request)
            self.assertFalse(result["valid"])
            self.assertEqual("E_UNKNOWN_CRITICAL_FIELD", result["info"]["reasonCode"])
            self.assertEqual(
                DEFAULT_CONTEXT.decision_authority_id,
                result["decisionEvidence"]["decisionAuthorityId"],
            )

    def test_current_and_candidate_registry_boundaries_are_explicit(self) -> None:
        assessment = assess_field_gap()
        self.assertEqual("PASS", assessment["status"])
        self.assertTrue(assessment["currentRecordsConformant"])
        self.assertTrue(assessment["currentRecordHashesEqual"])
        self.assertTrue(assessment["decisionEvidenceDigestsDiffer"])
        self.assertTrue(assessment["candidateRecordHashesDiffer"])
        self.assertTrue(assessment["candidateRejectedByCurrentRegistry"])
        self.assertEqual(
            ["decision_evidence_hash"],
            [field["name"] for field in assessment["minimalCandidateFields"]],
        )

    def test_published_sep3004_vectors_and_kat(self) -> None:
        report = run_vectors()
        self.assertEqual("PASS", report["status"])
        self.assertEqual((23, 0), (report["passed"], report["failed"]))
        self.assertEqual(KAT_HASH_2X, report["kat"]["observed"])
        self.assertEqual(KAT_HASH_2X, REC_BOTH["event_hash"])

    def test_sep3004_unicode_rules_are_precise(self) -> None:
        ascii_space = copy.deepcopy(REC_BOTH)
        ascii_space["tool_name"] = " export "
        self.assertEqual(canonical_preimage(REC_BOTH), canonical_preimage(ascii_space))
        nbsp = copy.deepcopy(REC_BOTH)
        nbsp["tool_name"] = "\u00a0export\u00a0"
        self.assertNotEqual(canonical_preimage(REC_BOTH), canonical_preimage(nbsp))
        control = copy.deepcopy(REC_BOTH)
        control["tool_name"] = "export\t"
        with self.assertRaises(Sep3004Error):
            canonical_preimage(control)

    def test_self_attested_is_not_independent_proof(self) -> None:
        self.assertEqual("self_attested", qualify_producer_trust())
        self.assertEqual(
            "authenticated", qualify_producer_trust(authenticated_identity=True)
        )
        self.assertEqual(
            "externally_anchored",
            qualify_producer_trust(
                authenticated_identity=True, external_anchor_verified=True
            ),
        )
        report = run_adversarial(100)
        self.assertFalse(report["independentProducerTruthEstablished"])
        self.assertEqual("PASS", report["status"])

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
        self.assertNotIn(
            "import socket", (ROOT / "sep3004_cleanroom.py").read_text(encoding="utf-8")
        )

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
