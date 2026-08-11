# SPDX-License-Identifier: Apache-2.0
"""Execute isolated single-mutant causal controls and preserve red/green evidence."""

from __future__ import annotations

import argparse
import ast
import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Mutation:
    case: str
    path: str
    needle: str
    replacement: str
    test: str
    matcher: str = "literal"


HOST_OPERATION_GUARD = re.compile(
    r"""
    (?P<indent>^[\t ]*)if[\t ]*
    (?:\([\t ]*(?:\r?\n)?)?
    [\t ]*not[\t ]+isinstance\([\t ]*op[\t ]*,[\t ]*str[\t ]*\)
    [ \t\r\n]+or[\t ]+op[\t ]+not[\t ]+in[\t ]+PURE_OPS
    [ \t\r\n]+or[\t ]+op[\t ]+not[\t ]+in[\t ]+policy\[
        [\t ]*["']allowedOps["'][\t ]*
    \]
    [ \t\r\n]*(?:\))?[\t ]*:
    """,
    re.MULTILINE | re.VERBOSE,
)


MUTATIONS = (
    Mutation(
        case="nc-sem-01",
        path="reference-runtime/aiew_uc/model.py",
        needle='if not isinstance(op, str) or op not in PURE_OPS or op not in policy["allowedOps"]:',
        replacement="if not isinstance(op, str) or op not in PURE_OPS:",
        test=(
            "test_core_semantic_controls.CoreSemanticCausalControls."
            "test_nc_sem_01_host_allowlist_blocks_requested_operation"
        ),
        matcher="host-operation-guard",
    ),
    Mutation(
        case="nc-sem-02",
        path="reference-runtime/aiew_uc/model.py",
        needle='if output["epistemic"] not in {"fact", "artifact"}:',
        replacement='if output["epistemic"] not in {"fact", "artifact", "claim"}:',
        test=(
            "test_core_semantic_controls.CoreSemanticCausalControls."
            "test_nc_sem_02_u0_claim_output_is_rejected"
        ),
    ),
    Mutation(
        case="nc-sem-03",
        path="reference-runtime/aiew_uc/authority.py",
        needle='status_is_fact = epistemic_status == "fact"',
        replacement='status_is_fact = epistemic_status in {"fact", "claim"}',
        test=(
            "test_core_semantic_controls.CoreSemanticCausalControls."
            "test_nc_sem_03_claim_never_authorizes_consequential_effect"
        ),
    ),
)


def _is_name(node: ast.AST, name: str) -> bool:
    return isinstance(node, ast.Name) and node.id == name


def _is_not_isinstance_op_str(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.UnaryOp)
        and isinstance(node.op, ast.Not)
        and isinstance(node.operand, ast.Call)
        and _is_name(node.operand.func, "isinstance")
        and len(node.operand.args) == 2
        and _is_name(node.operand.args[0], "op")
        and _is_name(node.operand.args[1], "str")
        and not node.operand.keywords
    )


def _is_op_not_in(node: ast.AST, comparator: ast.AST) -> bool:
    return (
        isinstance(node, ast.Compare)
        and _is_name(node.left, "op")
        and len(node.ops) == 1
        and isinstance(node.ops[0], ast.NotIn)
        and len(node.comparators) == 1
        and ast.dump(node.comparators[0], include_attributes=False)
        == ast.dump(comparator, include_attributes=False)
    )


def _host_operation_guard_count(source_text: str) -> int:
    expected_policy = ast.Subscript(
        value=ast.Name(id="policy", ctx=ast.Load()),
        slice=ast.Constant(value="allowedOps"),
        ctx=ast.Load(),
    )
    count = 0
    for node in ast.walk(ast.parse(source_text)):
        if not isinstance(node, ast.If) or not isinstance(node.test, ast.BoolOp):
            continue
        if not isinstance(node.test.op, ast.Or) or len(node.test.values) != 3:
            continue
        first, second, third = node.test.values
        if (
            _is_not_isinstance_op_str(first)
            and _is_op_not_in(second, ast.Name(id="PURE_OPS", ctx=ast.Load()))
            and _is_op_not_in(third, expected_policy)
        ):
            count += 1
    return count


