"""Behaviour tests for the DraftGap model reimplementation.

Run from the project root:

    python3 -m unittest discover -s tests -v

The full captured-page comparison lives in ../validate_fidelity.py.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import draftgap_model as dgm  # noqa: E402

DATA_DIR = os.environ.get("DRAFTGAP_DATA_DIR", str(ROOT / "data"))

# Numeric page values are captured from the live DraftGap page for this
# dataset.  Upstream refreshes the data daily, so exact-value assertions are
# only meaningful for the captured snapshot.
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


class ModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.model = dgm.load_model(DATA_DIR)
        cls.baseline = cls.model.analyze(FULL_DRAFT)

    def test_page_values(self) -> None:
        result = self.baseline
        if self.model.current.date != CAPTURED_DATASET_DATE:
            # The captured numbers no longer apply after an upstream refresh;
            # keep the cross-checks that must hold for any dataset.
            self.assertAlmostEqual(
                result["prediction"]["allyWinrate"]
                + result["prediction"]["opponentWinrate"],
                1.0,
                places=12,
            )
            self.assertEqual(
                [row["role"] for row in result["breakdown"]["allies"]["rows"]],
                [0, 1, 2, 3, 4],
            )
            return
        self.assertEqual(result["prediction"]["ally"]["championWinrateText"], "49.29")
        self.assertEqual(result["prediction"]["ally"]["matchupWinrateText"], "52.27")
        self.assertEqual(result["prediction"]["ally"]["duoWinrateText"], "53.17")
        self.assertEqual(result["prediction"]["allyWinrateText"], "58.58")
        self.assertEqual(result["prediction"]["opponent"]["championWinrateText"], "45.28")
        self.assertEqual(result["prediction"]["opponent"]["matchupWinrateText"], "47.73")
        self.assertEqual(result["prediction"]["opponent"]["duoWinrateText"], "50.81")
        self.assertEqual(result["prediction"]["opponentWinrateText"], "41.42")
        self.assertEqual(
            [row["totalText"] for row in result["breakdown"]["allies"]["rows"]],
            ["49.78", "48.81", "51.39", "53.03", "51.73"],
        )
        self.assertEqual(result["breakdown"]["allies"]["totals"]["totalText"], "54.73")

    def test_role_inference_matches_explicit_roles(self) -> None:
        payload = {
            "allies": [{"champion": entry["champion"]} for entry in FULL_DRAFT["allies"]],
            "opponents": [
                {"champion": entry["champion"]} for entry in FULL_DRAFT["opponents"]
            ],
        }
        result = self.model.analyze(payload)
        self.assertEqual(
            result["prediction"]["allyWinrateText"],
            self.baseline["prediction"]["allyWinrateText"],
        )
        self.assertEqual(
            [entry["roleName"] for entry in result["draft"]["allies"]],
            ["Top", "Jungle", "Middle", "Bottom", "Support"],
        )
        self.assertTrue(all(entry["roleInferred"] for entry in result["draft"]["allies"]))
        for entry in result["draft"]["allies"]:
            probabilities = entry["roleProbabilities"]
            self.assertGreaterEqual(len(probabilities), 1)
            self.assertAlmostEqual(
                sum(item["probability"] for item in probabilities), 1.0, places=9
            )

    def test_aliases_and_id_types(self) -> None:
        payload = {
            "allies": [
                {"champion": 57, "role": 0},
                {"champion": "MonkeyKing", "role": "jungle"},
                {"champion": "扭曲树精", "role": "middle"},
            ],
            "opponents": [
                {"champion": "145", "role": "BOTTOM"},
                {"champion": "Soraka", "role": "UTILITY"},
            ],
        }
        with self.assertRaises(dgm.InputError):
            # 57 and 扭曲树精 are both Maokai.
            self.model.analyze(payload)

        payload["allies"][2]["champion"] = "Karthus"
        result = self.model.analyze(payload)
        self.assertEqual(result["draft"]["allies"][0]["name"], "Maokai")
        self.assertEqual(result["draft"]["allies"][1]["name"], "Wukong")
        self.assertEqual(result["draft"]["opponents"][0]["name"], "Kai'Sa")

    def test_chinese_name_resolves(self) -> None:
        result = self.model.analyze(
            {
                "allies": [{"champion": "扭曲树精", "role": "top"}],
                "opponents": [{"champion": "虚空之女", "role": "bottom"}],
            }
        )
        self.assertEqual(result["draft"]["allies"][0]["championKey"], "57")
        self.assertEqual(result["draft"]["opponents"][0]["championKey"], "145")

    def test_role_to_champion_mapping(self) -> None:
        result = self.model.analyze(
            {
                "allies": {
                    "top": "Maokai",
                    "jungle": "Viego",
                    "middle": "Karthus",
                    "bottom": "Kalista",
                    "support": "Thresh",
                },
                "opponents": {
                    "TOP": "Camille",
                    "JUNGLE": "Lee Sin",
                    "MIDDLE": "Seraphine",
                    "BOTTOM": "Kai'Sa",
                    "UTILITY": "Soraka",
                },
            }
        )
        self.assertEqual(
            result["prediction"]["allyWinrateText"],
            self.baseline["prediction"]["allyWinrateText"],
        )

    def test_suggestions_fill_open_roles_and_sort(self) -> None:
        result = self.model.analyze(
            {
                "allies": {
                    "top": "Maokai",
                    "jungle": "Viego",
                    "middle": "Karthus",
                },
                "opponents": {"top": "Camille", "jungle": "Lee Sin"},
                "suggestions": 4,
            }
        )
        for side, open_roles in (("allies", {3, 4}), ("opponents", {2, 3, 4})):
            suggestions = result["suggestions"][side]
            self.assertEqual(len(suggestions), 4)
            self.assertTrue(all(item["role"] in open_roles for item in suggestions))
            winrates = [item["winrate"] for item in suggestions]
            self.assertEqual(winrates, sorted(winrates, reverse=True))

    def test_ignore_champion_winrates(self) -> None:
        result = self.model.analyze(
            {**FULL_DRAFT, "ignoreChampionWinrates": True}
        )
        self.assertEqual(
            result["prediction"]["ally"]["championWinrateText"], "50.00"
        )
        self.assertNotEqual(
            result["prediction"]["allyWinrateText"],
            self.baseline["prediction"]["allyWinrateText"],
        )

    def test_risk_level_and_prior_override(self) -> None:
        very_high = self.model.analyze({**FULL_DRAFT, "riskLevel": "very-high"})
        self.assertEqual(very_high["model"]["config"]["priorGames"], 250)
        override = self.model.analyze({**FULL_DRAFT, "priorGames": 1234})
        self.assertEqual(override["model"]["config"]["priorGames"], 1234)

    def test_empty_teams_is_fifty_percent(self) -> None:
        result = self.model.analyze({})
        self.assertEqual(result["prediction"]["allyWinrateText"], "50.00")
        self.assertEqual(result["prediction"]["opponentWinrateText"], "50.00")

    def test_rejections(self) -> None:
        cases = [
            # Unknown champion.
            {"allies": [{"champion": "Not A Champion"}]},
            # Duplicate champion.
            {
                "allies": [
                    {"champion": "Maokai"},
                    {"champion": "Maokai"},
                ]
            },
            # Same champion on both teams.
            {
                "allies": [{"champion": "Maokai"}],
                "opponents": [{"champion": "57"}],
            },
            # Duplicate explicit role.
            {
                "allies": [
                    {"champion": "Maokai", "role": "top"},
                    {"champion": "Viego", "role": "top"},
                ]
            },
            # More than five champions.
            {
                "allies": [
                    {"champion": "Maokai"},
                    {"champion": "Viego"},
                    {"champion": "Karthus"},
                    {"champion": "Kalista"},
                    {"champion": "Thresh"},
                    {"champion": "Soraka"},
                ]
            },
            # Unknown role.
            {"allies": [{"champion": "Maokai", "role": "roam"}]},
        ]
        for payload in cases:
            with self.subTest(payload=payload):
                with self.assertRaises(dgm.InputError):
                    self.model.analyze(payload)

    def test_output_is_json_serializable(self) -> None:
        import json

        text = json.dumps(
            self.baseline, ensure_ascii=False, allow_nan=False
        )
        self.assertEqual(
            json.loads(text)["prediction"]["allyWinrateText"],
            self.baseline["prediction"]["allyWinrateText"],
        )

    def test_display_rounding_matches_to_fixed(self) -> None:
        # 53.485... is displayed with JS toFixed-style rounding.
        self.assertEqual(dgm.percent_text(0.53485), "53.49")
        self.assertEqual(dgm.percent_text(0.53484), "53.48")
        self.assertEqual(dgm.percent_text(float("nan")), "NaN")


if __name__ == "__main__":
    unittest.main()
