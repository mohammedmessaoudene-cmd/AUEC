# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations

import ast
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.run_core_semantic_mutations import (
    MUTATIONS,
    TARGET_COVERAGE_RULE,
    mutate_source,
    prepare_mutation,
    prepare_mutation_with_targets,
    target_observed_lines,
)


ROOT = Path(__file__).resolve().parents[1]
NC_SEM_01 = next(item for item in MUTATIONS if item.case == "nc-sem-01")
MULTILINE_GUARD = (
    "if (\n"
    "    not isinstance(op, str)\n"
    "    or op not in PURE_OPS\n"
    '    or op not in policy["allowedOps"]\n'
    "):\n"
    "    raise RuntimeError\n"
)
MULTILINE_GUARD_WITH_ELSE = MULTILINE_GUARD + "else:\n    pass\n"


class CoreSemanticMutationHarnessTests(unittest.TestCase):
    def test_real_summary_emits_exact_target_coverage_rule(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auec-summary-contract-") as temp:
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "scripts/run_core_semantic_mutations.py",
                    "--output",
                    temp,
                ],
                cwd=ROOT,
                text=True,
                encoding="utf-8",
                errors="replace",
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            self.assertEqual(result.returncode, 0, result.stdout)
            summary = json.loads(
                (Path(temp) / "mutation-summary.json").read_text(encoding="utf-8")
            )
        self.assertEqual(len(summary["controls"]), len(MUTATIONS))
        self.assertTrue(
            all(
                control.get("targetCoverageRule") == TARGET_COVERAGE_RULE
                for control in summary["controls"]
            )
        )
        self.assertEqual(TARGET_COVERAGE_RULE, "guard-evaluation-span-overlap")

    def test_multiline_repository_guard_is_selected_once(self) -> None:
        source = (ROOT / NC_SEM_01.path).read_text(encoding="utf-8")
        mutant, line_number, count = mutate_source(NC_SEM_01, source)
        ast.parse(mutant)
        self.assertEqual(count, 1)
        self.assertGreater(line_number, 0)
        self.assertIn("or op not in policy", source)
        self.assertNotIn("or op not in policy", mutant)

    def test_single_line_guard_is_selected_once(self) -> None:
        source = (
            "if not isinstance(op, str) or op not in PURE_OPS "
            'or op not in policy["allowedOps"]:\n'
            "    raise RuntimeError\n"
        )
        mutant, line_number, count = mutate_source(NC_SEM_01, source)
        ast.parse(mutant)
        self.assertEqual(count, 1)
        self.assertEqual(line_number, 1)
        self.assertEqual(
            mutant.splitlines()[0],
            "if not isinstance(op, str) or op not in PURE_OPS:",
        )

    def test_multiline_guard_span_excludes_closing_line_and_body(self) -> None:
        _, target, count = prepare_mutation(NC_SEM_01, MULTILINE_GUARD)
        self.assertEqual(count, 1)
        self.assertEqual(target.start_line, 1)
        self.assertEqual(target.end_line, 4)
        self.assertEqual(target.candidate_lines, (1, 2, 3, 4))
        self.assertEqual(target.selection_kind, "ast-if-test")

    def test_opening_line_alone_proves_guard_evaluation(self) -> None:
        _, target, _ = prepare_mutation(NC_SEM_01, MULTILINE_GUARD)
        self.assertEqual(target_observed_lines(target, [1]), (1,))

    def test_operand_line_alone_proves_guard_evaluation(self) -> None:
        _, target, _ = prepare_mutation(NC_SEM_01, MULTILINE_GUARD)
        self.assertEqual(target_observed_lines(target, [3]), (3,))

    def test_multiple_operand_lines_prove_guard_evaluation(self) -> None:
        _, target, _ = prepare_mutation(NC_SEM_01, MULTILINE_GUARD)
        self.assertEqual(target_observed_lines(target, [2, 3, 4]), (2, 3, 4))

    def test_body_line_alone_does_not_prove_guard_evaluation(self) -> None:
        _, target, _ = prepare_mutation(NC_SEM_01, MULTILINE_GUARD)
        self.assertEqual(target_observed_lines(target, [6]), ())

    def test_closing_line_alone_does_not_prove_guard_evaluation(self) -> None:
        _, target, _ = prepare_mutation(NC_SEM_01, MULTILINE_GUARD)
        self.assertEqual(target_observed_lines(target, [5]), ())

    def test_actual_mutant_closing_line_does_not_prove_evaluation(self) -> None:
        prepared = prepare_mutation_with_targets(NC_SEM_01, MULTILINE_GUARD)
        mutant_if = ast.parse(prepared.mutant_text).body[0]
        self.assertIsInstance(mutant_if, ast.If)
        closing_line = prepared.mutant_target.end_line + 1
        self.assertEqual(
            prepared.mutant_text.splitlines()[closing_line - 1].strip(), "):"
        )
        self.assertEqual(
            prepared.mutant_target.end_line, mutant_if.test.end_lineno
        )
        self.assertIn(closing_line, prepared.original_target.candidate_lines)
        self.assertNotIn(closing_line, prepared.mutant_target.candidate_lines)
        self.assertEqual(
            target_observed_lines(prepared.mutant_target, [closing_line]), ()
        )

    def test_mutant_phase_selector_fails_closed_on_ambiguity(self) -> None:
        existing_two_clause_guard = (
            "if not isinstance(op, str) or op not in PURE_OPS:\n"
            "    raise RuntimeError\n"
        )
        with self.assertRaisesRegex(
            RuntimeError, "mutant host-operation guard is not uniquely selectable"
        ):
            prepare_mutation_with_targets(
                NC_SEM_01, MULTILINE_GUARD + existing_two_clause_guard
            )

    def test_else_line_alone_does_not_prove_guard_evaluation(self) -> None:
        _, target, _ = prepare_mutation(NC_SEM_01, MULTILINE_GUARD_WITH_ELSE)
        self.assertEqual(target_observed_lines(target, [8]), ())

    def test_if_end_line_would_include_body_and_else(self) -> None:
        tree = ast.parse(MULTILINE_GUARD_WITH_ELSE)
        selected_if = tree.body[0]
        self.assertIsInstance(selected_if, ast.If)
        _, target, _ = prepare_mutation(NC_SEM_01, MULTILINE_GUARD_WITH_ELSE)
        self.assertEqual(target.end_line, selected_if.test.end_lineno)
        self.assertGreater(selected_if.end_lineno, target.end_line)
        self.assertNotIn(selected_if.end_lineno, target.candidate_lines)

    def test_no_guard_line_does_not_prove_guard_evaluation(self) -> None:
        _, target, _ = prepare_mutation(NC_SEM_01, MULTILINE_GUARD)
        self.assertEqual(target_observed_lines(target, []), ())

    def test_single_line_guard_span_accepts_its_only_line(self) -> None:
        source = (
            "if not isinstance(op, str) or op not in PURE_OPS "
            'or op not in policy["allowedOps"]:\n'
            "    raise RuntimeError\n"
        )
        _, target, _ = prepare_mutation(NC_SEM_01, source)
        self.assertEqual(target.candidate_lines, (1,))
        self.assertEqual(target_observed_lines(target, [1]), (1,))

    def test_duplicate_guards_fail_closed(self) -> None:
        guard = (
            "if not isinstance(op, str) or op not in PURE_OPS "
            'or op not in policy["allowedOps"]:\n'
            "    raise RuntimeError\n"
        )
        with self.assertRaisesRegex(RuntimeError, "not uniquely selectable"):
            mutate_source(NC_SEM_01, guard + guard)

    def test_partial_lookalike_is_not_selected(self) -> None:
        lookalike = 'if op not in policy["allowedOps"]:\n    raise RuntimeError\n'
        with self.assertRaisesRegex(RuntimeError, "not uniquely selectable"):
            mutate_source(NC_SEM_01, lookalike)


if __name__ == "__main__":
    unittest.main()
