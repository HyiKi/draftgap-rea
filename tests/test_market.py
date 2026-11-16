"""Parsing and provenance tests for the Market LoL lineup browser."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import draftgap_model as dgm  # noqa: E402

DATA_DIR = os.environ.get("DRAFTGAP_DATA_DIR", str(ROOT / "data"))

FINAL_EVENT = {
    "id": "1345375",
    "slug": "lol-blg-gen-2026-11-14",
    "title": "LoL: Bilibili Gaming vs Gen.G (BO5) - Worlds Playoffs",
    "gameId": "1711021",
    "live": False,
    "closed": True,
    "ended": True,
    "startTime": "2026-11-14T19:40:00Z",
    "endTime": "2026-11-15T01:40:00Z",
    "period": "4/5",
    "score": "000-000|3-1|Bo5",
    "teams": [
        {
            "id": "146589",
            "name": "Bilibili Gaming",
            "abbreviation": "blg",
            "host": "home",
            "score": 3,
        },
        {
            "id": "146465",
            "name": "Gen.G",
            "abbreviation": "gen",
            "host": "away",
            "score": 1,
        },
    ],
    "metadata": {"gridSeriesId": "3012986"},
    "marketGroups": [
        {
            "id": "child_moneyline",
            "sportsMarketType": "child_moneyline",
            "markets": [
                {
                    "title": f"Game {number} Winner",
                    "slug": f"lol-blg-gen-2026-11-14-game{number}",
                    "closed": True,
                    "marketSides": [
                        {
                            "label": "Bilibili Gaming" if number > 1 else "Gen.G",
                            "won": True,
                        },
                        {
                            "label": "Gen.G" if number > 1 else "Bilibili Gaming",
                            "won": False,
                        },
                    ],
                }
                for number in range(1, 5)
            ],
        }
    ],
}

FINAL_SERIES = {
    "format": "best-of-5",
    "teams": [
        {"id": "47558", "name": "Gen.G Esports", "score": 1},
        {"id": "356", "name": "BILIBILI GAMING", "score": 3},
    ],
    "games": [
        {
            "sequenceNumber": 1,
            "started": True,
            "finished": True,
            "teams": [
                {"id": "47558", "score": 19, "won": True},
                {"id": "356", "score": 4, "won": False},
            ],
        },
        {
            "sequenceNumber": 2,
            "started": True,
            "finished": True,
            "teams": [
                {"id": "47558", "score": 14, "won": False},
                {"id": "356", "score": 19, "won": True},
            ],
        },
        {
            "sequenceNumber": 3,
            "started": True,
            "finished": True,
            "teams": [
                {"id": "47558", "score": 8, "won": False},
                {"id": "356", "score": 20, "won": True},
            ],
        },
        {
            "sequenceNumber": 4,
            "started": True,
            "finished": True,
            "teams": [
                {"id": "47558", "score": 11, "won": False},
                {"id": "356", "score": 21, "won": True},
            ],
        },
    ],
}

ARCHIVE_ROW = {
    "OverviewPage": "2026 Season World Championship/Main Event",
    "MatchId": "2026 Season World Championship/Main Event_Finals_1",
    "GameId": "2026 Season World Championship/Main Event_Finals_1_4",
    "Team1": "Bilibili Gaming",
    "Team2": "Gen.G",
    "Team1Picks": "Gwen,Nocturne,Twisted Fate,Yunara,Neeko",
    "Team2Picks": "Aurora,Pantheon,Akali,Xayah,Lulu",
    "Team1Bans": "Qiyana,Jayce,Seraphine,Sylas,Rumble",
    "Team2Bans": "Nautilus,Skarner,Kindred,Renekton,Galio",
    "DateTime UTC": "2026-11-14 23:18:00",
    "Tournament": "Worlds 2026 Main Event",
    "N GameInMatch": "4",
    "WinTeam": "Bilibili Gaming",
    "Team1Players": "Bin (Chen Ze-Bin),Xun,Knight (Zhuo Ding),Viper (Park Do-hyeon),ON",
    "Team2Players": "Kiin,Canyon,Chovy,Ruler,Duro",
}

LIVE_EVENT = {
    "id": "1399999",
    "slug": "lol-test-live-2026-11-16",
    "title": "LoL: Alpha vs Beta (BO3) - Test League",
    "gameId": "1800000",
    "live": True,
    "closed": False,
    "ended": False,
    "startTime": "2026-11-16T09:00:00Z",
    "period": "2/3",
    "score": "000-000|1-0|Bo3",
    "teams": [
        {"id": "1", "name": "Alpha", "abbreviation": "a", "host": "home", "score": 1},
        {"id": "2", "name": "Beta", "abbreviation": "b", "host": "away", "score": 0},
    ],
    "metadata": {"gridSeriesId": "3999999"},
    "marketGroups": [
        {
            "id": "child_moneyline",
            "markets": [
                {"title": "Game 1 Winner", "closed": True, "marketSides": [{"label": "Alpha", "won": True}]},
                {"title": "Game 2 Winner", "closed": False},
                {"title": "Game 3 Winner", "closed": False},
            ],
        }
    ],
}

LIVE_SERIES = {
    "format": "best-of-3",
    "teams": [
        {"id": "100", "name": "Alpha", "score": 1},
        {"id": "200", "name": "Beta", "score": 0},
    ],
    "games": [
        {
            "sequenceNumber": 1,
            "started": True,
            "finished": True,
            "teams": [
                {"id": "100", "score": 21, "won": True},
                {"id": "200", "score": 13, "won": False},
            ],
        },
        {
            "sequenceNumber": 2,
            "started": True,
            "finished": False,
            "teams": [
                {"id": "100", "score": 4, "won": False},
                {"id": "200", "score": 3, "won": False},
            ],
        },
    ],
}

LIVE_SNAPSHOT = {
    "event_id": "1399999",
    "title": "lol",
    "phase": "live",
    "current_game": 2,
    "best_of": 3,
    "teams": [
        {"id": "100", "name": "Alpha", "market_side": "home", "games_won": 1},
        {"id": "200", "name": "Beta", "market_side": "away", "games_won": 0},
    ],
    "games": [
        {
            "number": 2,
            "started": True,
            "finished": False,
            "winner_team_id": "",
            "teams": [
                {
                    "team_id": "100",
                    "side": "blue",
                    "kills": 4,
                    "players": [
                        {"id": "p1", "name": "TopA", "character": "Gwen", "character_id": "150"},
                        {"id": "p2", "name": "JungleA", "character": "Nocturne", "character_id": "56"},
                        {"id": "p3", "name": "MidA", "character": "Twisted Fate", "character_id": "4"},
                        {"id": "p4", "name": "BotA", "character": "Yunara", "character_id": "804"},
                        {"id": "p5", "name": "SupportA", "character": "Neeko", "character_id": "518"},
                    ],
                    "drakes": [],
                },
                {
                    "team_id": "200",
                    "side": "red",
                    "kills": 3,
                    "players": [
                        {"id": "p6", "name": "TopB", "character": "Aurora", "character_id": "893"},
                        {"id": "p7", "name": "JungleB", "character": "Pantheon", "character_id": "80"},
                        {"id": "p8", "name": "MidB", "character": "Akali", "character_id": "84"},
                        {"id": "p9", "name": "BotB", "character": "Xayah", "character_id": "498"},
                        {"id": "p10", "name": "SupportB", "character": "Lulu", "character_id": "117"},
                    ],
                    "drakes": [],
                },
            ],
            "draft": [
                {"sequence": 1, "action": "ban", "team_id": "100", "draftable": "Qiyana"},
                {"sequence": 2, "action": "ban", "team_id": "200", "draftable": "Nautilus"},
            ],
        }
    ],
}


@unittest.skipUnless(
    (Path(DATA_DIR) / "current-patch.json").exists()
    and (Path(DATA_DIR) / "30-days.json").exists(),
    f"datasets not found in {DATA_DIR}",
)
class MarketServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.model = dgm.load_model(DATA_DIR)

    def service(self) -> dgm._MarketService:
        return dgm._MarketService(lambda: self.model)

    def test_team_name_matching_tolerates_suffixes(self) -> None:
        self.assertTrue(dgm._team_names_match("Gen.G", "Gen.G Esports"))
        self.assertTrue(dgm._team_names_match("Bilibili Gaming", "BILIBILI GAMING"))
        self.assertFalse(dgm._team_names_match("Gen.G", "T1"))

    def test_final_event_lists_only_played_games_and_series_results(self) -> None:
        service = self.service()
        service._event_view = lambda slug: FINAL_EVENT  # type: ignore[method-assign]
        service._series_state = lambda series_id: FINAL_SERIES  # type: ignore[method-assign]
        detail = service.match("lol-blg-gen-2026-11-14")
        self.assertEqual(detail["state"], "finished")
        self.assertEqual(detail["home"]["name"], "Bilibili Gaming")
        self.assertEqual(detail["away"]["name"], "Gen.G")
        self.assertEqual([game["number"] for game in detail["games"]], [1, 2, 3, 4])
        self.assertEqual(
            [game["winnerSide"] for game in detail["games"]],
            ["away", "home", "home", "home"],
        )
        self.assertEqual(
            [(game["homeKills"], game["awayKills"]) for game in detail["games"]],
            [(4, 19), (19, 14), (20, 8), (21, 11)],
        )

    def test_finished_game_falls_back_to_leaguepedia_with_provenance(self) -> None:
        service = self.service()
        service._event_view = lambda slug: FINAL_EVENT  # type: ignore[method-assign]
        service._series_state = lambda series_id: FINAL_SERIES  # type: ignore[method-assign]
        service._leaguepedia_archive = lambda match: {  # type: ignore[method-assign]
            "rows": [ARCHIVE_ROW],
            "sourceUrl": "https://lol.fandom.com/wiki/2026_Season_World_Championship/Main_Event",
        }
        lineup = service.lineup("lol-blg-gen-2026-11-14", 4)
        self.assertEqual(lineup["source"]["kind"], "leaguepedia")
        self.assertIn("no longer serves", lineup["source"]["note"])
        self.assertEqual(lineup["coverage"]["resolved"], 10)
        self.assertTrue(lineup["coverage"]["complete"])
        self.assertEqual(lineup["winnerSide"], "home")
        self.assertEqual(lineup["home"]["roleSource"], "leaguepedia-pick-order")
        self.assertEqual(
            [pick["name"] for pick in lineup["home"]["picks"]],
            ["Gwen", "Nocturne", "Twisted Fate", "Yunara", "Neeko"],
        )
        self.assertEqual(
            [pick["player"] for pick in lineup["away"]["picks"]],
            ["Kiin", "Canyon", "Chovy", "Ruler", "Duro"],
        )
        self.assertEqual(
            [pick["role"] for pick in lineup["away"]["picks"]], [0, 1, 2, 3, 4]
        )

    def test_live_snapshot_is_preferred_over_http_summary(self) -> None:
        service = self.service()
        service._event_view = lambda slug: LIVE_EVENT  # type: ignore[method-assign]
        service._series_state = lambda series_id: LIVE_SERIES  # type: ignore[method-assign]
        service._live_snapshot = lambda event_id: LIVE_SNAPSHOT  # type: ignore[method-assign]
        lineup = service.lineup("lol-test-live-2026-11-16", 2)
        self.assertEqual(lineup["source"]["kind"], "market")
        self.assertEqual(lineup["source"]["url"], "https://polymarket.com/event/lol-test-live-2026-11-16")
        self.assertEqual(lineup["coverage"]["resolved"], 10)
        self.assertEqual(lineup["home"]["roleSource"], "market-player-order")
        self.assertEqual(
            [pick["name"] for pick in lineup["home"]["picks"]],
            ["Gwen", "Nocturne", "Twisted Fate", "Yunara", "Neeko"],
        )
        self.assertEqual(
            [pick["name"] for pick in lineup["home"]["bans"]], ["Qiyana"]
        )
        self.assertEqual(
            [pick["name"] for pick in lineup["away"]["bans"]], ["Nautilus"]
        )

    def test_live_draft_without_player_roles_keeps_picks_and_unknown_roles(self) -> None:
        service = self.service()
        event_id = "1399999"
        service._event_view = lambda slug: LIVE_EVENT  # type: ignore[method-assign]
        service._series_state = lambda series_id: LIVE_SERIES  # type: ignore[method-assign]
        draft_only = dict(LIVE_SNAPSHOT)
        draft_only["games"] = [
            {
                "number": 2,
                "started": False,
                "finished": False,
                "teams": [
                    {"team_id": "100", "players": [], "drakes": []},
                    {"team_id": "200", "players": [], "drakes": []},
                ],
                "draft": [
                    {"sequence": 1, "action": "pick", "team_id": "100", "draftable": "Gwen"},
                    {"sequence": 2, "action": "pick", "team_id": "200", "draftable": "Aurora"},
                    {"sequence": 3, "action": "pick", "team_id": "100", "draftable": "Nocturne"},
                ],
            }
        ]
        service._live_snapshot = lambda event_id: draft_only  # type: ignore[method-assign]
        lineup = service.lineup("lol-test-live-2026-11-16", 2)
        self.assertEqual(lineup["source"]["kind"], "market")
        self.assertEqual(lineup["home"]["roleSource"], "unavailable")
        self.assertEqual([pick["name"] for pick in lineup["home"]["picks"]], ["Gwen", "Nocturne"])
        self.assertEqual([pick["role"] for pick in lineup["home"]["picks"]], [None, None])
        self.assertTrue(any("without role order" in warning for warning in lineup["warnings"]))


if __name__ == "__main__":
    unittest.main()
