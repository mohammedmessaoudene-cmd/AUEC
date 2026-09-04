# SPDX-License-Identifier: Apache-2.0
"""Private experimental authority/effect lifecycle model.

The policy decision, dispatch attempt, provider observation and later
reconciliation are deliberately separate objects.  This module performs no
network request and no consequential effect.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Iterable


DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
DISPOSITIONS = {
    "not_attempted",
    "outcome_unknown",
    "confirmed_occurred",
    "confirmed_absent",
}
TERMINAL_DISPOSITIONS = {"confirmed_occurred", "confirmed_absent"}
AUTHORITATIVE_BASES = {"provider_response", "system_of_record_query"}
UNKNOWN_BASES = {
    "local_timeout",
    "transport_error",
    "provider_pending",
    "emitter_crash",
    "audit_append_failure",
    *AUTHORITATIVE_BASES,
}


class EffectContractError(ValueError):
    """Raised when effect evidence violates a lifecycle invariant."""


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def digest_value(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def digest_dataclass(value: Any) -> str:
    return digest_value(asdict(value))


def digest_idempotency_key(key: str) -> str:
    """Return a one-way key commitment; the raw key is never retained."""

    if not isinstance(key, str) or not key:
        raise EffectContractError("idempotency key must be a non-empty string")
    return digest_value(key)


def _require_text(value: str | None, field: str) -> None:
    if not isinstance(value, str) or not value:
        raise EffectContractError(f"{field} must be a non-empty string")


def _require_digest(value: str, field: str) -> None:
    if not isinstance(value, str) or not DIGEST_RE.fullmatch(value):
        raise EffectContractError(f"{field} must be a sha256 digest")


def _timestamp(value: str | None, field: str) -> datetime:
    _require_text(value, field)
    if not value.endswith("Z"):
        raise EffectContractError(f"{field} must be an RFC 3339 UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise EffectContractError(f"{field} must be an RFC 3339 UTC timestamp") from exc
    if parsed.tzinfo != timezone.utc:
        raise EffectContractError(f"{field} must use UTC")
    return parsed


@dataclass(frozen=True)
class AuthorityDecision:
    decision_id: str
    operation_id: str
    decision_evidence_digest: str
    action_digest: str
    principal_id: str
    verdict: str
    decision_authority_id: str
    boundary_emitter_id: str

    @classmethod
    def from_validation_result(
        cls,
        result: dict[str, Any],
        *,
        operation_id: str,
    ) -> "AuthorityDecision":
        evidence = result.get("decisionEvidence")
        info = result.get("info")
        if not isinstance(evidence, dict) or not isinstance(info, dict):
            raise EffectContractError("validation result lacks decision evidence")
        decision_digest = info.get("decisionEvidenceDigest")
        if digest_value(evidence) != decision_digest:
            raise EffectContractError("decision evidence digest mismatch")
        decision = cls(
            decision_id=evidence.get("decisionId"),
            operation_id=operation_id,
            decision_evidence_digest=decision_digest,
            action_digest=evidence.get("actionDigest"),
            principal_id=evidence.get("principalId"),
            verdict=evidence.get("verdict"),
            decision_authority_id=evidence.get("decisionAuthorityId"),
            boundary_emitter_id=evidence.get("recordEmitterId"),
        )
        decision.validate()
        return decision

    def validate(self) -> None:
        _require_text(self.decision_id, "decision_id")
        _require_text(self.operation_id, "operation_id")
        _require_digest(self.decision_evidence_digest, "decision_evidence_digest")
        _require_digest(self.action_digest, "action_digest")
        _require_text(self.principal_id, "principal_id")
        _require_text(self.decision_authority_id, "decision_authority_id")
        _require_text(self.boundary_emitter_id, "boundary_emitter_id")
        if self.verdict not in {"allowed", "denied"}:
            raise EffectContractError("decision verdict must be allowed or denied")


@dataclass(frozen=True)
class EffectAttempt:
    operation_id: str
    attempt_id: str
    decision_evidence_digest: str
    action_digest: str
    payload_digest: str
    principal_id: str
    boundary_emitter_id: str
    dispatch_state: str
    attempted_at: str | None
    idempotency_key_digest: str | None = None
    idempotency_scope: str | None = None

    def validate_against(self, decision: AuthorityDecision) -> None:
        decision.validate()
        _require_text(self.operation_id, "operation_id")
        _require_text(self.attempt_id, "attempt_id")
        _require_digest(self.decision_evidence_digest, "decision_evidence_digest")
        _require_digest(self.action_digest, "action_digest")
        _require_digest(self.payload_digest, "payload_digest")
        _require_text(self.principal_id, "principal_id")
        _require_text(self.boundary_emitter_id, "boundary_emitter_id")
        if self.decision_evidence_digest != decision.decision_evidence_digest:
            raise EffectContractError("attempt decision evidence digest mismatch")
        if self.operation_id != decision.operation_id:
            raise EffectContractError("attempt operation mismatch")
        if self.action_digest != decision.action_digest:
            raise EffectContractError("attempt action digest mismatch")
        if self.principal_id != decision.principal_id:
            raise EffectContractError("attempt principal mismatch")
        if self.boundary_emitter_id != decision.boundary_emitter_id:
            raise EffectContractError("attempt boundary emitter mismatch")
        if self.dispatch_state not in {"not_attempted", "attempted"}:
            raise EffectContractError("invalid dispatch state")
        if self.dispatch_state == "attempted":
            if decision.verdict != "allowed":
                raise EffectContractError("denied decision cannot be dispatched")
            _timestamp(self.attempted_at, "attempted_at")
        elif self.attempted_at is not None:
            raise EffectContractError("not_attempted cannot carry an attempt time")
        if self.idempotency_key_digest is not None:
            _require_digest(self.idempotency_key_digest, "idempotency_key_digest")
            _require_text(self.idempotency_scope, "idempotency_scope")
        elif self.idempotency_scope is not None:
            raise EffectContractError("idempotency scope requires a key digest")


@dataclass(frozen=True)
class EffectObservation:
    observation_id: str
    operation_id: str
    attempt_id: str
    decision_evidence_digest: str
    action_digest: str
    payload_digest: str
    principal_id: str
    disposition: str
    observation_basis: str | None
    observer_id: str | None
    observed_at: str | None
    provider_effect_ref: str | None = None

    def validate_against(
        self,
        decision: AuthorityDecision,
        attempt: EffectAttempt,
        *,
        authoritative_observer_ids: frozenset[str] = frozenset(),
    ) -> None:
        decision.validate()
        attempt.validate_against(decision)
        _require_text(self.observation_id, "observation_id")
        if self.operation_id != attempt.operation_id:
            raise EffectContractError("observation operation mismatch")
        if self.attempt_id != attempt.attempt_id:
            raise EffectContractError("observation attempt mismatch")
        if self.decision_evidence_digest != attempt.decision_evidence_digest:
            raise EffectContractError("observation decision digest mismatch")
        if self.action_digest != attempt.action_digest:
            raise EffectContractError("observation action digest mismatch")
        if self.payload_digest != attempt.payload_digest:
            raise EffectContractError("observation payload digest mismatch")
        if self.principal_id != attempt.principal_id:
            raise EffectContractError("observation principal mismatch")
        if self.disposition not in DISPOSITIONS:
            raise EffectContractError("invalid effect disposition")

        if self.disposition == "not_attempted":
            if attempt.dispatch_state != "not_attempted":
                raise EffectContractError("attempted dispatch cannot be not_attempted")
            if any(
                value is not None
                for value in (
                    self.observation_basis,
                    self.observer_id,
                    self.observed_at,
                    self.provider_effect_ref,
                )
            ):
                raise EffectContractError("not_attempted cannot carry observation data")
            return

        if attempt.dispatch_state != "attempted":
            raise EffectContractError("post-dispatch disposition requires an attempt")
        if self.observation_basis not in UNKNOWN_BASES:
            raise EffectContractError("invalid observation basis")
        _require_text(self.observer_id, "observer_id")
        _timestamp(self.observed_at, "observed_at")

        if self.disposition in TERMINAL_DISPOSITIONS:
            if self.observation_basis not in AUTHORITATIVE_BASES:
                raise EffectContractError(
                    "terminal effect disposition requires provider evidence"
                )
            if self.observer_id not in authoritative_observer_ids:
                raise EffectContractError(
                    "terminal effect disposition requires an authoritative observer"
                )
        if self.disposition == "confirmed_occurred" and not self.provider_effect_ref:
            raise EffectContractError(
                "confirmed occurrence requires a provider effect reference"
            )
        if (
            self.disposition == "confirmed_absent"
            and self.provider_effect_ref is not None
        ):
            raise EffectContractError(
                "confirmed absence cannot carry a provider effect reference"
            )


@dataclass(frozen=True)
class ReconciliationRecord:
    reconciliation_id: str
    previous_observation_digest: str
    operation_id: str
    attempt_id: str
    decision_evidence_digest: str
    action_digest: str
    payload_digest: str
    principal_id: str
    appended_at: str
    observation: EffectObservation

    def validate_against(
        self,
        previous: EffectObservation,
        decision: AuthorityDecision,
        attempt: EffectAttempt,
        *,
        authoritative_observer_ids: frozenset[str],
    ) -> None:
        _require_text(self.reconciliation_id, "reconciliation_id")
        appended_at = _timestamp(self.appended_at, "appended_at")
        _require_digest(self.previous_observation_digest, "previous_observation_digest")
        previous.validate_against(
            decision,
            attempt,
            authoritative_observer_ids=authoritative_observer_ids,
        )
        self.observation.validate_against(
            decision,
            attempt,
            authoritative_observer_ids=authoritative_observer_ids,
        )
        if self.previous_observation_digest != digest_dataclass(previous):
            raise EffectContractError(
                "reconciliation does not append to prior evidence"
            )
        if self.reconciliation_id == previous.observation_id:
            raise EffectContractError(
                "reconciliation id must differ from the prior observation id"
            )
        if self.observation.observation_id == previous.observation_id:
            raise EffectContractError(
                "reconciliation requires a new observation identity"
            )
        if self.observation.observation_id == self.reconciliation_id:
            raise EffectContractError(
                "observation and reconciliation identities must be distinct"
            )
        if previous.observed_at is not None and appended_at <= _timestamp(
            previous.observed_at, "previous.observed_at"
        ):
            raise EffectContractError(
                "reconciliation append time must follow the prior observation"
            )
        if (
            self.observation.observed_at is not None
            and _timestamp(self.observation.observed_at, "observation.observed_at")
            > appended_at
        ):
            raise EffectContractError(
                "reconciliation cannot be appended before its observation"
            )
        bound = (
            self.operation_id,
            self.attempt_id,
            self.decision_evidence_digest,
            self.action_digest,
            self.payload_digest,
            self.principal_id,
        )
        expected = (
            attempt.operation_id,
            attempt.attempt_id,
            attempt.decision_evidence_digest,
            attempt.action_digest,
            attempt.payload_digest,
            attempt.principal_id,
        )
        if bound != expected:
            raise EffectContractError("reconciliation binding mismatch")
        if self.observation.operation_id != self.operation_id:
            raise EffectContractError("reconciliation observation operation mismatch")
        if self.observation.attempt_id != self.attempt_id:
            raise EffectContractError("reconciliation observation attempt mismatch")
        if previous.disposition in TERMINAL_DISPOSITIONS:
            raise EffectContractError("terminal effect disposition cannot be rewritten")
        if previous.disposition != "outcome_unknown":
            raise EffectContractError("only outcome_unknown can be reconciled")
        if self.observation.disposition not in TERMINAL_DISPOSITIONS:
            raise EffectContractError(
                "reconciliation must monotonically refine unknown to terminal"
            )


@dataclass(frozen=True)
class IdempotencyBinding:
    operation_id: str
    action_digest: str
    payload_digest: str


class IdempotencyRegistry:
    """Thread-safe private model storing digests and bindings, never raw keys."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._bindings: dict[tuple[str, str], IdempotencyBinding] = {}

    def register(self, attempt: EffectAttempt) -> str:
        if attempt.idempotency_key_digest is None:
            raise EffectContractError("idempotent registration requires a key digest")
        _require_text(attempt.idempotency_scope, "idempotency_scope")
        registry_key = (attempt.idempotency_scope, attempt.idempotency_key_digest)
        candidate = IdempotencyBinding(
            operation_id=attempt.operation_id,
            action_digest=attempt.action_digest,
            payload_digest=attempt.payload_digest,
        )
        with self._lock:
            existing = self._bindings.get(registry_key)
            if existing is None:
                self._bindings[registry_key] = candidate
                return "BOUND_NEW"
            if existing.operation_id != attempt.operation_id:
                raise EffectContractError(
                    "idempotency key reused for a different logical operation"
                )
            if existing.action_digest != attempt.action_digest:
                raise EffectContractError(
                    "idempotency key reused with a different action digest"
                )
            if existing.payload_digest != attempt.payload_digest:
                raise EffectContractError(
                    "idempotency key reused with a different payload digest"
                )
            return "BOUND_REPLAY"

    def snapshot(self) -> dict[str, dict[str, str]]:
        with self._lock:
            return {
                f"{scope}|{key_digest}": asdict(binding)
                for (scope, key_digest), binding in sorted(self._bindings.items())
            }


