# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations

import json
import sys
import threading
import unittest
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reference-runtime"))

from aiew_gateway.server import create_server, main
from aiew_gateway.source_offer import require_exact_source_offer, source_offer_payload


class SourceOfferTests(unittest.TestCase):
    def test_prepublication_offer_is_explicitly_not_exact(self) -> None:
        payload = source_offer_payload()
        self.assertEqual(payload["license"], "AGPL-3.0-only")
        self.assertFalse(payload["exactCorrespondingSource"])
        self.assertEqual(payload["status"], "prepublication-unassigned")
        self.assertIsNone(payload["sourceReleaseUrl"])

    def test_modified_build_requires_a_notice(self) -> None:
        with self.assertRaises(RuntimeError):
            source_offer_payload(modified=True, modification_notice="")

    def test_exact_offer_can_be_verified(self) -> None:
        payload = source_offer_payload(
            source_url="https://example.invalid/auec/releases/v0.36.0-prestandard",
            source_ref="v0.36.0-prestandard",
            source_sha256="a" * 64,
            modified=True,
            modification_notice="local test fixture",
        )
        self.assertTrue(payload["exactCorrespondingSource"])

    def test_http_source_endpoint_matches_library_payload(self) -> None:
        server = create_server()
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            host, port = server.server_address
            with urllib.request.urlopen(f"http://{host}:{port}/source", timeout=5) as response:
                payload = json.loads(response.read())
            self.assertEqual(payload, source_offer_payload())
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_cli_source_offer_exits_without_starting_server(self) -> None:
        self.assertEqual(main(["--source-offer"]), 0)

    def test_http_source_endpoint_is_not_exact(self) -> None:
        payload = source_offer_payload(
            source_url="http://example.invalid/source.zip",
            source_ref="v0.36.0-prestandard",
            source_sha256="b" * 64,
        )
        self.assertFalse(payload["exactCorrespondingSource"])

    def test_exact_source_offer_guard_rejects_unassigned_coordinates(self) -> None:
        with self.assertRaises(RuntimeError):
            require_exact_source_offer()

    def test_non_loopback_server_rejects_unassigned_offer(self) -> None:
        with self.assertRaises(RuntimeError):
            create_server("0.0.0.0", 0)

    def test_loopback_server_remains_available_for_private_review(self) -> None:
        server = create_server("127.0.0.1", 0)
        server.server_close()


if __name__ == "__main__":
    unittest.main()
