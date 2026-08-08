# SPDX-License-Identifier: Apache-2.0
"""Run isolated causal source mutations in disposable copies."""

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
    target: str
    needle: str
    replacement: str


CAPABILITY_GUARD = (
    'if candidate_effective["capabilities"] != requested["capabilities"]:'
)
MUTATIONS = (
    Mutation(
        "remove-host-intersection",
        "fixture:denied_host_capability",
        "authority_validator.py",
        CAPABILITY_GUARD,
        "if False:",
    ),
    Mutation(
        "accept-claim-as-authority",
        "fixture:denied_claim",
        "authority_validator.py",
        'epistemic_status = epistemic.get("status")',
        'epistemic_status = "fact"',
    ),
    Mutation(
        "ignore-consent-digest",
        "fixture:denied_consent_digest",
        "authority_validator.py",
        'if consent.get("actionDigest") != action_digest:',
        "if False:",
    ),
    Mutation(
        "signed-declaration-grants-authority",
        "fixture:denied_signed_not_authority",
        "authority_validator.py",
        CAPABILITY_GUARD,
        'if candidate_effective["capabilities"] != requested["capabilities"] and not declaration_authenticated:',
    ),
    Mutation(
        "accept-unknown-critical-field",
        "fixture:denied_unknown_field",
        "authority_validator.py",
        "if unknown_top_level:",
        "if False:",
    ),
    Mutation(
        "audit-record-grants-authority",
        "fixture:denied_audit_not_authority",
        "authority_validator.py",
        CAPABILITY_GUARD,
        'if candidate_effective["capabilities"] != requested["capabilities"] and not request.get("auditRecord"):',
    ),
    Mutation(
        "accept-inconsistent-delta",
        "delta-inconsistent",
        "authority_validator.py",
        'if evidence["delta"] != expected_delta:',
        "if False:",
    ),
    Mutation(
        "skip-decision-digest-link",
        "decision-digest",
        "authority_validator.py",
        "if digest_json(evidence) != expected_digest:",
        "if False:",
    ),
    Mutation(
        "skip-emitter-identity-link",
        "wrong-emitter",
        "authority_validator.py",
        'if evidence["recordEmitterId"] != self.emitter_id:',
        "if False:",
    ),
    Mutation(
        "skip-action-digest-link",
        "wrong-action",
        "authority_validator.py",
        'if digest_json(observed_action) != evidence["actionDigest"]:',
        "if False:",
    ),
    Mutation(
        "skip-principal-link",
        "wrong-principal",
        "authority_validator.py",
        'if observed_principal_id != evidence["principalId"]:',
        "if False:",
    ),
    Mutation(
        "skip-actual-outcome-link",
        "wrong-outcome",
        "authority_validator.py",
        "if actual_outcome != expected_outcome:",
        "if False:",
    ),
    Mutation(
        "upgrade-self-attestation-without-proof",
        "self-attested",
        "sep3004_cleanroom.py",
        'return "self_attested"',
        'return "authenticated"',
    ),
)


def _copy_inputs(destination: Path) -> None:
    for name in (
        "authority_validator.py",
        "mutation_oracle.py",
        "sep3004_cleanroom.py",
        "UPSTREAM_PINS.json",
    ):
        shutil.copy2(ROOT / name, destination / name)
    shutil.copytree(ROOT / "fixtures", destination / "fixtures")


def _run(candidate: Path, oracle: str) -> bool:
    result = subprocess.run(
        [sys.executable, "-B", "mutation_oracle.py", "--oracle", oracle],
        cwd=candidate,
        check=False,
        text=True,
        encoding="utf-8",
        errors="strict",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=20,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip())
    return bool(json.loads(result.stdout)["safe"])


def run_mutations(temporary_parent: Path | None = None) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(
        prefix="auec-mcp-composition-mutants-",
        dir=None if temporary_parent is None else str(temporary_parent),
    ) as temporary:
        candidate = Path(temporary) / "candidate"
        candidate.mkdir()
        _copy_inputs(candidate)

        for mutation in MUTATIONS:
            source = candidate / mutation.target
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
                    "target": mutation.target,
                    "baseline": "GREEN" if baseline_safe else "UNEXPECTED",
                    "mutant": "RED_EXPECTED" if not mutant_safe else "UNEXPECTED",
                    "restoration": "GREEN" if restoration_safe else "UNEXPECTED",
                }
            )
    return results
