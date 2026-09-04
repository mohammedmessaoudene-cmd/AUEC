# SPDX-License-Identifier: Apache-2.0
"""Host-owned authority decision and boundary-emission experiment."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sep3004_cleanroom import (
    compute_event_hash,
    qualify_producer_trust,
    verify_record,
)

ROOT = Path(__file__).resolve().parent
PINS = json.loads((ROOT / "UPSTREAM_PINS.json").read_text(encoding="utf-8"))

TOP_LEVEL_FIELDS = {
    "action",
    "hostPolicy",
    "epistemic",
    "consent",
    "declaration",
    "auditRecord",
}
ACTION_FIELDS = {
    "tool",
    "capability",
    "effect",
    "egress",
    "consequential",
    "arguments",
    "placement",
    "budgets",
}
POLICY_FIELDS = {
    "allowedCapabilities",
    "allowedEffects",
    "allowedEgress",
    "consentRequiredEffects",
    "requireIndependentValidation",
    "requireAuthenticatedDeclarationForConsequential",
    "allowedPlacements",
    "maxBudgets",
}
POLICY_REQUIRED_FIELDS = POLICY_FIELDS - {"allowedPlacements", "maxBudgets"}
EPISTEMIC_FIELDS = {"status", "independentlyValidated", "evidenceDigest"}
DECLARATION_FIELDS = {
    "authenticated",
    "signatureValid",
    "fresh",
    "versionMatches",
    "capability",
    "trust",
}
TRUST_FIELDS = {"effect", "egress", "dataSensitivity", "reversible", "idempotent"}
AUTHORITY_DIMENSIONS = ("capabilities", "effects", "egress", "placements")
BUDGET_DIMENSIONS = ("nodes", "outputs", "wallMs")

EFFECT_RANK = {"read": 0, "write": 1, "destructive": 2}
LABEL_EFFECT = {
    "read-only": "read",
    "writes-data": "write",
    "destructive": "destructive",
}
EGRESS_RANK = {"none": 0, "internal": 1, "external": 2}
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class ContractError(ValueError):
    """Raised when deterministic evidence cannot represent an input."""


@dataclass(frozen=True)
class DecisionContext:
    decision_id: str
    decided_at: str
    decision_authority_id: str
    record_emitter_id: str
    principal_id: str
    policy_id: str
    policy_version: str


DEFAULT_CONTEXT = DecisionContext(
    decision_id="decision-fixture-0001",
    decided_at="2026-08-08T00:00:00.000Z",
    decision_authority_id="auec-host-authority:test",
    record_emitter_id="auec-action-boundary:test",
    principal_id="principal:test",
    policy_id="auec/fixture-host-policy",
    policy_version="2026-08-08-rev1",
)


def _validate_json_value(value: Any) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ContractError("non-finite number")
        raise ContractError("floating-point values are outside this profile")
    if isinstance(value, list):
        for item in value:
            _validate_json_value(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ContractError("object keys must be strings")
            _validate_json_value(item)
        return
    raise ContractError(f"unsupported JSON type: {type(value).__name__}")


def canonical_json_bytes(value: Any) -> bytes:
    """Return deterministic AUEC evidence bytes; this is not an RFC 8785 claim."""

    _validate_json_value(value)
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def digest_json(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _sorted_unique_strings(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ContractError(f"{field} must be an array of strings")
    return sorted(set(value))


def _normalize_budgets(value: Any, field: str) -> dict[str, int]:
    if value is None:
        return {}
    if not isinstance(value, dict) or set(value) - set(BUDGET_DIMENSIONS):
        raise ContractError(f"{field} has an invalid shape")
    result: dict[str, int] = {}
    for key, amount in value.items():
        if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
            raise ContractError(f"{field}.{key} must be a non-negative integer")
        result[key] = amount
    return dict(sorted(result.items()))


def normalize_authority(value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError("authority set must be an object")
    expected = set(AUTHORITY_DIMENSIONS) | {"budgets"}
    if set(value) != expected:
        raise ContractError("authority set has an invalid shape")
    result = {
        dimension: _sorted_unique_strings(value[dimension], dimension)
        for dimension in AUTHORITY_DIMENSIONS
    }
    result["budgets"] = _normalize_budgets(value["budgets"], "budgets")
    return result


def intersect_authority(
    requested: dict[str, Any], host_allowed: dict[str, Any]
) -> dict[str, Any]:
    requested = normalize_authority(requested)
    host_allowed = normalize_authority(host_allowed)
    effective: dict[str, Any] = {}
    for dimension in AUTHORITY_DIMENSIONS:
        allowed = set(host_allowed[dimension])
        effective[dimension] = [
            item for item in requested[dimension] if item in allowed
        ]
    budgets: dict[str, int] = {}
    for dimension, requested_amount in requested["budgets"].items():
        allowed_amount = host_allowed["budgets"].get(dimension, requested_amount)
        budgets[dimension] = min(requested_amount, allowed_amount)
    effective["budgets"] = budgets
    return effective


def authority_delta(
    requested: dict[str, Any], effective: dict[str, Any]
) -> dict[str, Any]:
    requested = normalize_authority(requested)
    effective = normalize_authority(effective)
    removed: dict[str, list[str]] = {}
    for dimension in AUTHORITY_DIMENSIONS:
        requested_set = set(requested[dimension])
        effective_set = set(effective[dimension])
        if not effective_set <= requested_set:
            raise ContractError(f"effective {dimension} exceeds requested authority")
        removed[dimension] = sorted(requested_set - effective_set)
    reduced_budgets: dict[str, dict[str, int]] = {}
    for dimension, effective_amount in effective["budgets"].items():
        if dimension not in requested["budgets"]:
            raise ContractError(f"effective budget {dimension} was not requested")
        requested_amount = requested["budgets"][dimension]
        if effective_amount > requested_amount:
            raise ContractError(
                f"effective budget {dimension} exceeds requested budget"
            )
        if effective_amount < requested_amount:
            reduced_budgets[dimension] = {
                "requested": requested_amount,
                "effective": effective_amount,
            }
    return {"removed": removed, "reducedBudgets": reduced_budgets}


def validate_authority_relation(
    requested: dict[str, Any],
    host_allowed: dict[str, Any],
    effective: dict[str, Any],
) -> None:
    requested = normalize_authority(requested)
    host_allowed = normalize_authority(host_allowed)
    effective = normalize_authority(effective)
    for dimension in AUTHORITY_DIMENSIONS:
        effective_set = set(effective[dimension])
        if not effective_set <= set(requested[dimension]):
            raise ContractError(f"effective {dimension} exceeds requested authority")
        if not effective_set <= set(host_allowed[dimension]):
            raise ContractError(f"effective {dimension} exceeds host authority")
    for dimension, amount in effective["budgets"].items():
        if amount > requested["budgets"].get(dimension, -1):
            raise ContractError(f"effective {dimension} budget exceeds request")
        if amount > host_allowed["budgets"].get(
            dimension, requested["budgets"].get(dimension, -1)
        ):
            raise ContractError(f"effective {dimension} budget exceeds host policy")


def _requested_authority(action: dict[str, Any]) -> dict[str, Any]:
    placement = action.get("placement", "local")
    if not isinstance(placement, str):
        raise ContractError("action placement must be a string")
    return normalize_authority(
        {
            "capabilities": [action.get("capability")],
            "effects": [action.get("effect")],
            "egress": [action.get("egress")],
            "placements": [placement],
            "budgets": action.get("budgets", {}),
        }
    )


def _host_authority(policy: dict[str, Any]) -> dict[str, Any]:
    return normalize_authority(
        {
            "capabilities": policy["allowedCapabilities"],
            "effects": policy["allowedEffects"],
            "egress": policy["allowedEgress"],
            "placements": policy.get("allowedPlacements", ["local"]),
            "budgets": policy.get("maxBudgets", {}),
        }
    )


def _empty_authority(requested: dict[str, Any]) -> dict[str, Any]:
    return {
        **{dimension: [] for dimension in AUTHORITY_DIMENSIONS},
        "budgets": {},
    }


def verify_decision_evidence(evidence: dict[str, Any]) -> None:
    required = {
        "schema",
        "decisionId",
        "decidedAt",
        "decisionAuthorityId",
        "recordEmitterId",
        "principalId",
        "actionDigest",
        "policy",
        "inputs",
        "requested",
        "hostAllowed",
        "effective",
        "delta",
        "verdict",
        "reasonCodes",
        "producerTrust",
    }
    if not isinstance(evidence, dict) or set(evidence) != required:
        raise ContractError("decision evidence has an invalid shape")
    if evidence["schema"] != "auec.authority-decision-evidence.v0":
        raise ContractError("decision evidence schema mismatch")
    for field in (
        "decisionId",
        "decidedAt",
        "decisionAuthorityId",
        "recordEmitterId",
        "principalId",
    ):
        if not isinstance(evidence[field], str) or not evidence[field]:
            raise ContractError(f"decision evidence {field} is invalid")
    if not DIGEST_RE.fullmatch(evidence["actionDigest"]):
        raise ContractError("decision evidence actionDigest is invalid")
    policy = evidence["policy"]
    if not isinstance(policy, dict) or set(policy) != {"id", "version", "digest"}:
        raise ContractError("decision evidence policy has an invalid shape")
    if not all(isinstance(policy[key], str) and policy[key] for key in policy):
        raise ContractError("decision evidence policy fields must be non-empty")
    if not DIGEST_RE.fullmatch(policy["digest"]):
        raise ContractError("decision evidence policy digest is invalid")
    inputs = evidence["inputs"]
    expected_inputs = {
        "requestDigest",
        "declarationDigest",
        "epistemicDigest",
        "consentDigest",
        "ignoredAuditDigest",
    }
    if not isinstance(inputs, dict) or set(inputs) != expected_inputs:
        raise ContractError("decision evidence inputs have an invalid shape")
    for value in inputs.values():
        if value is not None and not DIGEST_RE.fullmatch(value):
            raise ContractError("decision evidence input digest is invalid")
    validate_authority_relation(
        evidence["requested"], evidence["hostAllowed"], evidence["effective"]
    )
    expected_delta = authority_delta(evidence["requested"], evidence["effective"])
    if evidence["delta"] != expected_delta:
        raise ContractError("decision evidence delta is inconsistent")
    if evidence["verdict"] not in {"allowed", "denied"}:
        raise ContractError("decision evidence verdict is invalid")
    if (
        not isinstance(evidence["reasonCodes"], list)
        or not evidence["reasonCodes"]
        or any(not isinstance(item, str) for item in evidence["reasonCodes"])
    ):
        raise ContractError("decision evidence reasonCodes are invalid")
    if evidence["producerTrust"] not in {
        "self_attested",
        "authenticated",
        "externally_anchored",
    }:
        raise ContractError("decision evidence producerTrust is invalid")


def evaluate_authority(
    request: dict[str, Any], *, context: DecisionContext = DEFAULT_CONTEXT
) -> dict[str, Any]:
    """Evaluate without network access or consequential effects."""

    if not isinstance(request, dict):
        raise ContractError("request must be an object")
    unknown_top_level = set(request) - TOP_LEVEL_FIELDS
    action = request.get("action")
    policy = request.get("hostPolicy")
    epistemic = request.get("epistemic")
    if not isinstance(action, dict) or set(action) - ACTION_FIELDS:
        raise ContractError("action has an invalid shape")
    if (
        not isinstance(policy, dict)
        or set(policy) - POLICY_FIELDS
        or not POLICY_REQUIRED_FIELDS <= set(policy)
    ):
        raise ContractError("hostPolicy has an invalid shape")
    if not isinstance(epistemic, dict) or set(epistemic) - EPISTEMIC_FIELDS:
        raise ContractError("epistemic has an invalid shape")

    action_digest = digest_json(action)
    policy_digest = digest_json(policy)
    requested = _requested_authority(action)
    host_allowed = _host_authority(policy)
    candidate_effective = intersect_authority(requested, host_allowed)
    audit_input_ignored = "auditRecord" in request
    declaration = request.get("declaration")
    consent = request.get("consent")
    inputs = {
        "requestDigest": digest_json({"action": action}),
        "declarationDigest": None if declaration is None else digest_json(declaration),
        "epistemicDigest": digest_json(epistemic),
        "consentDigest": None if consent is None else digest_json(consent),
        "ignoredAuditDigest": (
            None if not audit_input_ignored else digest_json(request["auditRecord"])
        ),
    }

    declaration_authenticated = False

    def finish(valid: bool, code: str, message: str) -> dict[str, Any]:
        effective = candidate_effective if valid else _empty_authority(requested)
        delta = authority_delta(requested, effective)
        evidence = {
            "schema": "auec.authority-decision-evidence.v0",
            "decisionId": context.decision_id,
            "decidedAt": context.decided_at,
            "decisionAuthorityId": context.decision_authority_id,
            "recordEmitterId": context.record_emitter_id,
            "principalId": context.principal_id,
            "actionDigest": action_digest,
            "policy": {
                "id": context.policy_id,
                "version": context.policy_version,
                "digest": policy_digest,
            },
            "inputs": inputs,
            "requested": requested,
            "hostAllowed": host_allowed,
            "effective": effective,
            "delta": delta,
            "verdict": "allowed" if valid else "denied",
            "reasonCodes": [code],
            "producerTrust": qualify_producer_trust(),
        }
        verify_decision_evidence(evidence)
        evidence_digest = digest_json(evidence)
        return {
            "interceptor": "auec-authority-boundary",
            "type": "validation",
            "phase": "request",
            "valid": valid,
            "severity": "info" if valid else "error",
            "messages": [] if valid else [{"message": message, "severity": "error"}],
            "info": {
                "profile": "auec-authority-boundary/experimental-v2",
                "verdict": "allow" if valid else "deny",
                "reasonCode": code,
                "actionDigest": action_digest,
                "effectivePolicyDigest": policy_digest,
                "decisionEvidenceDigest": evidence_digest,
                "declarationAuthenticated": declaration_authenticated,
                "auditInputIgnored": audit_input_ignored,
                "upstreamPins": {
                    key: value["headSha"] for key, value in PINS["proposals"].items()
                },
            },
            "decisionEvidence": evidence,
        }

    if unknown_top_level:
        return finish(False, "E_UNKNOWN_CRITICAL_FIELD", "unknown critical field")

    if declaration is not None:
        if not isinstance(declaration, dict) or set(declaration) - DECLARATION_FIELDS:
            raise ContractError("declaration has an invalid shape")
        declaration_authenticated = bool(declaration.get("authenticated"))
        if declaration_authenticated:
            if not declaration.get("signatureValid"):
                return finish(False, "E_DECLARATION_SIGNATURE", "invalid declaration")
            if not declaration.get("fresh"):
                return finish(False, "E_DECLARATION_STALE", "stale declaration")
            if not declaration.get("versionMatches"):
                return finish(False, "E_DECLARATION_VERSION", "version mismatch")
            trust = declaration.get("trust", {})
            if not isinstance(trust, dict) or set(trust) - TRUST_FIELDS:
                raise ContractError("trust label has an invalid shape")
        elif policy["requireAuthenticatedDeclarationForConsequential"] and action.get(
            "consequential"
        ):
            return finish(False, "E_DECLARATION_REQUIRED", "declaration required")

    if candidate_effective["capabilities"] != requested["capabilities"]:
        return finish(False, "E_HOST_CAPABILITY", "capability not granted")
    if candidate_effective["effects"] != requested["effects"]:
        return finish(False, "E_HOST_EFFECT", "effect not granted")
    if candidate_effective["egress"] != requested["egress"]:
        return finish(False, "E_HOST_EGRESS", "egress not granted")
    if candidate_effective["placements"] != requested["placements"]:
        return finish(False, "E_HOST_PLACEMENT", "placement not granted")

    if declaration_authenticated:
        trust = declaration.get("trust", {})
        declared_effect = LABEL_EFFECT.get(trust.get("effect"))
        declared_egress = trust.get("egress")
        if declared_effect is None or declared_egress not in EGRESS_RANK:
            return finish(False, "E_TRUST_LABEL", "unknown trust label")
        if declaration.get("capability") != action.get("capability"):
            return finish(False, "E_DECLARATION_CAPABILITY", "capability mismatch")
        evaluated_effect = max(
            (action.get("effect"), declared_effect),
            key=lambda value: EFFECT_RANK.get(value, 99),
        )
        evaluated_egress = max(
            (action.get("egress"), declared_egress),
            key=lambda value: EGRESS_RANK.get(value, 99),
        )
        if evaluated_effect not in policy["allowedEffects"]:
            return finish(False, "E_HOST_EFFECT", "declared risk exceeds policy")
        if evaluated_egress not in policy["allowedEgress"]:
            return finish(False, "E_HOST_EGRESS", "declared egress exceeds policy")

    epistemic_status = epistemic.get("status")
    if epistemic_status in {"claim", "hypothesis"}:
        return finish(False, "E_EPISTEMIC_NOT_AUTHORITY", "claim is not authority")
    if (
        epistemic_status == "fact"
        and policy["requireIndependentValidation"]
        and not epistemic.get("independentlyValidated")
    ):
        return finish(False, "E_INDEPENDENT_VALIDATION", "validation required")
    if epistemic_status not in {"fact", "artifact"}:
        return finish(False, "E_EPISTEMIC_STATUS", "unsupported epistemic status")

    requires_consent = bool(action.get("consequential")) or (
        action.get("effect") in policy["consentRequiredEffects"]
    )
    if requires_consent:
        if not isinstance(consent, dict):
            return finish(False, "E_CONSENT_REQUIRED", "consent required")
        if consent.get("actionDigest") != action_digest:
            return finish(False, "E_CONSENT_DIGEST", "consent action mismatch")

    return finish(True, "ALLOW_HOST_POLICY", "allowed")


class ActionBoundaryEmitter:
    """Emit at the actual action boundary, separately from the policy engine."""

    def __init__(self, emitter_id: str):
        if not emitter_id:
            raise ContractError("record emitter identity is required")
        self.emitter_id = emitter_id

    def emit(
        self,
        validation_result: dict[str, Any],
        *,
        observed_action: dict[str, Any],
        observed_principal_id: str,
        authority_outcome: str,
        recorder_context: dict[str, Any],
        include_candidate_commitment: bool = False,
    ) -> dict[str, Any]:
        """Emit a current-registry authority-boundary record.

        ``authority_outcome`` is explicitly an authorization result.  It is
        not provider-side effect evidence; effect attempts and observations
        use the separate private lifecycle model.
        """

        evidence = validation_result.get("decisionEvidence")
        verify_decision_evidence(evidence)
        expected_digest = validation_result["info"]["decisionEvidenceDigest"]
        if digest_json(evidence) != expected_digest:
            raise ContractError("decision evidence digest mismatch")
        if evidence["recordEmitterId"] != self.emitter_id:
            raise ContractError("unexpected record emitter")
        if digest_json(observed_action) != evidence["actionDigest"]:
            raise ContractError("observed action differs from the decision")
        if observed_principal_id != evidence["principalId"]:
            raise ContractError("observed principal differs from the decision")
        if authority_outcome != evidence["verdict"]:
            raise ContractError("authority outcome contradicts the decision")
        required_context = {
            "eventId",
            "occurredAt",
            "previousHash",
            "purposeDeclared",
        }
        if set(recorder_context) != required_context:
            raise ContractError("recorder context has an invalid shape")
        extension: dict[str, Any] = {
            "purpose_declared": recorder_context["purposeDeclared"]
        }
        if include_candidate_commitment:
            extension["decision_evidence_hash"] = expected_digest
        body = {
            "event_id": recorder_context["eventId"],
            "occurred_at": recorder_context["occurredAt"],
            "principal_id": observed_principal_id,
            "event_type": "tool_call",
            "tool_name": observed_action["tool"],
            "outcome": authority_outcome,
            "extensions": {"caller-governance": extension},
            "previous_hash": recorder_context["previousHash"],
        }
        record = {**body, "event_hash": compute_event_hash(body)}
        return {
            "record": record,
            "decisionEvidenceDigest": expected_digest,
            "decisionAuthorityId": evidence["decisionAuthorityId"],
            "recordEmitterId": self.emitter_id,
            "producerTrust": qualify_producer_trust(),
            "currentRegistryConformant": not verify_record(record),
        }


def to_sep3004_record(
    validation_result: dict[str, Any],
    *,
    action: dict[str, Any],
    authority_outcome: str,
    recorder_context: dict[str, Any],
) -> dict[str, Any]:
    """Produce an authority record without claiming an effect disposition."""

    evidence = validation_result["decisionEvidence"]
    legacy_context = {
        "eventId": recorder_context["eventId"],
        "occurredAt": recorder_context["occurredAt"],
        "previousHash": recorder_context["previousHash"],
        "purposeDeclared": recorder_context["purposeDeclared"],
    }
    emitted = ActionBoundaryEmitter(evidence["recordEmitterId"]).emit(
        validation_result,
        observed_action=action,
        observed_principal_id=evidence["principalId"],
        authority_outcome=authority_outcome,
        recorder_context=legacy_context,
    )
    return emitted["record"]


def verify_sep3004_record(record: dict[str, Any]) -> bool:
    return not verify_record(record)


def load_fixture(name: str) -> dict[str, Any]:
    fixtures = json.loads(
        (ROOT / "fixtures" / "cases.json").read_text(encoding="utf-8")
    )
    if name not in fixtures:
        raise KeyError(name)
    request = copy.deepcopy(fixtures[name]["request"])
    consent = request.get("consent")
    if (
        isinstance(consent, dict)
        and consent.get("actionDigest") == "AUTO_ACTION_DIGEST"
    ):
        consent["actionDigest"] = digest_json(request["action"])
    return request


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            evaluate_authority(load_fixture(args.fixture)),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
