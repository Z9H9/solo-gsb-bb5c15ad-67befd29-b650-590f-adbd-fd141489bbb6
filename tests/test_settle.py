"""HTTP-level tests for POST /settle (require fastapi + httpx installed)."""

import unittest

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

PAYLOAD = {
    "segments": [100, 251, 80],
    "passengers": [
        {"id": "alice", "board": 0, "alight": 3},
        {"id": "bob", "board": 1, "alight": 3},
        {"id": "carol", "board": 0, "alight": 1},
    ],
    "payments": [
        {"id": "alice", "amount": 250},
        {"id": "bob", "amount": 100},
        {"id": "carol", "amount": 81},
    ],
}


class SettleApiTests(unittest.TestCase):
    def test_settle_ok(self):
        resp = client.post("/settle", json=PAYLOAD)
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        # owed amounts come straight from the /split computation
        self.assertEqual(body["owed"], {"alice": 216, "bob": 165, "carol": 50})
        self.assertEqual(body["paid"], {"alice": 250, "bob": 100, "carol": 81})
        self.assertEqual(body["balance"], {"alice": 34, "bob": -65, "carol": 31})
        self.assertEqual(
            body["transfers"],
            [
                {"from": "bob", "to": "alice", "amount": 34},
                {"from": "bob", "to": "carol", "amount": 31},
            ],
        )

    def test_input_order_does_not_matter(self):
        shuffled = dict(
            PAYLOAD,
            passengers=list(reversed(PAYLOAD["passengers"])),
            payments=list(reversed(PAYLOAD["payments"])),
        )
        r1 = client.post("/settle", json=PAYLOAD)
        r2 = client.post("/settle", json=shuffled)
        self.assertEqual(r1.status_code, r2.status_code)
        self.assertEqual(r1.json(), r2.json())

    def test_transfers_settle_every_balance(self):
        resp = client.post("/settle", json=PAYLOAD)
        balance = resp.json()["balance"]
        for t in resp.json()["transfers"]:
            self.assertGreater(t["amount"], 0)
            self.assertLess(balance[t["from"]], 0)
            self.assertGreater(balance[t["to"]], 0)
            balance[t["from"]] += t["amount"]
            balance[t["to"]] -= t["amount"]
        self.assertTrue(all(v == 0 for v in balance.values()))

    def test_minimal_transfer_count(self):
        # Two disjoint zero-sum groups -> exactly 2 transfers.
        payload = {
            "segments": [30, 70],
            "passengers": [
                {"id": "a", "board": 0, "alight": 1},
                {"id": "b", "board": 0, "alight": 1},
                {"id": "c", "board": 1, "alight": 2},
                {"id": "d", "board": 1, "alight": 2},
            ],
            "payments": [
                {"id": "a", "amount": 0},
                {"id": "b", "amount": 30},
                {"id": "c", "amount": 70},
                {"id": "d", "amount": 0},
            ],
        }
        resp = client.post("/settle", json=payload)
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(
            resp.json()["transfers"],
            [
                {"from": "a", "to": "b", "amount": 15},
                {"from": "d", "to": "c", "amount": 35},
            ],
        )

    def test_exact_payments_give_no_transfers(self):
        payload = dict(
            PAYLOAD,
            payments=[
                {"id": "alice", "amount": 216},
                {"id": "bob", "amount": 165},
                {"id": "carol", "amount": 50},
            ],
        )
        resp = client.post("/settle", json=payload)
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["balance"], {"alice": 0, "bob": 0, "carol": 0})
        self.assertEqual(body["transfers"], [])

    def test_integer_ids_are_preserved(self):
        payload = {
            "segments": [10],
            "passengers": [
                {"id": 2, "board": 0, "alight": 1},
                {"id": 1, "board": 0, "alight": 1},
            ],
            "payments": [{"id": 2, "amount": 10}, {"id": 1, "amount": 0}],
        }
        resp = client.post("/settle", json=payload)
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["owed"], {"1": 5, "2": 5})
        self.assertEqual(body["balance"], {"1": -5, "2": 5})
        self.assertEqual(body["transfers"], [{"from": 1, "to": 2, "amount": 5}])

    def test_no_passengers_no_payments(self):
        resp = client.post("/settle", json={"segments": [0]})
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(
            resp.json(),
            {"owed": {}, "paid": {}, "balance": {}, "transfers": []},
        )

    def test_payments_total_mismatch_is_422(self):
        payload = dict(PAYLOAD, payments=[{"id": "alice", "amount": 250},
                                          {"id": "bob", "amount": 100},
                                          {"id": "carol", "amount": 80}])
        resp = client.post("/settle", json=payload)
        self.assertEqual(resp.status_code, 422)
        self.assertIn("does not match trip cost", resp.text)

    def test_missing_payment_is_422(self):
        payload = dict(PAYLOAD, payments=[{"id": "alice", "amount": 431}])
        resp = client.post("/settle", json=payload)
        self.assertEqual(resp.status_code, 422)
        self.assertIn("missing payment", resp.text)

    def test_duplicate_payment_is_422(self):
        payload = dict(PAYLOAD, payments=[{"id": "alice", "amount": 250},
                                          {"id": "alice", "amount": 181}])
        resp = client.post("/settle", json=payload)
        self.assertEqual(resp.status_code, 422)
        self.assertIn("duplicate payment", resp.text)

    def test_unknown_payment_is_422(self):
        payload = dict(PAYLOAD, payments=[{"id": "alice", "amount": 250},
                                          {"id": "bob", "amount": 100},
                                          {"id": "dave", "amount": 81}])
        resp = client.post("/settle", json=payload)
        self.assertEqual(resp.status_code, 422)
        self.assertIn("unknown passenger", resp.text)

    def test_negative_payment_is_422(self):
        payload = dict(PAYLOAD, payments=[{"id": "alice", "amount": 450},
                                          {"id": "bob", "amount": 100},
                                          {"id": "carol", "amount": -119}])
        self.assertEqual(client.post("/settle", json=payload).status_code, 422)

    def test_trip_validation_still_applies(self):
        payload = {"segments": [100, 0, 50],
                   "passengers": [{"id": "a", "board": 2, "alight": 3}],
                   "payments": [{"id": "a", "amount": 150}]}
        resp = client.post("/settle", json=payload)
        self.assertEqual(resp.status_code, 422)
        self.assertIn("no passengers on board", resp.text)

    def test_unknown_field_is_422(self):
        self.assertEqual(
            client.post("/settle", json=dict(PAYLOAD, currency="usd")).status_code,
            422,
        )
        bad_payment = dict(PAYLOAD, payments=[{"id": "alice", "amount": 431,
                                               "method": "cash"}])
        self.assertEqual(client.post("/settle", json=bad_payment).status_code, 422)


if __name__ == "__main__":
    unittest.main()
