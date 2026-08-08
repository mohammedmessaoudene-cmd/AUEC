# SPDX-License-Identifier: Apache-2.0
"""Determine whether the current caller-governance registry loses decision basis."""

from __future__ import annotations

import copy
from typing import Any

from authority_validator import (
    ActionBoundaryEmitter,
    DEFAULT_CONTEXT,
    evaluate_authority,
    load_fixture,
)
from sep3004_cleanroom import verify_record


def _budget_request(limit: int) -> dict[str, Any]:
    request = load_fixture("positive_pure")
    request["action"]["budgets"] = {"nodes": 10}
    request["hostPolicy"]["maxBudgets"] = {"nodes": limit}
    return request


def assess_field_gap() -> dict[str, Any]:
    """Exercise one concrete collision in the current registered field set.

    Both actions are allowed and cross the same boundary.  Only the host policy
    limit differs, so the requested-to-effective budget delta differs.  The
    current caller-governance record cannot commit to that difference.
    """

    request_full = _budget_request(10)
    request_narrow = _budget_request(5)
    decision_full = evaluate_authority(request_full)
    decision_narrow = evaluate_authority(request_narrow)
    emitter = ActionBoundaryEmitter(DEFAULT_CONTEXT.record_emitter_id)
    context = {
        "eventId": "field-tribunal-0001",
        "occurredAt": "2026-08-08T00:00:01.000Z",
        "previousHash": None,
        "purposeDeclared": "exercise caller-governance field sufficiency",
    }

    def emit(
        decision: dict[str, Any],
        request: dict[str, Any],
        *,
        candidate: bool,
    ) -> dict[str, Any]:
        return emitter.emit(
            decision,
            observed_action=request["action"],
            observed_principal_id=DEFAULT_CONTEXT.principal_id,
            actual_outcome="allowed",
            recorder_context=copy.deepcopy(context),
            include_candidate_commitment=candidate,
        )

    current_full = emit(decision_full, request_full, candidate=False)
    current_narrow = emit(decision_narrow, request_narrow, candidate=False)
    candidate_full = emit(decision_full, request_full, candidate=True)
    candidate_narrow = emit(decision_narrow, request_narrow, candidate=True)
    evidence_digests_differ = (
        current_full["decisionEvidenceDigest"]
        != current_narrow["decisionEvidenceDigest"]
    )
    current_hashes_equal = (
        current_full["record"]["event_hash"] == current_narrow["record"]["event_hash"]
    )
    candidate_hashes_differ = (
        candidate_full["record"]["event_hash"]
        != candidate_narrow["record"]["event_hash"]
    )
    candidate_rejected_by_current_registry = bool(
        verify_record(candidate_full["record"])
        and verify_record(candidate_narrow["record"])
    )
    gap_proven = (
        evidence_digests_differ
        and current_hashes_equal
        and candidate_hashes_differ
        and candidate_rejected_by_current_registry
    )
    return {
        "status": "PASS" if gap_proven else "FAIL",
        "decision": (
            "CALLER_GOVERNANCE_OPTIONAL_FIELDS_CANDIDATE"
            if gap_proven
            else "IMPLEMENTATION_ONLY"
        ),
        "concreteVector": "CG-DELTA-LOSS-01",
        "currentRecordsConformant": (
            current_full["currentRegistryConformant"]
            and current_narrow["currentRegistryConformant"]
        ),
        "currentRecordHashesEqual": current_hashes_equal,
        "decisionEvidenceDigestsDiffer": evidence_digests_differ,
        "candidateRecordHashesDiffer": candidate_hashes_differ,
        "candidateRejectedByCurrentRegistry": candidate_rejected_by_current_registry,
        "fullDelta": decision_full["decisionEvidence"]["delta"],
        "narrowDelta": decision_narrow["decisionEvidence"]["delta"],
        "minimalCandidateFields": [
            {
                "name": "decision_evidence_hash",
                "type": "string",
                "semantics": (
                    "opaque algorithm-qualified commitment to a separately "
                    "canonicalized authority-decision evidence envelope"
                ),
            }
        ],
        "registrationStatus": "UNREGISTERED_PRIVATE_CANDIDATE",
        "newRecordCore": False,
        "newCanonicalization": False,
    }
