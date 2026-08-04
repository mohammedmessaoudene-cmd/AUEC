# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_style_module():
    path = ROOT / "scripts" / "style_audit.py"
    spec = importlib.util.spec_from_file_location("auec_style_audit", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AuditRegressionTests(unittest.TestCase):
    def test_recursive_input_fallback(self) -> None:
        module = load_style_module()
        with tempfile.TemporaryDirectory(prefix="auec-style-") as temp:
            root = Path(temp)
            (root / "main.tex").write_text(
                "before\n\\input{child}\nafter\n", encoding="utf-8"
            )
            (root / "child.tex").write_text(
                "middle\n\\input{leaf}\n", encoding="utf-8"
            )
            (root / "leaf.tex").write_text("leaf\n", encoding="utf-8")
            expanded = module.expand_inputs(root / "main.tex")
        self.assertIn("before", expanded)
        self.assertIn("middle", expanded)
        self.assertIn("leaf", expanded)
        self.assertNotIn("\\input", expanded)

    def test_cyclic_input_is_rejected(self) -> None:
        module = load_style_module()
        with tempfile.TemporaryDirectory(prefix="auec-style-cycle-") as temp:
            root = Path(temp)
            (root / "a.tex").write_text("\\input{b}", encoding="utf-8")
            (root / "b.tex").write_text("\\input{a}", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                module.expand_inputs(root / "a.tex")

    def test_plain_text_fallback_preserves_visible_prose(self) -> None:
        module = load_style_module()
        source = r"\section{Method} Visible \textbf{evidence} \cite{Example}."
        plain = module.latex_to_plain_fallback(source)
        self.assertIn("Method", plain)
        self.assertIn("Visible", plain)
        self.assertIn("evidence", plain)
        self.assertNotIn(r"\textbf", plain)

    def test_nonlocal_tex_input_is_ignored(self) -> None:
        module = load_style_module()
        with tempfile.TemporaryDirectory(prefix="auec-style-system-input-") as temp:
            root = Path(temp)
            (root / "main.tex").write_text(
                "before\n\\input{system-distribution-file}\nafter\n",
                encoding="utf-8",
            )
            expanded = module.expand_inputs(root / "main.tex")
        self.assertIn("before", expanded)
        self.assertIn("after", expanded)
        self.assertNotIn("\\input", expanded)


if __name__ == "__main__":
    unittest.main()
