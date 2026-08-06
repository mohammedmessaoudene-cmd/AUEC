# SPDX-License-Identifier: Apache-2.0
"""Experimental, draft-aligned AUEC validator composition for MCP proposals."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
from typing import Any

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
}
POLICY_FIELDS = {
    "allowedCapabilities",
    "allowedEffects",
    "allowedEgress",
    "consentRequiredEffects",
    "requireIndependentValidation",
    "requireAuthenticatedDeclarationForConsequential",
}
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

EFFECT_RANK = {"read": 0, "write": 1, "destructive": 2}
LABEL_EFFECT = {
    "read-only": "read",
    "writes-data": "write",
    "destructive": "destructive",
}
EGRESS_RANK = {"none": 0, "internal": 1, "external": 2}


class ContractError(ValueError):
    """Raised when deterministic canonicalization cannot represent an input."""


def _validate_json_value(value: Any) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ContractError("non-finite number")
        raise ContractError(
            "floating-point values are outside this experimental profile"
        )
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
    """Return the spike's deterministic JSON form; this is not an RFC 8785 claim."""

    _validate_json_value(value)
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def digest_json(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _deny(
    code: str,
    message: str,
    *,
    action_digest: str,
    policy_digest: str,
    declaration_authenticated: bool,
    audit_input_ignored: bool,
) -> dict[str, Any]:
    return {
        "interceptor": "auec-authority-boundary",
        "type": "validation",
        "phase": "request",
        "valid": False,
        "severity": "error",
        "messages": [{"message": message, "severity": "error"}],
        "info": {
            "profile": "auec-authority-boundary/experimental-v1",
            "verdict": "deny",
            "reasonCode": code,
            "actionDigest": action_digest,
            "effectivePolicyDigest": policy_digest,
            "declarationAuthenticated": declaration_authenticated,
            "auditInputIgnored": audit_input_ignored,
            "upstreamPins": {
                key: value["headSha"] for key, value in PINS["proposals"].items()
            },
        },
    }


def _allow(
    *,
    action_digest: str,
    policy_digest: str,
    declaration_authenticated: bool,
    audit_input_ignored: bool,
) -> dict[str, Any]:
    return {
        "interceptor": "auec-authority-boundary",
        "type": "validation",
        "phase": "request",
        "valid": True,
        "severity": "info",
        "messages": [],
        "info": {
            "profile": "auec-authority-boundary/experimental-v1",
            "verdict": "allow",
            "reasonCode": "ALLOW_HOST_POLICY",
            "actionDigest": action_digest,
            "effectivePolicyDigest": policy_digest,
            "declarationAuthenticated": declaration_authenticated,
            "auditInputIgnored": audit_input_ignored,
            "upstreamPins": {
                key: value["headSha"] for key, value in PINS["proposals"].items()
            },
        },
    }


def evaluate_authority(request: dict[str, Any]) -> dict[str, Any]:
    """Evaluate one proposal without network access or consequential effects."""

    if not isinstance(request, dict):
        raise ContractError("request must be an object")
    unknown_top_level = set(request) - TOP_LEVEL_FIELDS
    if unknown_top_level:
        empty_digest = digest_json({})
        return _deny(
            "E_UNKNOWN_CRITICAL_FIELD",
            "unknown critical request field",
            action_digest=empty_digest,
            policy_digest=empty_digest,
            declaration_authenticated=False,
            audit_input_ignored="auditRecord" in request,
        )

    action = request.get("action")
    policy = request.get("hostPolicy")
    epistemic = request.get("epistemic")
    if not isinstance(action, dict) or set(action) - ACTION_FIELDS:
        raise ContractError("action has an invalid shape")
    if not isinstance(policy, dict) or set(policy) != POLICY_FIELDS:
        raise ContractError("hostPolicy has an invalid shape")
    if not isinstance(epistemic, dict) or set(epistemic) - EPISTEMIC_FIELDS:
        raise ContractError("epistemic has an invalid shape")

    action_digest = digest_json(action)
    policy_digest = digest_json(policy)
    audit_input_ignored = "auditRecord" in request

    declaration = request.get("declaration")
    declaration_authenticated = False
    if declaration is not None:
        if not isinstance(declaration, dict) or set(declaration) - DECLARATION_FIELDS:
            raise ContractError("declaration has an invalid shape")
        declaration_authenticated = bool(declaration.get("authenticated"))
        if declaration_authenticated:
            if not declaration.get("signatureValid"):
                return _deny(
                    "E_DECLARATION_SIGNATURE",
                    "authenticated declaration failed signature verification",
                    action_digest=action_digest,
                    policy_digest=policy_digest,
                    declaration_authenticated=True,
                    audit_input_ignored=audit_input_ignored,
                )
            if not declaration.get("fresh"):
                return _deny(
                    "E_DECLARATION_STALE",
                    "authenticated declaration is stale",
                    action_digest=action_digest,
                    policy_digest=policy_digest,
                    declaration_authenticated=True,
                    audit_input_ignored=audit_input_ignored,
                )
            if not declaration.get("versionMatches"):
                return _deny(
                    "E_DECLARATION_VERSION",
                    "declaration version or content digest changed",
                    action_digest=action_digest,
                    policy_digest=policy_digest,
                    declaration_authenticated=True,
                    audit_input_ignored=audit_input_ignored,
                )
            trust = declaration.get("trust", {})
            if not isinstance(trust, dict) or set(trust) - TRUST_FIELDS:
                raise ContractError("trust label has an invalid shape")
        elif policy["requireAuthenticatedDeclarationForConsequential"] and action.get(
            "consequential"
        ):
            return _deny(
                "E_DECLARATION_REQUIRED",
                "consequential action requires an authenticated declaration",
                action_digest=action_digest,
                policy_digest=policy_digest,
                declaration_authenticated=False,
                audit_input_ignored=audit_input_ignored,
            )

    capability = action.get("capability")
    effect = action.get("effect")
    egress = action.get("egress")
    allowed_capabilities = set(policy["allowedCapabilities"])
    if capability not in allowed_capabilities:
        return _deny(
            "E_HOST_CAPABILITY",
            "host policy does not grant the requested capability",
            action_digest=action_digest,
            policy_digest=policy_digest,
            declaration_authenticated=declaration_authenticated,
            audit_input_ignored=audit_input_ignored,
        )

    effective_effect = effect
    effective_egress = egress
    if declaration_authenticated:
        trust = declaration.get("trust", {})
        declared_effect = LABEL_EFFECT.get(trust.get("effect"))
        declared_egress = trust.get("egress")
        if declared_effect is None or declared_egress not in EGRESS_RANK:
            return _deny(
                "E_TRUST_LABEL",
                "unknown authenticated trust label is treated as most restrictive",
                action_digest=action_digest,
                policy_digest=policy_digest,
                declaration_authenticated=True,
                audit_input_ignored=audit_input_ignored,
            )
        if declaration.get("capability") != capability:
            return _deny(
                "E_DECLARATION_CAPABILITY",
                "authenticated declaration does not bind the proposed capability",
                action_digest=action_digest,
                policy_digest=policy_digest,
                declaration_authenticated=True,
                audit_input_ignored=audit_input_ignored,
            )
        effective_effect = max(
            (effect, declared_effect),
            key=lambda value: EFFECT_RANK.get(value, 99),
        )
        effective_egress = max(
            (egress, declared_egress),
            key=lambda value: EGRESS_RANK.get(value, 99),
        )

    if effective_effect not in policy["allowedEffects"]:
        return _deny(
            "E_HOST_EFFECT",
            "host policy does not grant the effective effect",
            action_digest=action_digest,
            policy_digest=policy_digest,
            declaration_authenticated=declaration_authenticated,
            audit_input_ignored=audit_input_ignored,
        )
    if effective_egress not in policy["allowedEgress"]:
        return _deny(
            "E_HOST_EGRESS",
            "host policy does not grant the effective egress",
            action_digest=action_digest,
            policy_digest=policy_digest,
            declaration_authenticated=declaration_authenticated,
            audit_input_ignored=audit_input_ignored,
        )

    epistemic_status = epistemic.get("status")
    if epistemic_status in {"claim", "hypothesis"}:
        return _deny(
            "E_EPISTEMIC_NOT_AUTHORITY",
            "claim or hypothesis cannot authorize an action",
            action_digest=action_digest,
            policy_digest=policy_digest,
            declaration_authenticated=declaration_authenticated,
            audit_input_ignored=audit_input_ignored,
        )
    if (
        epistemic_status == "fact"
        and policy["requireIndependentValidation"]
        and not epistemic.get("independentlyValidated")
    ):
        return _deny(
            "E_INDEPENDENT_VALIDATION",
            "fact requires independent validation under host policy",
            action_digest=action_digest,
            policy_digest=policy_digest,
            declaration_authenticated=declaration_authenticated,
            audit_input_ignored=audit_input_ignored,
        )
    if epistemic_status not in {"fact", "artifact"}:
        return _deny(
            "E_EPISTEMIC_STATUS",
            "unsupported epistemic status",
            action_digest=action_digest,
            policy_digest=policy_digest,
            declaration_authenticated=declaration_authenticated,
            audit_input_ignored=audit_input_ignored,
        )

    requires_consent = bool(action.get("consequential")) or (
        effective_effect in policy["consentRequiredEffects"]
    )
    if requires_consent:
        consent = request.get("consent")
        if not isinstance(consent, dict):
            return _deny(
                "E_CONSENT_REQUIRED",
                "action-bound consent is required",
                action_digest=action_digest,
                policy_digest=policy_digest,
                declaration_authenticated=declaration_authenticated,
                audit_input_ignored=audit_input_ignored,
            )
        if consent.get("actionDigest") != action_digest:
            return _deny(
                "E_CONSENT_DIGEST",
                "consent is not bound to the exact action digest",
                action_digest=action_digest,
                policy_digest=policy_digest,
                declaration_authenticated=declaration_authenticated,
                audit_input_ignored=audit_input_ignored,
            )

    return _allow(
        action_digest=action_digest,
        policy_digest=policy_digest,
        declaration_authenticated=declaration_authenticated,
        audit_input_ignored=audit_input_ignored,
    )


def to_sep3004_record(
    validation_result: dict[str, Any],
    *,
    action: dict[str, Any],
    recorder_context: dict[str, Any],
) -> dict[str, Any]:
    """Map the result to the current caller-governance record shape.

    The recorder context is deliberately supplied out of band. The governed
    request cannot set the record time, event id, principal, or chain link.
    """

    required = {
        "eventId",
        "occurredAt",
        "principalId",
        "previousHash",
        "purposeDeclared",
    }
    if set(recorder_context) != required:
        raise ContractError("recorder context has an invalid shape")
    body = {
        "event_id": recorder_context["eventId"],
        "occurred_at": recorder_context["occurredAt"],
        "principal_id": recorder_context["principalId"],
        "event_type": "tool_call",
        "tool_name": action["tool"],
        "outcome": "allowed" if validation_result["valid"] else "denied",
        "extensions": {
            "caller-governance": {
                "purpose_declared": recorder_context["purposeDeclared"]
            }
        },
        "previous_hash": recorder_context["previousHash"],
    }
    return {**body, "event_hash": digest_json(body)}


def verify_sep3004_record(record: dict[str, Any]) -> bool:
    if not isinstance(record, dict) or "event_hash" not in record:
        return False
    body = {key: value for key, value in record.items() if key != "event_hash"}
    return record["event_hash"] == digest_json(body)


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
