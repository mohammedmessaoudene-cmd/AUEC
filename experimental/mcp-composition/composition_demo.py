# SPDX-License-Identifier: Apache-2.0
"""Build and verify deterministic evidence for the MCP composition experiment."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from adversarial_harness import run_adversarial
from authority_validator import (
    ActionBoundaryEmitter,
    DEFAULT_CONTEXT,
    ROOT,
    evaluate_authority,
    load_fixture,
)
from field_tribunal import assess_field_gap
from mutation_harness import run_mutations
from sep3004_cleanroom import verify_record
from sep3004_vectors import run_vectors


def build_report() -> dict[str, Any]:
    fixture_data = json.loads(
        (ROOT / "fixtures" / "cases.json").read_text(encoding="utf-8")
    )
    cases: list[dict[str, Any]] = []
    for name, definition in sorted(fixture_data.items()):
        result = evaluate_authority(load_fixture(name))
        expected = bool(definition["expectedValid"])
        cases.append(
            {
                "name": name,
                "expectedValid": expected,
                "observedValid": result["valid"],
                "reasonCode": result["info"]["reasonCode"],
                "oracle": "GREEN" if result["valid"] == expected else "UNEXPECTED",
                "decisionEvidenceDigest": result["info"]["decisionEvidenceDigest"],
            }
        )

    request = load_fixture("positive_consequential")
    decision = evaluate_authority(request)
    emitter = ActionBoundaryEmitter(DEFAULT_CONTEXT.record_emitter_id)
    recorder_context = {
        "eventId": "composition-fixture-0001",
        "occurredAt": "2026-08-08T00:00:00.000Z",
        "previousHash": None,
        "purposeDeclared": "exercise bounded composition fixture",
    }
    current = emitter.emit(
        decision,
        observed_action=request["action"],
        observed_principal_id=DEFAULT_CONTEXT.principal_id,
        actual_outcome="allowed",
        recorder_context=recorder_context,
    )
    candidate = emitter.emit(
        decision,
        observed_action=request["action"],
        observed_principal_id=DEFAULT_CONTEXT.principal_id,
        actual_outcome="allowed",
        recorder_context=recorder_context,
        include_candidate_commitment=True,
    )
    mutations = run_mutations()
    vectors = run_vectors()
    field_assessment = assess_field_gap()
    adversarial = run_adversarial()

    unexpected = sum(case["oracle"] != "GREEN" for case in cases)
    unexpected += sum(
        item["baseline"] != "GREEN"
        or item["mutant"] != "RED_EXPECTED"
        or item["restoration"] != "GREEN"
        for item in mutations
    )
    unexpected += vectors["failed"]
    unexpected += field_assessment["status"] != "PASS"
    unexpected += adversarial["status"] != "PASS"
    unexpected += bool(verify_record(current["record"]))
    unexpected += not bool(verify_record(candidate["record"]))
    return {
        "status": "PASS" if unexpected == 0 else "FAIL",
        "profile": "experimental-draft-aligned-non-conformant",
        "verdict": field_assessment["decision"],
        "cases": cases,
        "mutations": mutations,
        "authorityDecision": decision["decisionEvidence"],
        "decisionEmissionSeparation": {
            "decisionAuthorityId": decision["decisionEvidence"]["decisionAuthorityId"],
            "recordEmitterId": current["recordEmitterId"],
            "separateComponents": (
                decision["decisionEvidence"]["decisionAuthorityId"]
                != current["recordEmitterId"]
            ),
            "actionDigestVerifiedAtBoundary": True,
            "principalVerifiedAtBoundary": True,
            "actualOutcomeRecorded": True,
        },
        "sep3004Baseline": vectors,
        "sep3004Mapping": {
            "currentRegistryRecord": current["record"],
            "currentRegistryConformant": current["currentRegistryConformant"],
            "candidateCommitmentRecord": candidate["record"],
            "candidateConformantBeforeRegistration": candidate[
                "currentRegistryConformant"
            ],
            "authorityGrantedByRecord": False,
        },
        "fieldAssessment": field_assessment,
        "adversarial": adversarial,
        "networkRequired": False,
        "consequentialEffects": False,
        "unexpectedResults": unexpected,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--write-evidence", type=Path)
    parser.add_argument("--verify-evidence", type=Path)
    args = parser.parse_args()
    report = build_report()
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.write_evidence:
        args.write_evidence.parent.mkdir(parents=True, exist_ok=True)
        args.write_evidence.write_text(text, encoding="utf-8", newline="\n")
    if args.verify_evidence:
        expected = json.loads(args.verify_evidence.read_text(encoding="utf-8"))
        if expected != report:
            print("composition evidence mismatch", file=sys.stderr)
            return 1
    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        print(
            f"verdict={report['verdict']} status={report['status']} "
            f"cases={len(report['cases'])} mutants={len(report['mutations'])} "
            f"vectors={report['sep3004Baseline']['passed']}/"
            f"{report['sep3004Baseline']['total']} hostile="
            f"{report['adversarial']['hostileDecisionEnvelopes']} "
            "network=false effects=false"
        )
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
