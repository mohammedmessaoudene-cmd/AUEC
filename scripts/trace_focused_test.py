# SPDX-License-Identifier: Apache-2.0
"""Run one unittest while recording executed runtime source lines."""

from __future__ import annotations

import argparse
import io
import json
import sys
import unittest
from collections import defaultdict
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = (ROOT / "reference-runtime").resolve()
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(RUNTIME))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("test")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    executed: dict[str, set[int]] = defaultdict(set)

    def tracer(frame, event, arg):
        if event == "line":
            path = Path(frame.f_code.co_filename).resolve()
            try:
                rel = path.relative_to(ROOT).as_posix()
            except ValueError:
                return tracer
            if path.is_relative_to(RUNTIME):
                executed[rel].add(frame.f_lineno)
        return tracer

    stream = io.StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromName(args.test)
    import aiew_uc.runtime as runtime_module

    with patch.object(runtime_module.time, "monotonic_ns", return_value=0):
        sys.settrace(tracer)
        try:
            result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
        finally:
            sys.settrace(None)

    unittest_output = stream.getvalue().replace(str(ROOT), "<CANDIDATE_ROOT>")
    payload = {
        "test": args.test,
        "success": result.wasSuccessful(),
        "testsRun": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(result.skipped),
        "executedLines": {
            path: sorted(lines)
            for path, lines in sorted(executed.items())
        },
        "unittestOutput": unittest_output,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(unittest_output, end="")
    print(json.dumps({key: payload[key] for key in ("test", "success", "testsRun")}, sort_keys=True))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
