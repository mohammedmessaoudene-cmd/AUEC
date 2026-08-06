# SPDX-License-Identifier: Apache-2.0
"""Run six isolated causal mutations in disposable copies."""

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
    fixture: str
    needle: str
    replacement: str


CAPABILITY_GUARD = "if capability not in allowed_capabilities:"
MUTATIONS = (
    Mutation(
        "remove-host-intersection",
        "denied_host_capability",
        CAPABILITY_GUARD,
        "if False:",
    ),
    Mutation(
        "accept-claim-as-authority",
        "denied_claim",
        'epistemic_status = epistemic.get("status")',
        'epistemic_status = "fact"',
    ),
    Mutation(
        "ignore-consent-digest",
        "denied_consent_digest",
        'if consent.get("actionDigest") != action_digest:',
        "if False:",
    ),
    Mutation(
        "signed-declaration-grants-authority",
        "denied_signed_not_authority",
        CAPABILITY_GUARD,
        "if capability not in allowed_capabilities and not declaration_authenticated:",
    ),
    Mutation(
        "accept-unknown-critical-field",
        "denied_unknown_field",
        "if unknown_top_level:",
        "if False:",
    ),
    Mutation(
        "audit-record-grants-authority",
        "denied_audit_not_authority",
        CAPABILITY_GUARD,
        'if capability not in allowed_capabilities and not request.get("auditRecord"):',
    ),
)


def _copy_inputs(destination: Path) -> None:
    shutil.copy2(
        ROOT / "authority_validator.py", destination / "authority_validator.py"
    )
    shutil.copy2(ROOT / "UPSTREAM_PINS.json", destination / "UPSTREAM_PINS.json")
    shutil.copytree(ROOT / "fixtures", destination / "fixtures")


def _run(candidate: Path, fixture: str) -> dict[str, Any]:
    result = subprocess.run(
        [sys.executable, "authority_validator.py", "--fixture", fixture],
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
    return json.loads(result.stdout)


def run_mutations(temporary_parent: Path | None = None) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(
        prefix="auec-mcp-composition-mutants-",
        dir=None if temporary_parent is None else str(temporary_parent),
    ) as temporary:
        candidate = Path(temporary) / "candidate"
        candidate.mkdir()
        _copy_inputs(candidate)
        source = candidate / "authority_validator.py"

        for mutation in MUTATIONS:
            original = source.read_text(encoding="utf-8")
            if original.count(mutation.needle) != 1:
                raise RuntimeError(
                    f"{mutation.name}: mutation target must occur exactly once"
                )
            baseline = _run(candidate, mutation.fixture)
            source.write_text(
                original.replace(mutation.needle, mutation.replacement),
                encoding="utf-8",
                newline="\n",
            )
            mutant = _run(candidate, mutation.fixture)
            source.write_text(original, encoding="utf-8", newline="\n")
            restoration = _run(candidate, mutation.fixture)
            results.append(
                {
                    "mutation": mutation.name,
                    "fixture": mutation.fixture,
                    "baseline": "GREEN" if not baseline["valid"] else "UNEXPECTED",
                    "mutant": "RED_EXPECTED" if mutant["valid"] else "UNEXPECTED",
                    "restoration": (
                        "GREEN" if not restoration["valid"] else "UNEXPECTED"
                    ),
                }
            )
    return results
