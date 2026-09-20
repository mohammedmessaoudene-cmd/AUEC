import importlib.util
import unittest
from pathlib import Path


class SourceGuardTests(unittest.TestCase):
    def test_prohibited_surface_scan_passes(self):
        path = Path(__file__).resolve().parents[2] / "tools" / "check_prohibited_surfaces.py"
        spec = importlib.util.spec_from_file_location("guard", path)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
        self.assertEqual(module.main(), 0)


if __name__ == "__main__":
    unittest.main()