def retry_directive(
    attempt: EffectAttempt,
    observation: EffectObservation,
    *,
    effect_class: str,
    candidate_attempt: EffectAttempt | None = None,
    key_retention_valid: bool = True,
) -> str:
    state = observation.disposition
    if state == "not_attempted":
        return "ATTEMPT_ALLOWED"
    if state == "confirmed_occurred":
        return "REPLAY_CONFIRMED_RESULT_NO_REEXECUTION"
    if state == "confirmed_absent":
        return "NEW_ATTEMPT_ALLOWED_BY_POLICY"
    if state != "outcome_unknown":
        raise EffectContractError("unknown effect state")
    if effect_class == "irreversible":
        return "RECONCILIATION_REQUIRED_NO_BLIND_RETRY"
    if effect_class not in {"read", "idempotent"}:
        raise EffectContractError("unsupported effect class")
    if (
        candidate_attempt is None
        or not key_retention_valid
        or attempt.idempotency_key_digest is None
        or candidate_attempt.idempotency_key_digest != attempt.idempotency_key_digest
        or candidate_attempt.idempotency_scope != attempt.idempotency_scope
    ):
        return "RECONCILIATION_REQUIRED_NO_BLIND_RETRY"
    registry = IdempotencyRegistry()
    registry.register(attempt)
    registry.register(candidate_attempt)
    return "RETRY_SAME_IDEMPOTENCY_KEY_AND_CONTRACT_ONLY"


