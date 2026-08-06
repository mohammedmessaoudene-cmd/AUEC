# SPDX-License-Identifier: Apache-2.0
"""Run a safe red/green demonstration of the AUEC authority boundary."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reference-runtime"))

from aiew_uc.canonical import digest_json  # noqa: E402
from aiew_uc.model import default_host_policy  # noqa: E402


@dataclass(frozen=True)
class Mutation:
    scenario: str
    case: str
    source: str
    needle: str
    replacement: str
    baseline_expected: str
    mutation_expected: str
    restoration_expected: str


MUTATIONS = (
    Mutation(
        scenario="host-policy-intersection",
        case="nc-sem-01",
        source="reference-runtime/aiew_uc/model.py",
        needle='if not isinstance(op, str) or op not in PURE_OPS or op not in policy["allowedOps"]:',
        replacement="if not isinstance(op, str) or op not in PURE_OPS:",
        baseline_expected="rejected:E_OPERATION",
        mutation_expected="succeeded",
        restoration_expected="rejected:E_OPERATION",
    ),
    Mutation(
        scenario="epistemic-admission",
        case="nc-sem-02",
        source="reference-runtime/aiew_uc/model.py",
        needle='if output["epistemic"] not in {"fact", "artifact"}:',
        replacement='if output["epistemic"] not in {"fact", "artifact", "claim"}:',
        baseline_expected="rejected:E_EPISTEMIC",
        mutation_expected="succeeded",
        restoration_expected="rejected:E_EPISTEMIC",
    ),
    Mutation(
        scenario="authority-predicate",
        case="nc-sem-03",
        source="reference-runtime/aiew_uc/authority.py",
        needle='status_is_fact = epistemic_status == "fact"',
        replacement='status_is_fact = epistemic_status in {"fact", "claim"}',
        baseline_expected="fact=authorized;claim=denied",
        mutation_expected="claim=authorized",
        restoration_expected="fact=authorized;claim=denied",
    ),
)


def _copy_demo_inputs(destination: Path) -> None:
    shutil.copytree(
        ROOT / "reference-runtime",
        destination / "reference-runtime",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", "*.egg-info"),
    )
    (destination / "scripts").mkdir()
    shutil.copy2(
        ROOT / "scripts" / "core_semantic_probe.py",
        destination / "scripts" / "core_semantic_probe.py",
    )
    (destination / "examples").mkdir()
    shutil.copy2(
        ROOT / "examples" / "hello_manifest.json",
        destination / "examples" / "hello_manifest.json",
    )


def _probe(candidate: Path, case: str) -> dict[str, Any]:
    environment = os.environ.copy()
    environment.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": str(candidate / "reference-runtime"),
        }
    )
    result = subprocess.run(
        [sys.executable, "scripts/core_semantic_probe.py", case],
        cwd=candidate,
        env=environment,
        check=False,
        text=True,
        encoding="utf-8",
        errors="strict",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=20,
    )
    if result.returncode:
        raise RuntimeError(
            f"fixed demo probe failed for {case}: {result.stderr.strip()}"
        )
    return json.loads(result.stdout.strip())


def _status(observation: dict[str, Any]) -> str:
    if "status" in observation:
        if observation["status"] == "rejected":
            return f"rejected:{observation['error']}"
        return str(observation["status"])
    return "authorized" if observation["authorized"] else "denied"


def _authority_baseline(candidate: Path) -> tuple[dict[str, Any], str]:
    fact = _probe(candidate, "authority-fact")
    claim = _probe(candidate, "nc-sem-03")
    observed = f"fact={_status(fact)};claim={_status(claim)}"
    return {"fact": fact, "claim": claim}, observed


def build_demo_payload(temporary_parent: Path | None = None) -> dict[str, Any]:
    policy_digest = digest_json(default_host_policy())
    controls: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(
        prefix="auec-authority-demo-",
        dir=None if temporary_parent is None else str(temporary_parent),
    ) as temporary:
        candidate = Path(temporary) / "candidate"
        _copy_demo_inputs(candidate)

        for mutation in MUTATIONS:
            source = candidate / mutation.source
            original = source.read_text(encoding="utf-8")
            if original.count(mutation.needle) != 1:
                raise RuntimeError(
                    f"{mutation.scenario}: mutation target must occur exactly once"
                )

            if mutation.scenario == "authority-predicate":
                baseline_raw, baseline_observed = _authority_baseline(candidate)
            else:
                baseline_raw = _probe(candidate, mutation.case)
                baseline_observed = _status(baseline_raw)

            source.write_text(
                original.replace(mutation.needle, mutation.replacement),
                encoding="utf-8",
                newline="\n",
            )
            mutant_raw = _probe(candidate, mutation.case)
            mutation_observed = (
                f"claim={_status(mutant_raw)}"
                if mutation.scenario == "authority-predicate"
                else _status(mutant_raw)
            )

            source.write_text(original, encoding="utf-8", newline="\n")
            if mutation.scenario == "authority-predicate":
                restoration_raw, restoration_observed = _authority_baseline(candidate)
            else:
                restoration_raw = _probe(candidate, mutation.case)
                restoration_observed = _status(restoration_raw)

            observations = {
                "baseline": baseline_raw,
                "mutation": mutant_raw,
                "restoration": restoration_raw,
            }
            receipt_digest = digest_json(
                {"scenario": mutation.scenario, "observations": observations}
            )
            controls.append(
                {
                    "scenario": mutation.scenario,
                    "baseline": {
                        "expected": mutation.baseline_expected,
                        "observed": baseline_observed,
                        "oracle": "GREEN"
                        if baseline_observed == mutation.baseline_expected
                        else "FAIL",
                    },
                    "mutation": {
                        "expected": mutation.mutation_expected,
                        "observed": mutation_observed,
                        "oracle": "RED_EXPECTED"
                        if mutation_observed == mutation.mutation_expected
                        else "FAIL",
                    },
                    "restoration": {
                        "expected": mutation.restoration_expected,
                        "observed": restoration_observed,
                        "oracle": "GREEN"
                        if restoration_observed == mutation.restoration_expected
                        else "FAIL",
                    },
                    "policyDigest": policy_digest,
                    "receiptDigest": receipt_digest,
                }
            )

    verdict = "PASS"
    for control in controls:
        if (
            control["baseline"]["oracle"] != "GREEN"
            or control["mutation"]["oracle"] != "RED_EXPECTED"
            or control["restoration"]["oracle"] != "GREEN"
        ):
            verdict = "FAIL"

    return {
        "schema": "auec.authority-boundary-demo.v1",
        "profile": "U0",
        "verdict": verdict,
        "networkAccess": False,
        "consequentialEffects": False,
        "untrustedShellInput": False,
        "mutationIsolation": "disposable-copy",
        "controls": controls,
    }


def _print_table(payload: dict[str, Any]) -> None:
    print("AUEC authority-boundary demo (deterministic U0)")
    print(f"{'scenario':26} {'phase':12} {'oracle':13} {'expected':34} observed")
    print("-" * 112)
    for control in payload["controls"]:
        for phase in ("baseline", "mutation", "restoration"):
            row = control[phase]
            print(
                f"{control['scenario']:26} {phase:12} {row['oracle']:13} "
                f"{row['expected'][:34]:34} {row['observed']}"
            )
        print(
            f"{'':26} {'digests':12} {'':13} "
            f"policy={control['policyDigest'][:23]} "
            f"receipt={control['receiptDigest'][:23]}"
        )
    print("-" * 112)
    print(
        f"verdict={payload['verdict']} network=false effects=false "
        "mutations=disposable-copy"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="print JSON only")
    parser.add_argument("--write-evidence", type=Path)
    parser.add_argument("--verify-evidence", type=Path)
    args = parser.parse_args()

    payload = build_demo_payload()
    if args.write_evidence is not None:
        args.write_evidence.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    if args.verify_evidence is not None:
        recorded = json.loads(args.verify_evidence.read_text(encoding="utf-8"))
        if recorded != payload:
            raise SystemExit("recorded demo evidence does not match live results")

    if args.json:
        print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    else:
        _print_table(payload)
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
