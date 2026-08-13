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
TARGET_COVERAGE_RULE = "guard-evaluation-span-overlap"


@dataclass(frozen=True)
class Mutation:
    case: str
    path: str
    needle: str
    replacement: str
    test: str
    matcher: str = "literal"


@dataclass(frozen=True)
class MutationTarget:
    """Immutable source span whose evaluation makes a control causally relevant."""

    start_line: int
    end_line: int
    candidate_lines: tuple[int, ...]
    selection_kind: str

    def __post_init__(self) -> None:
        expected = tuple(range(self.start_line, self.end_line + 1))
        if self.start_line < 1 or self.end_line < self.start_line:
            raise ValueError("mutation target span is invalid")
        if self.candidate_lines != expected:
            raise ValueError("mutation target candidate lines do not match its span")


@dataclass(frozen=True)
class PreparedMutation:
    """Mutated text plus independently selected targets for each source phase."""

    mutant_text: str
    original_target: MutationTarget
    mutant_target: MutationTarget
    match_count: int


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


def _host_operation_guard_nodes(
    source_text: str, *, includes_policy_clause: bool
) -> list[ast.If]:
    expected_policy = ast.Subscript(
        value=ast.Name(id="policy", ctx=ast.Load()),
        slice=ast.Constant(value="allowedOps"),
        ctx=ast.Load(),
    )
    matches: list[ast.If] = []
    for node in ast.walk(ast.parse(source_text)):
        if not isinstance(node, ast.If) or not isinstance(node.test, ast.BoolOp):
            continue
        expected_value_count = 3 if includes_policy_clause else 2
        if (
            not isinstance(node.test.op, ast.Or)
            or len(node.test.values) != expected_value_count
        ):
            continue
        first, second = node.test.values[:2]
        if not (
            _is_not_isinstance_op_str(first)
            and _is_op_not_in(second, ast.Name(id="PURE_OPS", ctx=ast.Load()))
        ):
            continue
        if includes_policy_clause and not _is_op_not_in(
            node.test.values[2], expected_policy
        ):
            continue
        matches.append(node)
    return matches


def _host_operation_guard_count(source_text: str) -> int:
    return len(
        _host_operation_guard_nodes(source_text, includes_policy_clause=True)
    )


def _target_from_if(node: ast.If, selection_kind: str) -> MutationTarget:
    test_end_line = node.test.end_lineno
    if test_end_line is None:
        raise RuntimeError("host-operation guard test has no end line")
    return MutationTarget(
        start_line=node.lineno,
        end_line=test_end_line,
        candidate_lines=tuple(range(node.lineno, test_end_line + 1)),
        selection_kind=selection_kind,
    )


def _literal_target(
    source_text: str, start_offset: int, selected_text: str, selection_kind: str
) -> MutationTarget:
    end_offset = start_offset + len(selected_text) - 1
    start_line = source_text.count("\n", 0, start_offset) + 1
    end_line = source_text.count("\n", 0, end_offset) + 1
    return MutationTarget(
        start_line=start_line,
        end_line=end_line,
        candidate_lines=tuple(range(start_line, end_line + 1)),
        selection_kind=selection_kind,
    )


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


def target_observed_lines(
    target: MutationTarget, executed_lines: list[int] | tuple[int, ...] | set[int]
) -> tuple[int, ...]:
    """Return traced lines that overlap the selected evaluation span."""

    return tuple(sorted(set(target.candidate_lines).intersection(executed_lines)))


