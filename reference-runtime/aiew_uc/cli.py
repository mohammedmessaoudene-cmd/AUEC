# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .canonical import canonical_json_text, strict_json_load
from .runtime import UniversalRuntime, default_host_policy
from .store import ExecutionStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aiew-uc", description="AIEW Universal Execution Contract reference CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    execute = sub.add_parser("execute")
    execute.add_argument("manifest")
    execute.add_argument("--policy")
    execute.add_argument("--store")
    validate = sub.add_parser("validate")
    validate.add_argument("manifest")
    validate.add_argument("--policy")
    canonical = sub.add_parser("canonicalize")
    canonical.add_argument("json_file")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "canonicalize":
        print(canonical_json_text(strict_json_load(args.json_file)))
        return 0
    policy = strict_json_load(args.policy) if args.policy else default_host_policy()
    runtime = UniversalRuntime(policy)
    manifest = strict_json_load(args.manifest, max_bytes=policy["budgets"]["maxManifestBytes"])
    if args.command == "validate":
        result = runtime.execute(manifest)
        print(canonical_json_text({"valid": result.get("status") != "rejected", "result": result}))
        return 0 if result.get("status") != "rejected" else 2
    if args.store:
        result = ExecutionStore(Path(args.store)).execute_once(runtime, manifest)
    else:
        result = runtime.execute(manifest)
    print(canonical_json_text(result))
    return 0 if result.get("status") == "succeeded" else 2


if __name__ == "__main__":
    raise SystemExit(main())
