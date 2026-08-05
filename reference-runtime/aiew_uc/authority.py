# SPDX-License-Identifier: AGPL-3.0-only
"""Pure, deterministic authorization predicate for bounded decision testing.

The predicate evaluates whether an action description would be authorized. It
does not dispatch, execute, or simulate the described action.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any

from .errors import AUECError

_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_EPISTEMIC_STATUSES = {"fact", "claim", "hypothesis"}
_EFFECT_CLASSES = {"pure", "consequential"}
_REQUEST_FIELDS = {
    "epistemicStatus",
    "independentlyValidated",
    "effectClass",
    "consentRequired",
    "actionDigest",
    "consentDigest",
}
_POLICY_FIELDS = {"allowedEffectClasses"}


@dataclass(frozen=True)
class AuthorityDecision:
    authorized: bool
    action_digest: str
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["actionDigest"] = value.pop("action_digest")
        value["reasons"] = list(value["reasons"])
        return value


def _require_exact_fields(value: Mapping[str, Any], expected: set[str], name: str) -> None:
    if set(value) != expected:
        raise AUECError("E_AUTHORITY_INPUT", f"{name} fields do not match the decision contract")


def evaluate_authority(
    request: Mapping[str, Any],
    host_policy: Mapping[str, Any],
) -> AuthorityDecision:
    """Evaluate authority without producing an external effect.

    A claim or hypothesis is never treated as action authority. Consequential
    decisions additionally require independent validation and, when requested,
    consent bound to the exact action digest.
    """

    if not isinstance(request, Mapping) or not isinstance(host_policy, Mapping):
        raise AUECError("E_AUTHORITY_INPUT", "request and host policy must be objects")
    _require_exact_fields(request, _REQUEST_FIELDS, "request")
    _require_exact_fields(host_policy, _POLICY_FIELDS, "host policy")

    epistemic_status = request["epistemicStatus"]
    independently_validated = request["independentlyValidated"]
    effect_class = request["effectClass"]
    consent_required = request["consentRequired"]
    action_digest = request["actionDigest"]
    consent_digest = request["consentDigest"]
    allowed_effects = host_policy["allowedEffectClasses"]

    if epistemic_status not in _EPISTEMIC_STATUSES:
        raise AUECError("E_AUTHORITY_INPUT", "invalid epistemic status")
    if effect_class not in _EFFECT_CLASSES:
        raise AUECError("E_AUTHORITY_INPUT", "invalid effect class")
    if not isinstance(independently_validated, bool) or not isinstance(consent_required, bool):
        raise AUECError("E_AUTHORITY_INPUT", "validation and consent flags must be boolean")
    if not isinstance(action_digest, str) or not _DIGEST_RE.fullmatch(action_digest):
        raise AUECError("E_AUTHORITY_INPUT", "action digest must be canonical SHA-256")
    if consent_digest is not None and (
        not isinstance(consent_digest, str) or not _DIGEST_RE.fullmatch(consent_digest)
    ):
        raise AUECError("E_AUTHORITY_INPUT", "consent digest must be null or canonical SHA-256")
    if not isinstance(allowed_effects, list) or any(
        effect not in _EFFECT_CLASSES for effect in allowed_effects
    ) or len(allowed_effects) != len(set(allowed_effects)):
        raise AUECError("E_AUTHORITY_INPUT", "host effect policy is invalid")

    reasons: list[str] = []
    status_is_fact = epistemic_status == "fact"
    if not status_is_fact:
        reasons.append("E_AUTHORITY_EPISTEMIC")
    if effect_class not in allowed_effects:
        reasons.append("E_AUTHORITY_EFFECT")
    if effect_class == "consequential" and not independently_validated:
        reasons.append("E_AUTHORITY_VALIDATION")
    if effect_class == "consequential" and consent_required and consent_digest != action_digest:
        reasons.append("E_AUTHORITY_CONSENT")

    return AuthorityDecision(
        authorized=not reasons,
        action_digest=action_digest,
        reasons=tuple(reasons),
    )
