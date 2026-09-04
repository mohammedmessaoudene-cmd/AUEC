# SPDX-License-Identifier: Apache-2.0
"""Run causal effect-lifecycle mutations in disposable private copies."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Mutation:
    name: str
    oracle: str
    needle: str
    replacement: str


MUTATIONS = (
    Mutation(
        "accept-untrusted-terminal-observer",
        "terminal-authority",
        "if self.observer_id not in authoritative_observer_ids:",
        "if False:",
    ),
    Mutation(
        "dispatch-after-denial",
        "denied-dispatch",
        'if decision.verdict != "allowed":',
        "if False:",
    ),
    Mutation(
        "reuse-key-with-different-payload",
        "key-payload",
        "if existing.payload_digest != attempt.payload_digest:",
        "if False:",
    ),
    Mutation(
        "rewrite-terminal-disposition",
        "terminal-rewrite",
        'if previous.disposition in TERMINAL_DISPOSITIONS:\n            raise EffectContractError("terminal effect disposition cannot be rewritten")\n        if previous.disposition != "outcome_unknown":',
        'if previous.disposition not in TERMINAL_DISPOSITIONS and previous.disposition != "outcome_unknown":',
    ),
    Mutation(
        "blind-retry-unknown-irreversible",
        "blind-retry",
        'if effect_class == "irreversible":\n        return "RECONCILIATION_REQUIRED_NO_BLIND_RETRY"\n    if effect_class not in {"read", "idempotent"}:',
        'if effect_class not in {"read", "idempotent", "irreversible"}:',
    ),
    Mutation(
        "skip-append-only-link",
        "append-link",
        "if self.previous_observation_digest != digest_dataclass(previous):",
        "if False:",
    ),
)


def _run(candidate: Path, oracle: str) -> bool:
    completed = subprocess.run(
        [sys.executable, "-B", "effect_mutation_oracle.py", "--oracle", oracle],
        cwd=candidate,
        check=False,
        text=True,
        encoding="utf-8",
        errors="strict",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=20,
    )
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip())
    return bool(json.loads(completed.stdout)["safe"])


def run_effect_mutations() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="auec-effect-mutants-") as temporary:
        candidate = Path(temporary)
        shutil.copy2(ROOT / "effect_lifecycle.py", candidate / "effect_lifecycle.py")
        shutil.copy2(
            ROOT / "effect_mutation_oracle.py",
            candidate / "effect_mutation_oracle.py",
        )
        source = candidate / "effect_lifecycle.py"
        for mutation in MUTATIONS:
            original = source.read_text(encoding="utf-8")
            if original.count(mutation.needle) != 1:
                raise RuntimeError(
                    f"{mutation.name}: mutation target must occur exactly once"
                )
            baseline_safe = _run(candidate, mutation.oracle)
            source.write_text(
                original.replace(mutation.needle, mutation.replacement),
                encoding="utf-8",
                newline="\n",
            )
            mutant_safe = _run(candidate, mutation.oracle)
            source.write_text(original, encoding="utf-8", newline="\n")
            restoration_safe = _run(candidate, mutation.oracle)
            results.append(
                {
                    "mutation": mutation.name,
                    "oracle": mutation.oracle,
                    "baseline": "GREEN" if baseline_safe else "UNEXPECTED",
                    "mutant": "RED_EXPECTED" if not mutant_safe else "UNEXPECTED",
                    "restoration": "GREEN" if restoration_safe else "UNEXPECTED",
                }
            )
    return results


def main() -> int:
    results = run_effect_mutations()
    status = (
        "PASS"
        if all(
            item["baseline"] == "GREEN"
            and item["mutant"] == "RED_EXPECTED"
            and item["restoration"] == "GREEN"
            for item in results
        )
        else "FAIL"
    )
    print(json.dumps({"status": status, "results": results}, indent=2, sort_keys=True))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
