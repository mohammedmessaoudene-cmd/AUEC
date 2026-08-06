# SPDX-License-Identifier: Apache-2.0
"""Exhaustively check the declared finite AUEC semantic model domains."""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reference-runtime"))

from aiew_uc.authority import evaluate_authority  # noqa: E402


def powerset(values: tuple[str, ...]):
    for mask in range(1 << len(values)):
        yield {value for index, value in enumerate(values) if mask & (1 << index)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "evidence" / "bounded-models.json",
    )
    args = parser.parse_args()
    counterexamples: list[dict] = []

    capabilities = ("hash.sha256", "text.length", "json.project")
    capability_pairs = 0
    planner_additions = 0
    for planner in powerset(capabilities):
        for host in powerset(capabilities):
            capability_pairs += 1
            effective = planner & host
            if not effective <= planner or not effective <= host:
                counterexamples.append(
                    {
                        "model": "capability-intersection",
                        "planner": sorted(planner),
                        "host": sorted(host),
                    }
                )
            for operation in set(capabilities) - planner:
                planner_additions += 1
                expanded = (planner | {operation}) & host
                if not expanded <= host or not (expanded - effective) <= {operation}:
                    counterexamples.append(
                        {"model": "capability-monotonicity", "operation": operation}
                    )

    placements = ("local", "edge", "cloud")
    placement_pairs = 0
    empty_placement_intersections = 0
    for planner in powerset(placements):
        for host in powerset(placements):
            placement_pairs += 1
            effective = planner & host
            if not effective:
                empty_placement_intersections += 1
            if not effective <= planner or not effective <= host:
                counterexamples.append(
                    {
                        "model": "placement-intersection",
                        "planner": sorted(planner),
                        "host": sorted(host),
                    }
                )

    budget_values = (1, 2, 4, 8, 16)
    budget_pairs = 0
    for planner_budget in budget_values:
        for host_budget in budget_values:
            budget_pairs += 1
            effective_budget = min(planner_budget, host_budget)
            if effective_budget > planner_budget or effective_budget > host_budget:
                counterexamples.append(
                    {
                        "model": "budget-minimum",
                        "planner": planner_budget,
                        "host": host_budget,
                    }
                )

    digest = "sha256:" + "1" * 64
    other_digest = "sha256:" + "2" * 64
    authority_states = 0
    authorized_consequential = 0
    for (
        status,
        validated,
        consent_required,
        digest_matches,
        effect,
        host_allows,
    ) in itertools.product(
        ("fact", "claim", "hypothesis"),
        (False, True),
        (False, True),
        (False, True),
        ("pure", "consequential"),
        (False, True),
    ):
        authority_states += 1
        request = {
            "epistemicStatus": status,
            "independentlyValidated": validated,
            "effectClass": effect,
            "consentRequired": consent_required,
            "actionDigest": digest,
            "consentDigest": digest if digest_matches else other_digest,
        }
        policy = {"allowedEffectClasses": [effect] if host_allows else []}
        decision = evaluate_authority(request, policy)
        expected = (
            status == "fact"
            and host_allows
            and (
                effect == "pure"
                or (validated and (not consent_required or digest_matches))
            )
        )
        if decision.authorized != expected:
            counterexamples.append(
                {
                    "model": "epistemic-authority",
                    "state": {
                        "status": status,
                        "validated": validated,
                        "consentRequired": consent_required,
                        "digestMatches": digest_matches,
                        "effect": effect,
                        "hostAllows": host_allows,
                    },
                    "expected": expected,
                    "actual": decision.authorized,
                }
            )
        if decision.authorized and effect == "consequential":
            authorized_consequential += 1
            if not (
                status == "fact"
                and validated
                and host_allows
                and (not consent_required or digest_matches)
            ):
                counterexamples.append(
                    {"model": "consequential-authorization-safety", "state": request}
                )

    payload = {
        "schemaVersion": 1,
        "declaredDomains": {
            "capabilities": list(capabilities),
            "placements": list(placements),
            "budgetValues": list(budget_values),
            "epistemicStatuses": ["fact", "claim", "hypothesis"],
            "booleans": [False, True],
            "effectClasses": ["pure", "consequential"],
        },
        "counts": {
            "capabilityPairs": capability_pairs,
            "plannerCapabilityAdditions": planner_additions,
            "placementPairs": placement_pairs,
            "emptyPlacementIntersectionsRejected": empty_placement_intersections,
            "budgetPairs": budget_pairs,
            "authorityStates": authority_states,
            "authorizedConsequentialStates": authorized_consequential,
            "totalChecked": (
                capability_pairs
                + planner_additions
                + placement_pairs
                + budget_pairs
                + authority_states
            ),
        },
        "counterexamples": counterexamples,
        "scope": "Exhaustive only over the finite domains declared above; not an unbounded formal proof.",
        "verdict": "PASS" if not counterexamples else "FAIL",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(payload["counts"], sort_keys=True))
    print(
        f"BOUNDED MODELS {payload['verdict']}: {len(counterexamples)} counterexamples"
    )
    return 0 if not counterexamples else 1


if __name__ == "__main__":
    raise SystemExit(main())
