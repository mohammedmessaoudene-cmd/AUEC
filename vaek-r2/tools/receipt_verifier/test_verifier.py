import copy
import json
import unittest
from pathlib import Path

from verifier import ReceiptRejected, recompute_receipt_hash, verify_document


FIXTURE = Path(__file__).with_name("fixtures") / "receipt_transfer.json"


class ReceiptVerifierTests(unittest.TestCase):
    def setUp(self):
        self.document = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_golden_receipt_validates(self):
        self.assertTrue(verify_document(self.document))

    def test_golden_hash_is_reproduced(self):
        self.assertEqual(recompute_receipt_hash(self.document), self.document["receiptHash"])

    def test_tamper_corpus_rejected(self):
        mutations = {
            "requestedHash": "0x" + "91" * 32,
            "authorizedHash": "0x" + "92" * 32,
            "executedHash": "0x" + "93" * 32,
            "adapterVersion": "2",
            "resourceRegistryVersion": "9",
            "actualOutput": "49",
            "blockNumber": "78",
        }
        for field, replacement in mutations.items():
            with self.subTest(field=field):
                changed = copy.deepcopy(self.document)
                changed[field] = replacement
                self.assertFalse(verify_document(changed))

    def test_unknown_field_rejected(self):
        changed = copy.deepcopy(self.document)
        changed["privateDatabaseRow"] = "trusted"
        with self.assertRaises(ReceiptRejected):
            recompute_receipt_hash(changed)


if __name__ == "__main__":
    unittest.main()

