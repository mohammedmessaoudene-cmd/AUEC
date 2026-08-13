# SPDX-License-Identifier: Apache-2.0
"""Deterministic, effect-free concurrency stress for the private lifecycle."""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from authority_validator import evaluate_authority, load_fixture
from effect_lifecycle import (
    AuthorityDecision,
    EffectAttempt,
    EffectContractError,
    EffectObservation,
    IdempotencyRegistry,
    digest_idempotency_key,
    digest_value,
)


def run_effect_stress(iterations: int = 10_000, workers: int = 8) -> dict[str, Any]:
    if iterations < 1 or workers < 1:
        raise ValueError("iterations and workers must be positive")
    request = load_fixture("positive_consequential")
    decision = AuthorityDecision.from_validation_result(
        evaluate_authority(request),
        operation_id="operation-stress-1",
    )
    payload_digest = digest_value(request["action"]["arguments"])
    key_digest = digest_idempotency_key("stress-key-never-stored")
    registry = IdempotencyRegistry()

    def make_attempt(index: int, *, changed: bool = False) -> EffectAttempt:
        return EffectAttempt(
            operation_id="operation-stress-1",
            attempt_id=f"attempt-{index:08d}",
            decision_evidence_digest=decision.decision_evidence_digest,
            action_digest=decision.action_digest,
            payload_digest=(
                digest_value("changed-payload") if changed else payload_digest
            ),
            principal_id=decision.principal_id,
            boundary_emitter_id=decision.boundary_emitter_id,
            dispatch_state="attempted",
            attempted_at="2026-08-12T04:00:00.000Z",
            idempotency_key_digest=key_digest,
            idempotency_scope="provider:stress",
        )

    def bind(index: int) -> str:
        attempt = make_attempt(index)
        attempt.validate_against(decision)
        observation = EffectObservation(
            observation_id=f"observation-{index:08d}",
            operation_id=attempt.operation_id,
            attempt_id=attempt.attempt_id,
            decision_evidence_digest=attempt.decision_evidence_digest,
            action_digest=attempt.action_digest,
            payload_digest=attempt.payload_digest,
            principal_id=attempt.principal_id,
            disposition="outcome_unknown",
            observation_basis=(
                "local_timeout" if index % 2 == 0 else "transport_error"
            ),
            observer_id="local-boundary:stress",
            observed_at="2026-08-12T04:00:01.000Z",
        )
        observation.validate_against(decision, attempt)
        return registry.register(attempt)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        bindings = list(pool.map(bind, range(iterations)))

    conflict_count = max(1, iterations // 10)

    def conflict(index: int) -> str:
        try:
            registry.register(make_attempt(iterations + index, changed=True))
        except EffectContractError:
            return "REJECTED"
        return "UNEXPECTED_ACCEPT"

    with ThreadPoolExecutor(max_workers=workers) as pool:
        conflicts = list(pool.map(conflict, range(conflict_count)))

    result = {
        "schema": "auec.private-effect-stress.v1",
        "iterations": iterations,
        "workers": workers,
        "newBindings": bindings.count("BOUND_NEW"),
        "safeReplays": bindings.count("BOUND_REPLAY"),
        "payloadConflicts": conflict_count,
        "payloadConflictsRejected": conflicts.count("REJECTED"),
        "unexpectedAccepted": conflicts.count("UNEXPECTED_ACCEPT"),
        "registryEntries": len(registry.snapshot()),
        "networkRequired": False,
        "consequentialEffects": False,
    }
    result["status"] = (
        "PASS"
        if result["newBindings"] == 1
        and result["safeReplays"] == iterations - 1
        and result["payloadConflictsRejected"] == conflict_count
        and result["unexpectedAccepted"] == 0
        and result["registryEntries"] == 1
        else "FAIL"
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=10_000)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    result = run_effect_stress(args.iterations, args.workers)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
