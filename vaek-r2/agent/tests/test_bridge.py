import json
import unittest

from reference_bridge import BridgeRejected, compile_request


H = "0x" + "11" * 32
A = "0x" + "aa" * 32
R = "0x" + "bb" * 32


def valid_transfer() -> dict:
    return {
        "schemaVersion": "0.2", "effectType": "TRANSFER_ERC20", "executionId": H,
        "mandateId": H, "nonce": "1", "validAfter": "1", "deadline": "2",
        "observationHash": H, "modelCommitment": H, "policyCommitment": H,
        "contextHash": H, "payload": {"assetId": A, "recipientId": R, "requestedAmount": "20"},
    }


class BridgeTests(unittest.TestCase):
    def test_valid_request_is_canonical_and_catalog_bound(self):
        obj, encoded = compile_request(json.dumps(valid_transfer()), {"assetId": {A}, "recipientId": {R}})
        self.assertEqual(obj["payload"]["requestedAmount"], "20")
        self.assertEqual(encoded, json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("ascii"))

    def test_duplicate_key_rejected(self):
        raw = json.dumps(valid_transfer())[:-1] + ',"effectType":"SWAP_EXACT_INPUT"}'
        with self.assertRaises(BridgeRejected):
            compile_request(raw, {"assetId": {A}, "recipientId": {R}})

    def test_hidden_calldata_rejected(self):
        obj = valid_transfer()
        obj["payload"]["calldata"] = "0xdeadbeef"
        with self.assertRaises(BridgeRejected):
            compile_request(json.dumps(obj), {"assetId": {A}, "recipientId": {R}})

    def test_float_and_json_number_rejected(self):
        obj = valid_transfer()
        obj["payload"]["requestedAmount"] = 1.5
        with self.assertRaises(BridgeRejected):
            compile_request(json.dumps(obj), {"assetId": {A}, "recipientId": {R}})

    def test_scientific_notation_string_rejected(self):
        obj = valid_transfer()
        obj["payload"]["requestedAmount"] = "1e6"
        with self.assertRaises(BridgeRejected):
            compile_request(json.dumps(obj), {"assetId": {A}, "recipientId": {R}})

    def test_unknown_resource_id_rejected(self):
        with self.assertRaises(BridgeRejected):
            compile_request(json.dumps(valid_transfer()), {"assetId": set(), "recipientId": {R}})

    def test_adapter_address_rejected(self):
        obj = valid_transfer()
        obj["adapterAddress"] = "0x" + "12" * 20
        with self.assertRaises(BridgeRejected):
            compile_request(json.dumps(obj), {"assetId": {A}, "recipientId": {R}})

    def test_uint128_overflow_rejected(self):
        obj = valid_transfer()
        obj["payload"]["requestedAmount"] = str(2**128)
        with self.assertRaises(BridgeRejected):
            compile_request(json.dumps(obj), {"assetId": {A}, "recipientId": {R}})


if __name__ == "__main__":
    unittest.main()

