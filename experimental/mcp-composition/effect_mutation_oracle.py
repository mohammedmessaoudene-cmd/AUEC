# SPDX-License-Identifier: Apache-2.0
"""Focused safety oracles for private effect-lifecycle source mutations."""

from __future__ import annotations

import argparse
import json

from effect_lifecycle import (
    AuthorityDecision,
    EffectAttempt,
    EffectContractError,
    EffectObservation,
    IdempotencyRegistry,
    ReconciliationRecord,
    digest_dataclass,
    digest_idempotency_key,
    digest_value,
    retry_directive,
)


AUTH = frozenset({"provider:test", "system-of-record:test"})


def decision(verdict: str = "allowed") -> AuthorityDecision:
    return AuthorityDecision(
        decision_id="decision-1",
        operation_id="operation-1",
        decision_evidence_digest=digest_value("decision-evidence"),
        action_digest=digest_value("action"),
        principal_id="principal-1",
        verdict=verdict,
        decision_authority_id="authority-1",
        boundary_emitter_id="boundary-1",
    )


def attempt(
    *, verdict: str = "allowed", payload: str = "payload"
) -> tuple[AuthorityDecision, EffectAttempt]:
    d = decision(verdict)
    return d, EffectAttempt(
        operation_id="operation-1",
        attempt_id="attempt-1",
        decision_evidence_digest=d.decision_evidence_digest,
        action_digest=d.action_digest,
        payload_digest=digest_value(payload),
        principal_id=d.principal_id,
        boundary_emitter_id=d.boundary_emitter_id,
        dispatch_state="attempted",
        attempted_at="2026-08-12T04:00:00.000Z",
        idempotency_key_digest=digest_idempotency_key("key-1"),
        idempotency_scope="provider:test",
    )


def observation(
    a: EffectAttempt,
    disposition: str,
    basis: str,
    observer: str,
    *,
    observation_id: str = "observation-1",
) -> EffectObservation:
    return EffectObservation(
        observation_id=observation_id,
        operation_id=a.operation_id,
        attempt_id=a.attempt_id,
        decision_evidence_digest=a.decision_evidence_digest,
        action_digest=a.action_digest,
        payload_digest=a.payload_digest,
        principal_id=a.principal_id,
        disposition=disposition,
        observation_basis=basis,
        observer_id=observer,
        observed_at="2026-08-12T04:00:01.000Z",
        provider_effect_ref=(
            "provider-ref:1" if disposition == "confirmed_occurred" else None
        ),
    )


def rejected(operation) -> bool:
    try:
        operation()
    except EffectContractError:
        return True
    return False


def run(oracle: str) -> bool:
    if oracle == "terminal-authority":
        d, a = attempt()
        item = observation(a, "confirmed_occurred", "provider_response", "local:test")
        return rejected(
            lambda: item.validate_against(d, a, authoritative_observer_ids=AUTH)
        )
    if oracle == "denied-dispatch":
        d, a = attempt(verdict="denied")
        return rejected(lambda: a.validate_against(d))
    if oracle == "key-payload":
        _, first = attempt(payload="payload-a")
        _, second_unbound = attempt(payload="payload-b")
        second = EffectAttempt(**{**second_unbound.__dict__, "attempt_id": "attempt-2"})
        registry = IdempotencyRegistry()
        registry.register(first)
        return rejected(lambda: registry.register(second))
    if oracle == "terminal-rewrite":
        d, a = attempt()
        previous = observation(
            a, "confirmed_occurred", "provider_response", "provider:test"
        )
        newer = observation(
            a,
            "confirmed_absent",
            "system_of_record_query",
            "system-of-record:test",
            observation_id="observation-2",
        )
        record = ReconciliationRecord(
            reconciliation_id="reconciliation-1",
            previous_observation_digest=digest_dataclass(previous),
            operation_id=a.operation_id,
            attempt_id=a.attempt_id,
            decision_evidence_digest=a.decision_evidence_digest,
            action_digest=a.action_digest,
            payload_digest=a.payload_digest,
            principal_id=a.principal_id,
            appended_at="2026-08-12T04:01:00.000Z",
            observation=newer,
        )
        return rejected(
            lambda: record.validate_against(
                previous, d, a, authoritative_observer_ids=AUTH
            )
        )
    if oracle == "blind-retry":
        _, a = attempt()
        unknown = observation(a, "outcome_unknown", "local_timeout", "local:test")
        return (
            retry_directive(
                a,
                unknown,
                effect_class="irreversible",
                candidate_attempt=EffectAttempt(
                    **{**a.__dict__, "attempt_id": "attempt-2"}
                ),
            )
            == "RECONCILIATION_REQUIRED_NO_BLIND_RETRY"
        )
    if oracle == "append-link":
        d, a = attempt()
        previous = observation(a, "outcome_unknown", "local_timeout", "local:test")
        newer = observation(
            a,
            "confirmed_occurred",
            "provider_response",
            "provider:test",
            observation_id="observation-2",
        )
        record = ReconciliationRecord(
            reconciliation_id="reconciliation-1",
            previous_observation_digest=digest_value("wrong-link"),
            operation_id=a.operation_id,
            attempt_id=a.attempt_id,
            decision_evidence_digest=a.decision_evidence_digest,
            action_digest=a.action_digest,
            payload_digest=a.payload_digest,
            principal_id=a.principal_id,
            appended_at="2026-08-12T04:01:00.000Z",
            observation=newer,
        )
        return rejected(
            lambda: record.validate_against(
                previous, d, a, authoritative_observer_ids=AUTH
            )
        )
    raise ValueError(f"unknown oracle: {oracle}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--oracle", required=True)
    args = parser.parse_args()
    print(json.dumps({"oracle": args.oracle, "safe": run(args.oracle)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
