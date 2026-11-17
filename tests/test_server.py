"""HTTP contract tests for the local prediction service.

The server is started through the public CLI on an ephemeral port, so this
exercises the same path a frontend or backend uses.  Requires the datasets in
``data/`` (or ``DRAFTGAP_DATA_DIR``); skipped when they are missing.
"""

from __future__ import annotations

import http.client
import json
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.environ.get("DRAFTGAP_DATA_DIR", ROOT / "data"))
CAPTURED_DATASET_DATE = "2026-11-15T18:27:27.113Z"

FULL_DRAFT = {
    "allies": [
        {"champion": "Maokai", "role": "top"},
        {"champion": "Viego", "role": "jungle"},
        {"champion": "Karthus", "role": "middle"},
        {"champion": "Kalista", "role": "bottom"},
        {"champion": "Thresh", "role": "support"},
    ],
    "opponents": [
        {"champion": "Camille", "role": "top"},
        {"champion": "Lee Sin", "role": "jungle"},
        {"champion": "Seraphine", "role": "middle"},
        {"champion": "Kai'Sa", "role": "bottom"},
        {"champion": "Soraka", "role": "support"},
    ],
}


@unittest.skipUnless(
    (DATA_DIR / "current-patch.json").exists()
    and (DATA_DIR / "30-days.json").exists(),
    f"datasets not found in {DATA_DIR}",
)
class ServerContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.process = subprocess.Popen(
            [
                sys.executable,
                "-I",
                str(ROOT / "draftgap_model.py"),
                "--serve",
                "--port",
                "0",
                "--data-dir",
                str(DATA_DIR),
                "--cors",
                "http://localhost:3000",
                "--no-auto-refresh",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        line = cls.process.stderr.readline()
        match = re.search(r"http://[^\s]+:(\d+)/", line)
        if not match:
            details = line + cls.process.stderr.read()
            cls.process.kill()
            raise RuntimeError(f"server did not start: {details.strip()}")
        cls.port = int(match.group(1))
        connection = http.client.HTTPConnection("127.0.0.1", cls.port, timeout=30)
        try:
            connection.request("GET", "/health")
            health = json.loads(connection.getresponse().read())
            cls.dataset_date = health["currentPatchDate"]
        finally:
            connection.close()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.process.terminate()
        try:
            cls.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            cls.process.kill()
            cls.process.wait()
        cls.process.stderr.close()

    def request(
        self,
        method: str,
        path: str,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        try:
            connection.request(method, path, body=body, headers=headers or {})
            response = connection.getresponse()
            raw = response.read()
            response_headers = {
                key.lower(): value for key, value in response.getheaders()
            }
            return response.status, response_headers, raw
        finally:
            connection.close()

    def assert_baseline_winrates(self, result: dict) -> None:
        if self.dataset_date == CAPTURED_DATASET_DATE:
            self.assertEqual(result["prediction"]["allyWinrateText"], "58.58")
            self.assertEqual(result["prediction"]["opponentWinrateText"], "41.42")
        else:
            # Upstream refreshes daily; the prediction contract must still
            # produce complementary winrates for any dataset.
            self.assertAlmostEqual(
                result["prediction"]["allyWinrate"]
                + result["prediction"]["opponentWinrate"],
                1.0,
                places=12,
            )

    def post_json(
        self,
        payload: object,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], dict]:
        status, response_headers, raw = self.request(
            "POST",
            "/predict",
            json.dumps(payload).encode("utf-8"),
            {"Content-Type": "application/json", **(headers or {})},
        )
        return status, response_headers, json.loads(raw)

    def test_health(self) -> None:
        status, headers, raw = self.request("GET", "/health")
        self.assertEqual(status, 200)
        self.assertEqual(headers["content-type"], "application/json; charset=utf-8")
        health = json.loads(raw)
        self.assertTrue(health["ok"])
        self.assertEqual(health["champions"], 173)
        self.assertEqual(health["currentPatchDate"], self.dataset_date)
        self.assertIn("refreshIntervalSeconds", health)

    def test_static_page_and_bootstrap(self) -> None:
        status, headers, raw = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertEqual(headers["content-type"], "text/html; charset=utf-8")
        self.assertIn(b"DRAFTGAP", raw)
        self.assertIn(b"/assets/app.js", raw)
        self.assertIn(b"/assets/ui.css", raw)
        self.assertIn(b'id="json-dialog"', raw)
        self.assertIn(b'id="market-open"', raw)
        self.assertIn(b'id="market-dialog"', raw)
        self.assertIn(b'id="pm-matches"', raw)
        self.assertIn(b'id="pm-pager"', raw)

        status, headers, raw = self.request("GET", "/assets/app.css")
        self.assertEqual(status, 200)
        self.assertEqual(headers["content-type"], "text/css; charset=utf-8")
        self.assertGreater(len(raw), 10_000)

        status, headers, raw = self.request("GET", "/assets/ui.css")
        self.assertEqual(status, 200)
        self.assertEqual(headers["content-type"], "text/css; charset=utf-8")
        self.assertGreater(len(raw), 1_000)

        status, headers, raw = self.request("GET", "/assets/app.js")
        self.assertEqual(status, 200)
        self.assertEqual(
            headers["content-type"], "application/javascript; charset=utf-8"
        )
        self.assertGreater(len(raw), 10_000)

        status, headers, raw = self.request("GET", "/api/bootstrap")
        self.assertEqual(status, 200)
        bootstrap = json.loads(raw)
        self.assertEqual(bootstrap["dataset"]["champions"], 173)
        self.assertEqual(len(bootstrap["roles"]), 5)
        zilean = next(
            champion
            for champion in bootstrap["champions"]
            if champion["id"] == "Zilean"
        )
        top = next(role for role in zilean["roles"] if role["role"] == 0)
        self.assertEqual(top["roleName"], "Top")
        self.assertGreater(top["games"], 0)

    def test_suggestions_contract(self) -> None:
        status, _, result = self.post_json(
            {"suggestions": 1000, "includeTables": False, "scaling": False}
        )
        self.assertEqual(status, 200)
        for side in ("allies", "opponents"):
            suggestions = result["suggestions"][side]
            self.assertGreater(len(suggestions), 100)
            self.assertTrue(
                all(item["role"] in range(5) for item in suggestions)
            )
            winrates = [item["winrate"] for item in suggestions]
            self.assertEqual(winrates, sorted(winrates, reverse=True))
        if self.dataset_date == CAPTURED_DATASET_DATE:
            first = result["suggestions"]["allies"][0]
            self.assertEqual(first["name"], "Zilean")
            self.assertEqual(first["winrateText"], "54.46")

    def test_predict_reduced_contract(self) -> None:
        status, headers, result = self.post_json(
            {**FULL_DRAFT, "includeTables": False, "scaling": False}
        )
        self.assertEqual(status, 200)
        self.assertEqual(headers["content-type"], "application/json; charset=utf-8")
        self.assert_baseline_winrates(result)
        self.assertNotIn("matchups", result)
        self.assertNotIn("duos", result)
        self.assertIsNone(result["scaling"])
        self.assertEqual(result["draft"]["roleAssignmentsEvaluated"]["allies"], 1)

    def test_invalid_input_has_code(self) -> None:
        status, _, result = self.post_json({"allies": [{"champion": "Nobody"}]})
        self.assertEqual(status, 400)
        self.assertEqual(result["code"], "invalid_input")
        self.assertIn("unknown champion", result["error"])

    def test_invalid_json_has_code(self) -> None:
        status, _, raw = self.request(
            "POST",
            "/predict",
            b"not json",
            {"Content-Type": "application/json"},
        )
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(raw)["code"], "invalid_json")

    def test_market_endpoint_validation(self) -> None:
        cases = [
            ("/api/market/matches?limit=abc", 400, "invalid_limit"),
            ("/api/market/matches?limit=0", 400, "invalid_limit"),
            ("/api/market/matches?limit=41", 400, "invalid_limit"),
            ("/api/market/matches?page=abc", 400, "invalid_page"),
            ("/api/market/matches?page=0", 400, "invalid_page"),
            ("/api/market/matches?page=-1", 400, "invalid_page"),
            ("/api/market/match", 400, "missing_slug"),
            ("/api/market/lineup?slug=x", 400, "missing_game"),
            ("/api/market/lineup?slug=x&game=abc", 400, "invalid_game"),
            ("/api/market/lineup?slug=x&game=0", 400, "invalid_game"),
            ("/api/market/lineup?slug=x&game=10", 400, "invalid_game"),
            ("/api/market/lineup?slug=not%20a%20slug&game=1", 400, "invalid_slug"),
            ("/api/market/lineup?game=1", 400, "missing_slug"),
            ("/api/market/unknown", 404, "not_found"),
        ]
        for path, expected_status, expected_code in cases:
            with self.subTest(path=path):
                status, headers, raw = self.request("GET", path)
                self.assertEqual(status, expected_status)
                self.assertEqual(
                    headers["content-type"], "application/json; charset=utf-8"
                )
                self.assertEqual(json.loads(raw)["code"], expected_code)

    def test_wrong_method_is_405(self) -> None:
        status, headers, raw = self.request("GET", "/predict")
        self.assertEqual(status, 405)
        self.assertEqual(headers["allow"], "POST, OPTIONS")
        self.assertEqual(json.loads(raw)["code"], "method_not_allowed")

    def test_cors_preflight_and_allowed_origin(self) -> None:
        status, headers, raw = self.request(
            "OPTIONS",
            "/predict",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
            },
        )
        self.assertEqual(status, 204)
        self.assertEqual(raw, b"")
        self.assertEqual(
            headers["access-control-allow-origin"], "http://localhost:3000"
        )
        self.assertIn("POST", headers["access-control-allow-methods"])

        status, headers, result = self.post_json(
            FULL_DRAFT, {"Origin": "http://localhost:3000"}
        )
        self.assertEqual(status, 200)
        self.assertEqual(
            headers["access-control-allow-origin"], "http://localhost:3000"
        )
        self.assert_baseline_winrates(result)

    def test_disallowed_origin_has_no_cors_header(self) -> None:
        status, headers, _ = self.post_json(
            FULL_DRAFT, {"Origin": "http://evil.example"}
        )
        self.assertEqual(status, 200)
        self.assertNotIn("access-control-allow-origin", headers)


if __name__ == "__main__":
    unittest.main()
