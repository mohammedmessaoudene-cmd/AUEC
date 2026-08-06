# SPDX-License-Identifier: Apache-2.0
"""Build and verify deterministic evidence for the MCP composition spike."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from authority_validator import (
    ROOT,
    evaluate_authority,
    load_fixture,
    to_sep3004_record,
    verify_sep3004_record,
)
from mutation_harness import run_mutations


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
            }
        )

    action = load_fixture("positive_consequential")["action"]
    positive = evaluate_authority(load_fixture("positive_consequential"))
    recorder_context = {
        "eventId": "composition-fixture-0001",
        "occurredAt": "2026-08-06T00:00:00.000Z",
        "principalId": "composition-test-principal",
        "previousHash": None,
        "purposeDeclared": "exercise bounded composition fixture",
    }
    record = to_sep3004_record(
        positive,
        action=action,
        recorder_context=recorder_context,
    )
    mutations = run_mutations()
    unexpected = sum(case["oracle"] != "GREEN" for case in cases)
    unexpected += sum(
        item["baseline"] != "GREEN"
        or item["mutant"] != "RED_EXPECTED"
        or item["restoration"] != "GREEN"
        for item in mutations
    )
    return {
        "status": "PASS" if unexpected == 0 else "FAIL",
        "profile": "experimental-draft-aligned-non-conformant",
        "verdict": "INTERCEPTOR_PROFILE_CANDIDATE",
        "cases": cases,
        "mutations": mutations,
        "sep3004Mapping": {
            "verified": verify_sep3004_record(record),
            "record": record,
            "authorityGrantedByRecord": False,
        },
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
        print(
            json.dumps(
                report, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
        )
    else:
        print(
            f"verdict={report['verdict']} status={report['status']} "
            f"cases={len(report['cases'])} mutants={len(report['mutations'])} "
            "network=false effects=false"
        )
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    import sys

    raise SystemExit(main())
