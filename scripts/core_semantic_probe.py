# SPDX-License-Identifier: Apache-2.0
"""Emit one machine-readable observation for a core-semantic safety case."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reference-runtime"))

from aiew_uc.canonical import digest_json
from aiew_uc.model import default_host_policy
from aiew_uc.runtime import UniversalRuntime


def manifest_copy() -> dict:
    return json.loads((ROOT / "examples" / "hello_manifest.json").read_text(encoding="utf-8"))


def observe(case: str) -> dict:
    if case == "nc-sem-01":
        policy = default_host_policy()
        policy["allowedOps"].remove("hash.sha256")
        result = UniversalRuntime(policy).execute(manifest_copy())
        return {
            "case": case,
            "status": result["status"],
            "error": result.get("error", {}).get("code"),
        }
    if case == "nc-sem-02":
        manifest = manifest_copy()
        manifest["nodes"][0]["output"]["epistemic"] = "claim"
        manifest["nodes"][0]["output"]["export"] = False
        result = UniversalRuntime().execute(manifest)
        return {
            "case": case,
            "status": result["status"],
            "error": result.get("error", {}).get("code"),
        }
    if case == "nc-sem-03":
        action_digest = digest_json({"effect": "notify", "target": "bounded-test-sink"})
        decision = UniversalRuntime().evaluate_authority(
            {
                "epistemicStatus": "claim",
                "independentlyValidated": True,
                "effectClass": "consequential",
                "consentRequired": True,
                "actionDigest": action_digest,
                "consentDigest": action_digest,
            },
            {"allowedEffectClasses": ["pure", "consequential"]},
        )
        return {
            "case": case,
            "authorized": decision["authorized"],
            "reasons": decision["reasons"],
        }
    raise ValueError(f"unknown case: {case}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("case", choices=("nc-sem-01", "nc-sem-02", "nc-sem-03"))
    args = parser.parse_args()
    print(json.dumps(observe(args.case), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
