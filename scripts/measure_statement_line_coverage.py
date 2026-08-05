# SPDX-License-Identifier: Apache-2.0
"""Measure deterministic AST statement-line coverage with the Python tracer."""

from __future__ import annotations

import argparse
import ast
import io
import json
import os
import sys
import unittest
from collections import defaultdict
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = (ROOT / "reference-runtime").resolve()
TESTS = (ROOT / "tests").resolve()
sys.path.insert(0, str(RUNTIME))


def statement_lines(path: Path) -> set[int]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.stmt) and hasattr(node, "lineno")
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "evidence" / "statement-line-coverage.json",
    )
    args = parser.parse_args()
    tracked_files = sorted(
        [
            *RUNTIME.glob("aiew_uc/*.py"),
            *RUNTIME.glob("aiew_gateway/*.py"),
        ]
    )
    executed: dict[Path, set[int]] = defaultdict(set)

    def tracer(frame, event, arg):
        if event == "line":
            path = Path(frame.f_code.co_filename).resolve()
            if path in tracked_files:
                executed[path].add(frame.f_lineno)
        return tracer

    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.discover(str(TESTS))
    import aiew_uc.runtime as runtime_module

    with patch.object(runtime_module.time, "monotonic_ns", return_value=0):
        sys.settrace(tracer)
        try:
            result = unittest.TextTestRunner(stream=stream, verbosity=1).run(suite)
        finally:
            sys.settrace(None)
    if not result.wasSuccessful():
        print(stream.getvalue(), end="")
        return 1

    files = []
    total_statements = 0
    total_covered = 0
    for path in tracked_files:
        statements = statement_lines(path)
        covered = statements & executed[path]
        total_statements += len(statements)
        total_covered += len(covered)
        files.append(
            {
                "path": path.relative_to(ROOT).as_posix(),
                "statementLines": len(statements),
                "coveredStatementLines": len(covered),
                "percent": round(100 * len(covered) / len(statements), 2) if statements else 100.0,
                "uncoveredLines": sorted(statements - covered),
            }
        )

    payload = {
        "method": "Python sys.settrace line events intersected with unique ast.stmt source lines",
        "timingTreatment": (
            "The monotonic clock is frozen only during traced coverage measurement "
            "to prevent instrumentation overhead from consuming U0 wall budgets."
        ),
        "branchCoverage": "NOT_MEASURED",
        "testsRun": result.testsRun,
        "statementLines": total_statements,
        "coveredStatementLines": total_covered,
        "percent": round(100 * total_covered / total_statements, 2),
        "files": files,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        f"STATEMENT-LINE COVERAGE: {total_covered}/{total_statements} "
        f"({payload['percent']:.2f}%), {result.testsRun} tests"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