def verify_reconciliation_chain(
    initial: EffectObservation,
    records: Iterable[ReconciliationRecord],
    decision: AuthorityDecision,
    attempt: EffectAttempt,
    *,
    authoritative_observer_ids: frozenset[str],
) -> EffectObservation:
    current = initial
    for record in records:
        record.validate_against(
            current,
            decision,
            attempt,
            authoritative_observer_ids=authoritative_observer_ids,
        )
        current = record.observation
    return current


def candidate_effect_projection(
    decision: AuthorityDecision,
    attempt: EffectAttempt,
    observation: EffectObservation,
    *,
    authoritative_observer_ids: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    """Return an unregistered, non-conformant private candidate projection."""

    observation.validate_against(
        decision,
        attempt,
        authoritative_observer_ids=authoritative_observer_ids,
    )
    return {
        "event_type": "effect_observation",
        "authority_outcome": decision.verdict,
        "extensions": {
            "effect-disposition": {
                "operation_id": attempt.operation_id,
                "attempt_id": attempt.attempt_id,
                "decision_evidence_hash": attempt.decision_evidence_digest,
                "action_digest": attempt.action_digest,
                "payload_digest": attempt.payload_digest,
                "principal_id": attempt.principal_id,
                "dispatch_state": attempt.dispatch_state,
                "effect_disposition": observation.disposition,
                "observation_basis": observation.observation_basis,
                "effect_observer_id": observation.observer_id,
                "provider_effect_ref": observation.provider_effect_ref,
                "idempotency_key_hash": attempt.idempotency_key_digest,
            }
        },
        "registration_status": "UNREGISTERED_PRIVATE_CANDIDATE",
    }