def prepare_mutation_with_targets(
    mutation: Mutation, original_text: str
) -> PreparedMutation:
    """Apply one mutation and select original/mutant targets independently."""

    if mutation.matcher == "host-operation-guard":
        syntax_matches = _host_operation_guard_nodes(
            original_text, includes_policy_clause=True
        )
        syntax_count = len(syntax_matches)
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
        mutant_syntax_matches = _host_operation_guard_nodes(
            mutant_text, includes_policy_clause=False
        )
        if len(mutant_syntax_matches) != 1:
            raise RuntimeError(
                f"{mutation.case}: mutant host-operation guard is not uniquely "
                f"selectable (syntax={len(mutant_syntax_matches)})"
            )
        return PreparedMutation(
            mutant_text=mutant_text,
            original_target=_target_from_if(
                syntax_matches[0], "ast-if-test"
            ),
            mutant_target=_target_from_if(
                mutant_syntax_matches[0], "ast-if-test-mutant-two-clause"
            ),
            match_count=replacement_count,
        )

    match_count = original_text.count(mutation.needle)
    if match_count != 1:
        raise RuntimeError(f"{mutation.case}: mutation needle count is not exactly one")
    match_start = original_text.index(mutation.needle)
    mutant_text = original_text.replace(
        mutation.needle,
        mutation.replacement,
        1,
    )
    ast.parse(mutant_text)
    return PreparedMutation(
        mutant_text=mutant_text,
        original_target=_literal_target(
            original_text, match_start, mutation.needle, "literal"
        ),
        mutant_target=_literal_target(
            mutant_text, match_start, mutation.replacement, "literal-mutant"
        ),
        match_count=match_count,
    )


def prepare_mutation(
    mutation: Mutation, original_text: str
) -> tuple[str, MutationTarget, int]:
    """Compatibility wrapper returning the original-phase target descriptor."""

    prepared = prepare_mutation_with_targets(mutation, original_text)
    return prepared.mutant_text, prepared.original_target, prepared.match_count


def mutate_source(mutation: Mutation, original_text: str) -> tuple[str, int, int]:
    """Compatibility wrapper returning text, legacy targetLine and match count."""

    mutant_text, target, match_count = prepare_mutation(mutation, original_text)
    return mutant_text, target.start_line, match_count


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
        prepared = prepare_mutation_with_targets(
            mutation,
            original_text,
        )
        mutant_text = prepared.mutant_text
        target = prepared.original_target
        mutant_target = prepared.mutant_target
        match_count = prepared.match_count
        line_number = target.start_line
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
        baseline_executed_lines = baseline_trace_payload["executedLines"].get(
            mutation.path, []
        )
        baseline_observed_lines = target_observed_lines(
            target, baseline_executed_lines
        )
        if not baseline_observed_lines:
            raise RuntimeError(
                f"{mutation.case}: baseline did not evaluate the target span"
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
            mutant_executed_lines = mutant_trace_payload["executedLines"].get(
                mutation.path, []
            )
            mutant_observed_lines = target_observed_lines(
                mutant_target, mutant_executed_lines
            )
            if not mutant_observed_lines:
                raise RuntimeError(
                    f"{mutation.case}: mutant test did not evaluate the target span"
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
        restored_trace_payload = json.loads(
            restored_trace.read_text(encoding="utf-8")
        )
        restored_executed_lines = restored_trace_payload["executedLines"].get(
            mutation.path, []
        )
        restored_observed_lines = target_observed_lines(
            target, restored_executed_lines
        )
        if not restored_observed_lines:
            raise RuntimeError(
                f"{mutation.case}: restoration did not evaluate the target span"
            )

        summary["controls"].append(
            {
                "id": mutation.case.upper(),
                "source": mutation.path,
                "targetLine": line_number,
                "targetLineStart": target.start_line,
                "targetLineEnd": target.end_line,
                "targetCandidateLines": list(target.candidate_lines),
                "targetObservedLines": list(baseline_observed_lines),
                "targetCoverageRule": TARGET_COVERAGE_RULE,
                "targetSelectionKind": target.selection_kind,
                "mutantTargetLineStart": mutant_target.start_line,
                "mutantTargetLineEnd": mutant_target.end_line,
                "mutantTargetCandidateLines": list(
                    mutant_target.candidate_lines
                ),
                "mutantTargetSelectionKind": mutant_target.selection_kind,
                "originalSha256": original_hash,
                "mutationNeedleCount": match_count,
                "baseline": baseline_observation,
                "mutant": mutant_observation,
                "safetyTestUnderMutant": "RED",
                "targetLineExecuted": line_number in baseline_executed_lines,
                "targetSpanExecuted": True,
                "mutantTargetObservedLines": list(mutant_observed_lines),
                "restored": restored_observation,
                "restorationTest": "GREEN",
                "restoredTargetObservedLines": list(restored_observed_lines),
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
