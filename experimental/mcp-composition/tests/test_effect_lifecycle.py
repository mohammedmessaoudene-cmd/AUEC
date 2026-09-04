# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import copy
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from authority_validator import evaluate_authority, load_fixture  # noqa: E402
from effect_lifecycle import (  # noqa: E402
    AuthorityDecision,
    EffectAttempt,
    EffectContractError,
    EffectObservation,
    IdempotencyRegistry,
    ReconciliationRecord,
    candidate_effect_projection,
    digest_dataclass,
    digest_idempotency_key,
    digest_value,
    retry_directive,
    verify_reconciliation_chain,
)
from effect_mutation_harness import run_effect_mutations  # noqa: E402
from effect_stress import run_effect_stress  # noqa: E402


AUTHORITATIVE = frozenset({"provider:test", "system-of-record:test"})


class EffectLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        request = load_fixture("positive_consequential")
        result = evaluate_authority(request)
        self.assertTrue(result["valid"])
        self.decision = AuthorityDecision.from_validation_result(
            result,
            operation_id="operation-order-777",
        )
        self.payload_digest = digest_value(request["action"]["arguments"])
        self.key_digest = digest_idempotency_key("private-test-key")

    def attempt(
        self,
        *,
        attempt_id: str = "attempt-0001",
        operation_id: str = "operation-order-777",
        dispatch_state: str = "attempted",
        payload_digest: str | None = None,
        action_digest: str | None = None,
        decision_evidence_digest: str | None = None,
        principal_id: str | None = None,
        boundary_emitter_id: str | None = None,
        key_digest: str | None = "DEFAULT",
        key_scope: str | None = "provider:test-account",
    ) -> EffectAttempt:
        if key_digest == "DEFAULT":
            key_digest = self.key_digest
        return EffectAttempt(
            operation_id=operation_id,
            attempt_id=attempt_id,
            decision_evidence_digest=(
                decision_evidence_digest or self.decision.decision_evidence_digest
            ),
            action_digest=action_digest or self.decision.action_digest,
            payload_digest=payload_digest or self.payload_digest,
            principal_id=principal_id or self.decision.principal_id,
            boundary_emitter_id=(
                boundary_emitter_id or self.decision.boundary_emitter_id
            ),
            dispatch_state=dispatch_state,
            attempted_at=(
                "2026-08-12T04:00:00.000Z" if dispatch_state == "attempted" else None
            ),
            idempotency_key_digest=key_digest,
            idempotency_scope=key_scope if key_digest is not None else None,
        )

    def observation(
        self,
        attempt: EffectAttempt,
        disposition: str,
        basis: str | None,
        *,
        observation_id: str = "observation-0001",
        observer_id: str | None = "local-boundary:test",
        provider_effect_ref: str | None = None,
    ) -> EffectObservation:
        no_attempt = disposition == "not_attempted"
        return EffectObservation(
            observation_id=observation_id,
            operation_id=attempt.operation_id,
            attempt_id=attempt.attempt_id,
            decision_evidence_digest=attempt.decision_evidence_digest,
            action_digest=attempt.action_digest,
            payload_digest=attempt.payload_digest,
            principal_id=attempt.principal_id,
            disposition=disposition,
            observation_basis=None if no_attempt else basis,
            observer_id=None if no_attempt else observer_id,
            observed_at=None if no_attempt else "2026-08-12T04:00:01.000Z",
            provider_effect_ref=provider_effect_ref,
        )

    def reconciliation(
        self,
        previous: EffectObservation,
        newer: EffectObservation,
        attempt: EffectAttempt,
    ) -> ReconciliationRecord:
        return ReconciliationRecord(
            reconciliation_id="reconciliation-0001",
            previous_observation_digest=digest_dataclass(previous),
            operation_id=attempt.operation_id,
            attempt_id=attempt.attempt_id,
            decision_evidence_digest=attempt.decision_evidence_digest,
            action_digest=attempt.action_digest,
            payload_digest=attempt.payload_digest,
            principal_id=attempt.principal_id,
            appended_at="2026-08-12T04:01:00.000Z",
            observation=newer,
        )

    def test_decision_allowed_plus_outcome_unknown_is_valid(self) -> None:
        attempt = self.attempt()
        observation = self.observation(attempt, "outcome_unknown", "local_timeout")
        observation.validate_against(self.decision, attempt)

    def test_not_attempted_is_explicit(self) -> None:
        attempt = self.attempt(dispatch_state="not_attempted")
        observation = self.observation(attempt, "not_attempted", None)
        observation.validate_against(self.decision, attempt)
        self.assertEqual(
            "ATTEMPT_ALLOWED",
            retry_directive(attempt, observation, effect_class="irreversible"),
        )

    def test_timeout_cannot_mean_confirmed_absent(self) -> None:
        attempt = self.attempt()
        observation = self.observation(
            attempt,
            "confirmed_absent",
            "local_timeout",
            observer_id="provider:test",
        )
        with self.assertRaises(EffectContractError):
            observation.validate_against(
                self.decision,
                attempt,
                authoritative_observer_ids=AUTHORITATIVE,
            )

    def test_terminal_state_requires_configured_authoritative_observer(self) -> None:
        attempt = self.attempt()
        observation = self.observation(
            attempt,
            "confirmed_occurred",
            "provider_response",
            observer_id="local-boundary:test",
            provider_effect_ref="provider-ref:charge-1",
        )
        with self.assertRaises(EffectContractError):
            observation.validate_against(
                self.decision,
                attempt,
                authoritative_observer_ids=AUTHORITATIVE,
            )

    def test_provider_can_confirm_occurrence(self) -> None:
        attempt = self.attempt()
        observation = self.observation(
            attempt,
            "confirmed_occurred",
            "provider_response",
            observer_id="provider:test",
            provider_effect_ref="provider-ref:charge-1",
        )
        observation.validate_against(
            self.decision,
            attempt,
            authoritative_observer_ids=AUTHORITATIVE,
        )

    def test_system_of_record_can_confirm_absence_without_effect_handle(self) -> None:
        attempt = self.attempt()
        observation = self.observation(
            attempt,
            "confirmed_absent",
            "system_of_record_query",
            observer_id="system-of-record:test",
        )
        observation.validate_against(
            self.decision,
            attempt,
            authoritative_observer_ids=AUTHORITATIVE,
        )

    def test_confirmed_absence_rejects_provider_effect_reference(self) -> None:
        attempt = self.attempt()
        observation = self.observation(
            attempt,
            "confirmed_absent",
            "system_of_record_query",
            observer_id="system-of-record:test",
            provider_effect_ref="provider-ref:contradiction",
        )
        with self.assertRaises(EffectContractError):
            observation.validate_against(
                self.decision,
                attempt,
                authoritative_observer_ids=AUTHORITATIVE,
            )

    def test_confirmed_occurrence_requires_provider_reference(self) -> None:
        attempt = self.attempt()
        observation = self.observation(
            attempt,
            "confirmed_occurred",
            "provider_response",
            observer_id="provider:test",
        )
        with self.assertRaises(EffectContractError):
            observation.validate_against(
                self.decision,
                attempt,
                authoritative_observer_ids=AUTHORITATIVE,
            )

    def test_denied_decision_cannot_be_dispatched(self) -> None:
        denied_result = evaluate_authority(load_fixture("denied_claim"))
        denied = AuthorityDecision.from_validation_result(
            denied_result,
            operation_id="operation-order-777",
        )
        attempted = copy.copy(self.attempt())
        attempted = EffectAttempt(
            **{
                **attempted.__dict__,
                "decision_evidence_digest": denied.decision_evidence_digest,
                "action_digest": denied.action_digest,
                "principal_id": denied.principal_id,
                "boundary_emitter_id": denied.boundary_emitter_id,
            }
        )
        with self.assertRaises(EffectContractError):
            attempted.validate_against(denied)

    def test_decision_action_principal_and_emitter_substitution_rejected(self) -> None:
        changes = (
            {"decision_evidence_digest": digest_value("wrong")},
            {"action_digest": digest_value("wrong")},
            {"principal_id": "principal:attacker"},
            {"boundary_emitter_id": "boundary:attacker"},
        )
        for change in changes:
            with self.subTest(change=change):
                attempt = EffectAttempt(**{**self.attempt().__dict__, **change})
                with self.assertRaises(EffectContractError):
                    attempt.validate_against(self.decision)

    def test_operation_id_is_stable_and_attempt_ids_are_distinct(self) -> None:
        first = self.attempt(attempt_id="attempt-1")
        second = self.attempt(attempt_id="attempt-2")
        self.assertEqual(first.operation_id, second.operation_id)
        self.assertNotEqual(first.attempt_id, second.attempt_id)

    def test_same_key_same_contract_is_replay(self) -> None:
        registry = IdempotencyRegistry()
        self.assertEqual("BOUND_NEW", registry.register(self.attempt(attempt_id="a1")))
        self.assertEqual(
            "BOUND_REPLAY", registry.register(self.attempt(attempt_id="a2"))
        )

    def test_same_key_different_payload_rejected(self) -> None:
        registry = IdempotencyRegistry()
        registry.register(self.attempt(attempt_id="a1"))
        with self.assertRaises(EffectContractError):
            registry.register(
                self.attempt(attempt_id="a2", payload_digest=digest_value("changed"))
            )

    def test_same_key_different_action_rejected(self) -> None:
        registry = IdempotencyRegistry()
        registry.register(self.attempt(attempt_id="a1"))
        with self.assertRaises(EffectContractError):
            registry.register(
                self.attempt(attempt_id="a2", action_digest=digest_value("changed"))
            )

    def test_same_key_different_operation_rejected(self) -> None:
        registry = IdempotencyRegistry()
        registry.register(self.attempt(attempt_id="a1"))
        with self.assertRaises(EffectContractError):
            registry.register(
                self.attempt(attempt_id="a2", operation_id="operation-other")
            )

    def test_registry_snapshot_contains_no_raw_idempotency_key(self) -> None:
        registry = IdempotencyRegistry()
        registry.register(self.attempt())
        snapshot = repr(registry.snapshot())
        self.assertNotIn("private-test-key", snapshot)
        self.assertIn(self.key_digest, snapshot)

    def test_blind_retry_of_unknown_irreversible_effect_is_rejected(self) -> None:
        attempt = self.attempt(attempt_id="a1")
        observation = self.observation(attempt, "outcome_unknown", "transport_error")
        self.assertEqual(
            "RECONCILIATION_REQUIRED_NO_BLIND_RETRY",
            retry_directive(
                attempt,
                observation,
                effect_class="irreversible",
                candidate_attempt=self.attempt(attempt_id="a2"),
            ),
        )

    def test_idempotent_retry_requires_same_key_and_contract(self) -> None:
        attempt = self.attempt(attempt_id="a1")
        observation = self.observation(attempt, "outcome_unknown", "transport_error")
        self.assertEqual(
            "RETRY_SAME_IDEMPOTENCY_KEY_AND_CONTRACT_ONLY",
            retry_directive(
                attempt,
                observation,
                effect_class="idempotent",
                candidate_attempt=self.attempt(attempt_id="a2"),
            ),
        )

    def test_idempotency_retention_expired_requires_reconciliation(self) -> None:
        attempt = self.attempt(attempt_id="a1")
        observation = self.observation(attempt, "outcome_unknown", "transport_error")
        self.assertEqual(
            "RECONCILIATION_REQUIRED_NO_BLIND_RETRY",
            retry_directive(
                attempt,
                observation,
                effect_class="idempotent",
                candidate_attempt=self.attempt(attempt_id="a2"),
                key_retention_valid=False,
            ),
        )

    def test_lost_response_after_provider_commit_reconciles_to_occurred(self) -> None:
        attempt = self.attempt()
        unknown = self.observation(attempt, "outcome_unknown", "local_timeout")
        occurred = self.observation(
            attempt,
            "confirmed_occurred",
            "system_of_record_query",
            observation_id="observation-0002",
            observer_id="system-of-record:test",
            provider_effect_ref="provider-ref:charge-1",
        )
        record = self.reconciliation(unknown, occurred, attempt)
        final = verify_reconciliation_chain(
            unknown,
            [record],
            self.decision,
            attempt,
            authoritative_observer_ids=AUTHORITATIVE,
        )
        self.assertEqual("confirmed_occurred", final.disposition)

    def test_lost_response_before_provider_receives_reconciles_to_absent(self) -> None:
        attempt = self.attempt()
        unknown = self.observation(attempt, "outcome_unknown", "transport_error")
        absent = self.observation(
            attempt,
            "confirmed_absent",
            "system_of_record_query",
            observation_id="observation-0002",
            observer_id="system-of-record:test",
        )
        record = self.reconciliation(unknown, absent, attempt)
        final = verify_reconciliation_chain(
            unknown,
            [record],
            self.decision,
            attempt,
            authoritative_observer_ids=AUTHORITATIVE,
        )
        self.assertEqual("confirmed_absent", final.disposition)

    def test_provider_pending_handle_remains_unknown(self) -> None:
        attempt = self.attempt()
        pending = self.observation(
            attempt,
            "outcome_unknown",
            "provider_pending",
            provider_effect_ref="provider-ref:pending-1",
        )
        pending.validate_against(self.decision, attempt)

    def test_terminal_state_cannot_be_rewritten(self) -> None:
        attempt = self.attempt()
        occurred = self.observation(
            attempt,
            "confirmed_occurred",
            "provider_response",
            observer_id="provider:test",
            provider_effect_ref="provider-ref:charge-1",
        )
        absent = self.observation(
            attempt,
            "confirmed_absent",
            "system_of_record_query",
            observation_id="observation-0002",
            observer_id="system-of-record:test",
        )
        record = self.reconciliation(occurred, absent, attempt)
        with self.assertRaises(EffectContractError):
            record.validate_against(
                occurred,
                self.decision,
                attempt,
                authoritative_observer_ids=AUTHORITATIVE,
            )

    def test_reconciliation_requires_exact_prior_digest(self) -> None:
        attempt = self.attempt()
        unknown = self.observation(attempt, "outcome_unknown", "local_timeout")
        occurred = self.observation(
            attempt,
            "confirmed_occurred",
            "provider_response",
            observation_id="observation-0002",
            observer_id="provider:test",
            provider_effect_ref="provider-ref:charge-1",
        )
        record = ReconciliationRecord(
            **{
                **self.reconciliation(unknown, occurred, attempt).__dict__,
                "previous_observation_digest": digest_value("removed-or-reordered"),
            }
        )
        with self.assertRaises(EffectContractError):
            verify_reconciliation_chain(
                unknown,
                [record],
                self.decision,
                attempt,
                authoritative_observer_ids=AUTHORITATIVE,
            )

    def test_reconciliation_rejects_reused_ids(self) -> None:
        attempt = self.attempt()
        unknown = self.observation(attempt, "outcome_unknown", "local_timeout")
        occurred = self.observation(
            attempt,
            "confirmed_occurred",
            "provider_response",
            observation_id="observation-0002",
            observer_id="provider:test",
            provider_effect_ref="provider-ref:charge-1",
        )
        valid = self.reconciliation(unknown, occurred, attempt)
        cases = (
            {"reconciliation_id": unknown.observation_id},
            {
                "observation": EffectObservation(
                    **{**occurred.__dict__, "observation_id": unknown.observation_id}
                )
            },
            {
                "observation": EffectObservation(
                    **{**occurred.__dict__, "observation_id": valid.reconciliation_id}
                )
            },
        )
        for change in cases:
            with self.subTest(change=change):
                record = ReconciliationRecord(**{**valid.__dict__, **change})
                with self.assertRaises(EffectContractError):
                    record.validate_against(
                        unknown,
                        self.decision,
                        attempt,
                        authoritative_observer_ids=AUTHORITATIVE,
                    )

    def test_reconciliation_timestamps_are_monotone(self) -> None:
        attempt = self.attempt()
        unknown = self.observation(attempt, "outcome_unknown", "local_timeout")
        occurred = self.observation(
            attempt,
            "confirmed_occurred",
            "provider_response",
            observation_id="observation-0002",
            observer_id="provider:test",
            provider_effect_ref="provider-ref:charge-1",
        )
        valid = self.reconciliation(unknown, occurred, attempt)
        bad_append = ReconciliationRecord(
            **{**valid.__dict__, "appended_at": unknown.observed_at}
        )
        with self.assertRaises(EffectContractError):
            bad_append.validate_against(
                unknown,
                self.decision,
                attempt,
                authoritative_observer_ids=AUTHORITATIVE,
            )
        future_observation = EffectObservation(
            **{**occurred.__dict__, "observed_at": "2026-08-12T04:02:00.000Z"}
        )
        before_evidence = ReconciliationRecord(
            **{**valid.__dict__, "observation": future_observation}
        )
        with self.assertRaises(EffectContractError):
            before_evidence.validate_against(
                unknown,
                self.decision,
                attempt,
                authoritative_observer_ids=AUTHORITATIVE,
            )

    def test_emitter_crash_and_audit_append_failure_remain_unknown(self) -> None:
        attempt = self.attempt()
        for basis in ("emitter_crash", "audit_append_failure"):
            with self.subTest(basis=basis):
                observation = self.observation(attempt, "outcome_unknown", basis)
                observation.validate_against(self.decision, attempt)

    def test_confirmed_occurrence_prevents_double_charge(self) -> None:
        attempt = self.attempt()
        occurred = self.observation(
            attempt,
            "confirmed_occurred",
            "provider_response",
            observer_id="provider:test",
            provider_effect_ref="provider-ref:charge-1",
        )
        occurred.validate_against(
            self.decision,
            attempt,
            authoritative_observer_ids=AUTHORITATIVE,
        )
        self.assertEqual(
            "REPLAY_CONFIRMED_RESULT_NO_REEXECUTION",
            retry_directive(attempt, occurred, effect_class="irreversible"),
        )

    def test_concurrent_identical_bindings_collapse_to_one_new_binding(self) -> None:
        registry = IdempotencyRegistry()

        def bind(index: int) -> str:
            return registry.register(self.attempt(attempt_id=f"attempt-{index:04d}"))

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(bind, range(500)))
        self.assertEqual(1, results.count("BOUND_NEW"))
        self.assertEqual(499, results.count("BOUND_REPLAY"))
        self.assertEqual(1, len(registry.snapshot()))

    def test_candidate_projection_separates_three_post_dispatch_states(self) -> None:
        attempt = self.attempt()
        observations = (
            self.observation(attempt, "outcome_unknown", "local_timeout"),
            self.observation(
                attempt,
                "confirmed_occurred",
                "provider_response",
                observer_id="provider:test",
                provider_effect_ref="provider-ref:charge-1",
            ),
            self.observation(
                attempt,
                "confirmed_absent",
                "system_of_record_query",
                observer_id="system-of-record:test",
            ),
        )
        projections = [
            candidate_effect_projection(
                self.decision,
                attempt,
                item,
                authoritative_observer_ids=AUTHORITATIVE,
            )
            for item in observations
        ]
        self.assertEqual(3, len({repr(item) for item in projections}))
        self.assertTrue(
            all(
                item["registration_status"] == "UNREGISTERED_PRIVATE_CANDIDATE"
                for item in projections
            )
        )

    def test_decision_authority_and_effect_observer_remain_distinct(self) -> None:
        attempt = self.attempt()
        observation = self.observation(
            attempt,
            "confirmed_occurred",
            "provider_response",
            observer_id="provider:test",
            provider_effect_ref="provider-ref:charge-1",
        )
        self.assertNotEqual(
            self.decision.decision_authority_id, observation.observer_id
        )

    def test_six_effect_mutants_turn_red_then_restore(self) -> None:
        results = run_effect_mutations()
        self.assertEqual(6, len(results))
        for item in results:
            with self.subTest(mutation=item["mutation"]):
                self.assertEqual("GREEN", item["baseline"])
                self.assertEqual("RED_EXPECTED", item["mutant"])
                self.assertEqual("GREEN", item["restoration"])

    def test_effect_stress_has_one_binding_and_no_conflict_acceptance(self) -> None:
        result = run_effect_stress(iterations=1_000, workers=8)
        self.assertEqual("PASS", result["status"])
        self.assertEqual(1, result["newBindings"])
        self.assertEqual(999, result["safeReplays"])
        self.assertEqual(100, result["payloadConflictsRejected"])
        self.assertEqual(0, result["unexpectedAccepted"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
