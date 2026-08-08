# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reference-runtime"))

from aiew_gateway.server import _validated_response_header  # noqa: E402


class GatewaySecurityTests(unittest.TestCase):
    def test_safe_response_header_is_preserved(self) -> None:
        self.assertEqual(
            _validated_response_header("Mcp-Session-Id", "aiew-0123456789"),
            ("Mcp-Session-Id", "aiew-0123456789"),
        )

    def test_response_header_value_rejects_crlf(self) -> None:
        with self.assertRaises(ValueError):
            _validated_response_header(
                "Mcp-Session-Id", "aiew-safe\r\nX-Injected: true"
            )

    def test_response_header_name_rejects_colon_and_crlf(self) -> None:
        with self.assertRaises(ValueError):
            _validated_response_header("X-Safe:\r\nX-Injected", "value")


if __name__ == "__main__":
    unittest.main()
