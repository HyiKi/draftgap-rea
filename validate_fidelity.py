#!/usr/bin/env python3
"""Compare the reimplementation with values captured from draftgap.com.

The expected values were read from the live DraftGap page for its built-in
debug draft (the draft used by window.DRAFTGAP_DEBUG.test()):

    allies:    Maokai top, Viego jungle, Karthus middle, Kalista bottom,
               Thresh support
    opponents: Camille top, Lee Sin jungle, Seraphine middle, Kai'Sa bottom,
               Soraka support

The page and the datasets were observed on 2026-11-15.  Run with the matching
v5 datasets (the service refreshes upstream data daily, so the captured numbers
only apply to the recorded snapshot):

    python3 validate_fidelity.py --data-dir /path/to/datasets-live
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import draftgap_model as dgm  # noqa: E402

DEBUG_DRAFT = {
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

CAPTURED_DATASET_DATE = "2026-11-15T18:27:27.113Z"

# Captured "DRAFT ANALYSIS" cards.
EXPECTED_CARDS = {
    "ally": {
        "championWinrateText": "49.29",
        "matchupWinrateText": "52.27",
        "duoWinrateText": "53.17",
        "winrateText": "58.58",
    },
    "opponent": {
        "championWinrateText": "45.28",
        "matchupWinrateText": "47.73",
        "duoWinrateText": "50.81",
        "winrateText": "41.42",
    },
}

# Captured per-champion overview rows: base, matchup, duo, total.
EXPECTED_ROWS = {
    "allies": [
        ("Top", "Maokai", ("49.66", "50.15", "49.97", "49.78")),
        ("Jungle", "Viego", ("50.05", "48.42", "50.34", "48.81")),
        ("Middle", "Karthus", ("49.53", "50.72", "51.13", "51.39")),
        ("Bottom", "Kalista", ("48.92", "52.79", "51.33", "53.03")),
        ("Support", "Thresh", ("51.14", "50.19", "50.40", "51.73")),
    ],
    "opponents": [
        ("Top", "Camille", ("50.38", "51.26", "49.93", "51.57")),
        ("Jungle", "Lee Sin", ("48.16", "49.41", "49.78", "47.34")),
        ("Middle", "Seraphine", ("46.33", "51.62", "50.42", "48.37")),
        ("Bottom", "Kai'Sa", ("49.57", "47.79", "50.83", "48.19")),
        ("Support", "Soraka", ("50.85", "47.65", "49.85", "48.34")),
    ],
}

EXPECTED_TEAM_TOTALS = {
    "allies": ("49.29", "52.27", "53.17", "54.73"),
    "opponents": ("45.28", "47.73", "50.81", "43.83"),
}

# Captured HEAD 2 HEAD rows (same role, ally perspective / opponent perspective).
EXPECTED_MATCHUPS = [
    ("Maokai", "Camille", "49.42", "50.58"),
    ("Viego", "Lee Sin", "48.94", "51.06"),
    ("Karthus", "Seraphine", "49.96", "50.04"),
    ("Kalista", "Kai'Sa", "51.04", "48.96"),
    ("Thresh", "Soraka", "49.76", "50.24"),
]
EXPECTED_MATCHUP_TOTALS = {
    "all": ("52.27", "47.73"),
    "sameRole": ("49.12", "50.88"),
}

# Captured duo tables.
EXPECTED_DUOS = {
    "allies": [
        ("Maokai", "Viego", "50.06"),
        ("Maokai", "Karthus", "50.03"),
        ("Maokai", "Kalista", "50.57"),
        ("Maokai", "Thresh", "49.28"),
        ("Viego", "Karthus", "50.51"),
        ("Viego", "Kalista", "50.34"),
        ("Viego", "Thresh", "49.78"),
        ("Karthus", "Kalista", "50.87"),
        ("Karthus", "Thresh", "50.86"),
        ("Kalista", "Thresh", "50.88"),
    ],
    "opponents": [
        ("Camille", "Lee Sin", "50.25"),
        ("Camille", "Seraphine", "49.90"),
        ("Camille", "Kai'Sa", "49.80"),
        ("Camille", "Soraka", "49.91"),
        ("Lee Sin", "Seraphine", "49.23"),
        ("Lee Sin", "Kai'Sa", "50.13"),
        ("Lee Sin", "Soraka", "49.95"),
        ("Seraphine", "Kai'Sa", "51.81"),
        ("Seraphine", "Soraka", "49.91"),
        ("Kai'Sa", "Soraka", "49.93"),
    ],
}
EXPECTED_DUO_TOTALS = {"allies": "53.17", "opponents": "50.81"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        default=os.environ.get(
            "DRAFTGAP_DATA_DIR",
            str(Path(__file__).resolve().parent / "data"),
        ),
    )
    args = parser.parse_args()

    model = dgm.load_model(args.data_dir)
    result = model.analyze(DEBUG_DRAFT)
    dataset_date = result["model"]["currentPatch"]["date"]
    if dataset_date != CAPTURED_DATASET_DATE:
        print(
            "SKIP: captured page values were recorded for "
            f"{CAPTURED_DATASET_DATE}, but the loaded dataset is {dataset_date}.\n"
            "Upstream refreshes the data daily; rerun with the matching snapshot "
            "or update the captured values."
        )
        return 2
    failures: list[str] = []
    checks = 0

    def check(label: str, actual: object, expected: object) -> None:
        nonlocal checks
        checks += 1
        if actual != expected:
            failures.append(f"{label}: expected {expected!r}, got {actual!r}")

    for side in ("ally", "opponent"):
        cards = result["prediction"][side]
        for field, expected in EXPECTED_CARDS[side].items():
            check(f"{side} card {field}", cards[field], expected)

    for side, expected_rows in EXPECTED_ROWS.items():
        rows = result["breakdown"][side]["rows"]
        actual_rows = [
            (
                row["roleName"],
                row["name"],
                (
                    row["baseText"],
                    row["matchupText"],
                    row["duoText"],
                    row["totalText"],
                ),
            )
            for row in rows
        ]
        check(f"{side} rows", actual_rows, expected_rows)
        totals = result["breakdown"][side]["totals"]
        check(
            f"{side} team totals",
            (
                totals["baseText"],
                totals["matchupText"],
                totals["duoText"],
                totals["totalText"],
            ),
            EXPECTED_TEAM_TOTALS[side],
        )

    same_role = result["matchups"]["sameRoleResults"]
    actual_matchups = [
        (row["nameA"], row["nameB"], row["allyText"], row["opponentText"])
        for row in same_role
    ]
    check("same-role matchups", actual_matchups, EXPECTED_MATCHUPS)
    for key, expected in EXPECTED_MATCHUP_TOTALS.items():
        totals = result["matchups"]["totals"][key]
        check(
            f"matchup {key} totals",
            (totals["allyText"], totals["opponentText"]),
            expected,
        )

    for side, expected_duos in EXPECTED_DUOS.items():
        actual_duos = [
            (row["nameA"], row["nameB"], row["winrateText"])
            for row in result["duos"][side]["results"]
        ]
        check(f"{side} duos", actual_duos, expected_duos)
        check(
            f"{side} duo total",
            result["duos"][side]["totals"]["winrateText"],
            EXPECTED_DUO_TOTALS[side],
        )

    if failures:
        print(f"FAIL: {len(failures)} of {checks} checks differ")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"PASS: all {checks} captured page checks match")
    print(
        "  ally winrate "
        f"{result['prediction']['allyWinrateText']} / opponent "
        f"{result['prediction']['opponentWinrateText']}"
    )
    print(
        "  dataset "
        f"{result['model']['currentPatch']['version']} "
        f"({result['model']['currentPatch']['date']})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
