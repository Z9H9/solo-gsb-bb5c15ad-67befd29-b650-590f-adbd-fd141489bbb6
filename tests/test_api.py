"""HTTP-level tests for the FastAPI app (require fastapi + httpx installed)."""

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
}


class SplitApiTests(unittest.TestCase):
    def test_split_ok(self):
        resp = client.post("/split", json=PAYLOAD)
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["total_cost"], 431)
        self.assertEqual(body["totals"], {"alice": 216, "bob": 165, "carol": 50})
        self.assertEqual(sum(body["totals"].values()), body["total_cost"])
        self.assertEqual(len(body["segments"]), 3)
        for seg, cost in zip(body["segments"], PAYLOAD["segments"]):
            self.assertEqual(seg["cost"], cost)
            self.assertEqual(sum(seg["shares"].values()), cost)
        self.assertEqual(body["segments"][0]["passengers"], ["alice", "carol"])
        self.assertEqual(body["segments"][1]["shares"], {"alice": 126, "bob": 125})

    def test_passenger_order_does_not_matter(self):
        reversed_payload = dict(PAYLOAD, passengers=list(reversed(PAYLOAD["passengers"])))
        r1 = client.post("/split", json=PAYLOAD)
        r2 = client.post("/split", json=reversed_payload)
        self.assertEqual(r1.status_code, r2.status_code)
        self.assertEqual(r1.json(), r2.json())

    def test_empty_load_charged_segment_is_422(self):
        payload = {"segments": [100, 0, 50],
                   "passengers": [{"id": "a", "board": 2, "alight": 3}]}
        resp = client.post("/split", json=payload)
        self.assertEqual(resp.status_code, 422)
        self.assertIn("no passengers on board", resp.text)

    def test_zero_cost_empty_segment_is_ok(self):
        payload = {"segments": [0, 50],
                   "passengers": [{"id": "a", "board": 1, "alight": 2}]}
        resp = client.post("/split", json=payload)
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["totals"], {"a": 50})

    def test_board_not_before_alight_is_422(self):
        payload = {"segments": [10, 10],
                   "passengers": [{"id": "a", "board": 1, "alight": 1}]}
        resp = client.post("/split", json=payload)
        self.assertEqual(resp.status_code, 422)
        self.assertIn("invalid interval", resp.text)

    def test_station_out_of_range_is_422(self):
        payload = {"segments": [10, 10],
                   "passengers": [{"id": "a", "board": 0, "alight": 3}]}
        resp = client.post("/split", json=payload)
        self.assertEqual(resp.status_code, 422)
        self.assertIn("out of range", resp.text)

    def test_negative_board_is_422(self):
        payload = {"segments": [10],
                   "passengers": [{"id": "a", "board": -1, "alight": 1}]}
        self.assertEqual(client.post("/split", json=payload).status_code, 422)

    def test_duplicate_passenger_id_is_422(self):
        payload = {"segments": [10],
                   "passengers": [{"id": "a", "board": 0, "alight": 1},
                                  {"id": "a", "board": 0, "alight": 1}]}
        resp = client.post("/split", json=payload)
        self.assertEqual(resp.status_code, 422)
        self.assertIn("duplicate passenger id", resp.text)

    def test_negative_cost_is_422(self):
        payload = {"segments": [10, -5],
                   "passengers": [{"id": "a", "board": 0, "alight": 2}]}
        self.assertEqual(client.post("/split", json=payload).status_code, 422)

    def test_empty_segments_is_422(self):
        self.assertEqual(client.post("/split", json={"segments": []}).status_code, 422)

    def test_unknown_field_is_422(self):
        payload = dict(PAYLOAD, currency="usd")
        self.assertEqual(client.post("/split", json=payload).status_code, 422)

    def test_healthz(self):
        resp = client.get("/healthz")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"status": "ok"})


if __name__ == "__main__":
    unittest.main()
