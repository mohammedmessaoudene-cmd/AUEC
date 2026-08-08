# SPDX-License-Identifier: Apache-2.0
"""Deterministic hostile-envelope and action-boundary assurance campaign."""

from __future__ import annotations

import copy
import random
from typing import Any, Callable

from authority_validator import (
    ActionBoundaryEmitter,
    ContractError,
    DEFAULT_CONTEXT,
    digest_json,
    evaluate_authority,
    load_fixture,
    verify_decision_evidence,
)
from sep3004_cleanroom import qualify_producer_trust


def _baseline() -> tuple[dict[str, Any], dict[str, Any]]:
    request = load_fixture("positive_pure")
    request["action"]["budgets"] = {"nodes": 10}
    request["hostPolicy"]["maxBudgets"] = {"nodes": 5}
    return request, evaluate_authority(request)


def run_adversarial(iterations: int = 10_000) -> dict[str, Any]:
    request, decision = _baseline()
    evidence = decision["decisionEvidence"]
    mutations: tuple[Callable[[dict[str, Any]], None], ...] = (
        lambda item: item.__setitem__("delta", {"removed": {}, "reducedBudgets": {}}),
        lambda item: item["effective"].__setitem__("capabilities", ["root"]),
        lambda item: item["effective"]["budgets"].__setitem__("nodes", 11),
        lambda item: item["policy"].__setitem__("version", ""),
        lambda item: item.__setitem__("principalId", ""),
        lambda item: item.__setitem__("recordEmitterId", ""),
        lambda item: item.__setitem__("actionDigest", "sha256:bad"),
        lambda item: item["inputs"].__setitem__("requestDigest", "sha256:bad"),
        lambda item: item.__setitem__("producerTrust", "independently_verified"),
        lambda item: item.__setitem__("reasonCodes", []),
    )
    randomizer = random.Random(48_3004)
    rejected = 0
    unexpected: list[int] = []
    for index in range(iterations):
        hostile = copy.deepcopy(evidence)
        mutations[randomizer.randrange(len(mutations))](hostile)
        try:
            verify_decision_evidence(hostile)
        except ContractError:
            rejected += 1
        else:
            unexpected.append(index)

    emitter = ActionBoundaryEmitter(DEFAULT_CONTEXT.record_emitter_id)
    context = {
        "eventId": "adversarial-boundary-0001",
        "occurredAt": "2026-08-08T00:00:02.000Z",
        "previousHash": None,
        "purposeDeclared": "exercise negative boundary linkage",
    }

    boundary_cases: dict[str, Callable[[], None]] = {
        "wrong_action": lambda: emitter.emit(
            decision,
            observed_action={**request["action"], "tool": "other-tool"},
            observed_principal_id=DEFAULT_CONTEXT.principal_id,
            actual_outcome="allowed",
            recorder_context=context,
        ),
        "wrong_principal": lambda: emitter.emit(
            decision,
            observed_action=request["action"],
            observed_principal_id="principal:attacker",
            actual_outcome="allowed",
            recorder_context=context,
        ),
        "wrong_outcome": lambda: emitter.emit(
            decision,
            observed_action=request["action"],
            observed_principal_id=DEFAULT_CONTEXT.principal_id,
            actual_outcome="denied",
            recorder_context=context,
        ),
        "wrong_emitter": lambda: ActionBoundaryEmitter("boundary:attacker").emit(
            decision,
            observed_action=request["action"],
            observed_principal_id=DEFAULT_CONTEXT.principal_id,
            actual_outcome="allowed",
            recorder_context=context,
        ),
        "decision_digest_mismatch": lambda: emitter.emit(
            {
                **decision,
                "info": {
                    **decision["info"],
                    "decisionEvidenceDigest": digest_json({"attacker": True}),
                },
            },
            observed_action=request["action"],
            observed_principal_id=DEFAULT_CONTEXT.principal_id,
            actual_outcome="allowed",
            recorder_context=context,
        ),
    }
    boundary_results: dict[str, str] = {}
    for name, operation in boundary_cases.items():
        try:
            operation()
        except ContractError:
            boundary_results[name] = "RED_EXPECTED"
        else:
            boundary_results[name] = "UNEXPECTED_GREEN"

    self_attested = qualify_producer_trust()
    status = (
        "PASS"
        if rejected == iterations
        and not unexpected
        and set(boundary_results.values()) == {"RED_EXPECTED"}
        and self_attested == "self_attested"
        else "FAIL"
    )
    return {
        "status": status,
        "hostileDecisionEnvelopes": iterations,
        "rejected": rejected,
        "unexpectedAccepted": len(unexpected),
        "unexpectedIndices": unexpected[:20],
        "boundaryCases": boundary_results,
        "producerTrust": self_attested,
        "independentProducerTruthEstablished": False,
        "networkRequired": False,
        "consequentialEffects": False,
    }