def _remove_host_policy_clause(match: re.Match[str]) -> str:
    indent = match.group("indent")
    matched = match.group(0)
    if "\n" not in matched and "\r" not in matched:
        return f"{indent}if not isinstance(op, str) or op not in PURE_OPS:"
    newline = "\r\n" if "\r\n" in matched else "\n"
    continuation = indent + "    "
    return newline.join(
        (
            f"{indent}if (",
            f"{continuation}not isinstance(op, str)",
            f"{continuation}or op not in PURE_OPS",
            f"{indent}):",
        )
    )


def mutate_source(mutation: Mutation, original_text: str) -> tuple[str, int, int]:
    """Apply exactly one bounded mutation and return text, line and match count."""

    if mutation.matcher == "host-operation-guard":
        syntax_count = _host_operation_guard_count(original_text)
        matches = list(HOST_OPERATION_GUARD.finditer(original_text))
        if syntax_count != 1 or len(matches) != 1:
            raise RuntimeError(
                f"{mutation.case}: host-operation guard is not uniquely selectable "
                f"(syntax={syntax_count}, regex={len(matches)})"
            )
        match = matches[0]
        mutant_text, replacement_count = HOST_OPERATION_GUARD.subn(
            _remove_host_policy_clause,
            original_text,
            count=1,
        )
        ast.parse(mutant_text)
        if replacement_count != 1 or _host_operation_guard_count(mutant_text) != 0:
            raise RuntimeError(
                f"{mutation.case}: host-operation guard mutation was incomplete"
            )
        line_number = original_text.count("\n", 0, match.start()) + 1
        return mutant_text, line_number, replacement_count

    match_count = original_text.count(mutation.needle)
    if match_count != 1:
        raise RuntimeError(f"{mutation.case}: mutation needle count is not exactly one")
    line_number = original_text.count("\n", 0, original_text.index(mutation.needle)) + 1
    mutant_text = original_text.replace(
        mutation.needle,
        mutation.replacement,
        1,
    )
    ast.parse(mutant_text)
    return mutant_text, line_number, match_count


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": str(repo / "reference-runtime"),
        }
    )
    return subprocess.run(
        [sys.executable, *args],
        cwd=repo,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def probe(repo: Path, case: str) -> dict:
    result = run(repo, "scripts/core_semantic_probe.py", case)
    if result.returncode:
        raise RuntimeError(result.stdout)
    return json.loads(result.stdout.strip().splitlines()[-1])


def expected_baseline(case: str, observation: dict) -> bool:
    if case == "nc-sem-01":
        return observation == {
            "case": case,
            "status": "rejected",
            "error": "E_OPERATION",
        }
    if case == "nc-sem-02":
        return observation == {
            "case": case,
            "status": "rejected",
            "error": "E_EPISTEMIC",
        }
    return observation.get("case") == case and observation.get("authorized") is False


def expected_mutant(case: str, observation: dict) -> bool:
    if case in {"nc-sem-01", "nc-sem-02"}:
        return observation == {"case": case, "status": "succeeded", "error": None}
    return observation == {"case": case, "authorized": True, "reasons": []}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "evidence" / "core-semantic-causal-controls",
    )
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    summary: dict[str, object] = {
        "schemaVersion": 1,
        "controls": [],
        "singleMutantIsolation": True,
        "noExternalEffectExecuted": True,
    }

    for mutation in MUTATIONS:
        source = ROOT / mutation.path
        original_text = source.read_text(encoding="utf-8")
        mutant_text, line_number, match_count = mutate_source(
            mutation,
            original_text,
        )
        original_hash = sha256(source)

        baseline_observation = probe(ROOT, mutation.case)
        if not expected_baseline(mutation.case, baseline_observation):
            raise RuntimeError(f"{mutation.case}: baseline observation is not safe")
        baseline_trace = output / f"{mutation.case}-baseline-trace.json"
        baseline_test = run(
            ROOT,
            "scripts/trace_focused_test.py",
            mutation.test,
            "--output",
            str(baseline_trace),
        )
        if baseline_test.returncode:
            raise RuntimeError(
                f"{mutation.case}: baseline safety test failed\n{baseline_test.stdout}"
            )
        baseline_trace_payload = json.loads(baseline_trace.read_text(encoding="utf-8"))
        if line_number not in baseline_trace_payload["executedLines"].get(
            mutation.path, []
        ):
            raise RuntimeError(
                f"{mutation.case}: baseline did not execute the target line"
            )

        with tempfile.TemporaryDirectory(prefix=f"auec-{mutation.case}-") as temporary:
            mutant_root = Path(temporary) / "candidate"
            shutil.copytree(
                ROOT,
                mutant_root,
                ignore=shutil.ignore_patterns(
                    ".git", "__pycache__", "*.pyc", ".pytest_cache"
                ),
            )
            mutant_source = mutant_root / mutation.path
            mutant_source.write_text(mutant_text, encoding="utf-8", newline="\n")
            if sha256(mutant_source) == original_hash:
                raise RuntimeError(
                    f"{mutation.case}: mutation did not change the source hash"
                )

            diff = "".join(
                difflib.unified_diff(
                    original_text.splitlines(keepends=True),
                    mutant_text.splitlines(keepends=True),
                    fromfile=f"a/{mutation.path}",
                    tofile=f"b/{mutation.path}",
                )
            )
            (output / f"{mutation.case}.diff").write_text(
                diff, encoding="utf-8", newline="\n"
            )

            mutant_observation = probe(mutant_root, mutation.case)
            if not expected_mutant(mutation.case, mutant_observation):
                raise RuntimeError(f"{mutation.case}: mutant did not enable the attack")
            mutant_trace_temp = mutant_root / "mutant-trace.json"
            mutant_test = run(
                mutant_root,
                "scripts/trace_focused_test.py",
                mutation.test,
                "--output",
                str(mutant_trace_temp),
            )
            if mutant_test.returncode == 0:
                raise RuntimeError(
                    f"{mutation.case}: safety test stayed green under mutation"
                )
            mutant_trace_payload = json.loads(
                mutant_trace_temp.read_text(encoding="utf-8")
            )
            if line_number not in mutant_trace_payload["executedLines"].get(
                mutation.path, []
            ):
                raise RuntimeError(
                    f"{mutation.case}: mutant test did not execute the target line"
                )
            shutil.copyfile(
                mutant_trace_temp, output / f"{mutation.case}-mutant-red-trace.json"
            )
            (output / f"{mutation.case}-mutant-red.txt").write_text(
                mutant_test.stdout,
                encoding="utf-8",
                newline="\n",
            )

        if sha256(source) != original_hash:
            raise RuntimeError(
                f"{mutation.case}: original source changed after temporary mutation"
            )
        restored_observation = probe(ROOT, mutation.case)
        restored_trace = output / f"{mutation.case}-restored-trace.json"
        restored_test = run(
            ROOT,
            "scripts/trace_focused_test.py",
            mutation.test,
            "--output",
            str(restored_trace),
        )
        if restored_test.returncode or not expected_baseline(
            mutation.case, restored_observation
        ):
            raise RuntimeError(f"{mutation.case}: restoration was not green")

        summary["controls"].append(
            {
                "id": mutation.case.upper(),
                "source": mutation.path,
                "targetLine": line_number,
                "originalSha256": original_hash,
                "mutationNeedleCount": match_count,
                "baseline": baseline_observation,
                "mutant": mutant_observation,
                "safetyTestUnderMutant": "RED",
                "targetLineExecuted": True,
                "restored": restored_observation,
                "restorationTest": "GREEN",
            }
        )

    summary["verdict"] = "PASS"
    (output / "mutation-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print("CORE SEMANTIC MUTATION CONTROLS PASS: 3/3 red then green")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
