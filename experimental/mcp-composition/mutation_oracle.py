# SPDX-License-Identifier: Apache-2.0
"""Safety oracles used only inside disposable source-mutation copies."""

from __future__ import annotations

import argparse
import copy
import json
from typing import Callable

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


def _rejected(operation: Callable[[], object]) -> bool:
    try:
        operation()
    except ContractError:
        return True
    return False


def _decision():
    request = load_fixture("positive_pure")
    return request, evaluate_authority(request)


def _emit_case(case: str) -> bool:
    request, decision = _decision()
    context = {
        "eventId": "mutation-boundary-1",
        "occurredAt": "2026-08-08T00:00:04.000Z",
        "previousHash": None,
        "purposeDeclared": "mutation oracle",
    }
    emitter = ActionBoundaryEmitter(DEFAULT_CONTEXT.record_emitter_id)
    if case == "wrong-action":
        return _rejected(
            lambda: emitter.emit(
                decision,
                observed_action={**request["action"], "tool": "changed"},
                observed_principal_id=DEFAULT_CONTEXT.principal_id,
                actual_outcome="allowed",
                recorder_context=context,
            )
        )
    if case == "wrong-principal":
        return _rejected(
            lambda: emitter.emit(
                decision,
                observed_action=request["action"],
                observed_principal_id="principal:changed",
                actual_outcome="allowed",
                recorder_context=context,
            )
        )
    if case == "wrong-emitter":
        return _rejected(
            lambda: ActionBoundaryEmitter("emitter:changed").emit(
                decision,
                observed_action=request["action"],
                observed_principal_id=DEFAULT_CONTEXT.principal_id,
                actual_outcome="allowed",
                recorder_context=context,
            )
        )
    if case == "wrong-outcome":
        return _rejected(
            lambda: emitter.emit(
                decision,
                observed_action=request["action"],
                observed_principal_id=DEFAULT_CONTEXT.principal_id,
                actual_outcome="denied",
                recorder_context=context,
            )
        )
    if case == "decision-digest":
        changed = copy.deepcopy(decision)
        changed["info"]["decisionEvidenceDigest"] = digest_json({"changed": True})
        return _rejected(
            lambda: emitter.emit(
                changed,
                observed_action=request["action"],
                observed_principal_id=DEFAULT_CONTEXT.principal_id,
                actual_outcome="allowed",
                recorder_context=context,
            )
        )
    raise KeyError(case)


def evaluate_oracle(name: str) -> bool:
    if name.startswith("fixture:"):
        return not evaluate_authority(load_fixture(name.split(":", 1)[1]))["valid"]
    if name == "delta-inconsistent":
        _, decision = _decision()
        evidence = copy.deepcopy(decision["decisionEvidence"])
        evidence["delta"] = {"removed": {}, "reducedBudgets": {}}
        return _rejected(lambda: verify_decision_evidence(evidence))
    if name in {
        "wrong-action",
        "wrong-principal",
        "wrong-emitter",
        "wrong-outcome",
        "decision-digest",
    }:
        return _emit_case(name)
    if name == "self-attested":
        return qualify_producer_trust() == "self_attested"
    raise KeyError(name)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--oracle", required=True)
    args = parser.parse_args()
    print(json.dumps({"safe": evaluate_oracle(args.oracle)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
