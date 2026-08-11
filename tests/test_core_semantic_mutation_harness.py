# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations

import ast
import unittest
from pathlib import Path

from scripts.run_core_semantic_mutations import MUTATIONS, mutate_source


ROOT = Path(__file__).resolve().parents[1]
NC_SEM_01 = next(item for item in MUTATIONS if item.case == "nc-sem-01")


class CoreSemanticMutationHarnessTests(unittest.TestCase):
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
