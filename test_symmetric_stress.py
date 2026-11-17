"""Empirical Stress Harness for Symmetric Pairing & Dealer Alternation Logic."""

import unittest
from pathlib import Path
from arena_sdk import MatchConfig
from benchmark_suite import BenchmarkRunner, resolve_opponent_arg

PROJECT_ROOT = Path(__file__).resolve().parent

class TestSymmetricPairingMathematicalExactness(unittest.TestCase):
    """Stress tests mathematical exactness of symmetric pairing and dealer logic across game counts."""

    def _simulate_pairing_logic(self, games: int, symmetric: bool = True):
        half = games // 2
        match_records = []
        p0_count = 0
        p1_count = 0
        mon_starts = 0
        opp_starts = 0

        for i in range(games):
            if symmetric:
                is_p0 = (i < half)
                sub_i = i if is_p0 else (i - half)
                dealer = 1 if (sub_i % 2 == 0) else 0
            else:
                is_p0 = True
                dealer = 1 if (i % 2 == 0) else 0

            my_slot = "p0" if is_p0 else "p1"
            opp_slot = "p1" if is_p0 else "p0"
            starter_slot = "p0" if dealer == 1 else "p1"
            starter_bot = "mon-bot" if starter_slot == my_slot else "opp"

            if is_p0:
                p0_count += 1
            else:
                p1_count += 1

            if starter_bot == "mon-bot":
                mon_starts += 1
            else:
                opp_starts += 1

            match_records.append({
                "i": i,
                "is_p0": is_p0,
                "sub_i": sub_i if symmetric else i,
                "dealer": dealer,
                "my_slot": my_slot,
                "starter_slot": starter_slot,
                "starter_bot": starter_bot,
            })

        return {
            "games": games,
            "p0_count": p0_count,
            "p1_count": p1_count,
            "mon_starts": mon_starts,
            "opp_starts": opp_starts,
            "records": match_records,
        }

    def test_even_counts_exact_split(self):
        """Verify that every even game count splits p0/p1 and starters with zero bias."""
        test_counts = [2, 4, 6, 8, 10, 12, 20, 30, 50, 100, 200, 1000]
        for n in test_counts:
            res = self._simulate_pairing_logic(n, symmetric=True)
            expected_half = n // 2
            self.assertEqual(
                res["p0_count"],
                expected_half,
                f"Failed p0 split for N={n}: got {res['p0_count']}, expected {expected_half}",
            )
            self.assertEqual(
                res["p1_count"],
                expected_half,
                f"Failed p1 split for N={n}: got {res['p1_count']}, expected {expected_half}",
            )
            self.assertEqual(
                res["mon_starts"],
                expected_half,
                f"Failed starter split for mon-bot for N={n}: got {res['mon_starts']}, expected {expected_half}",
            )
            self.assertEqual(
                res["opp_starts"],
                expected_half,
                f"Failed starter split for opp for N={n}: got {res['opp_starts']}, expected {expected_half}",
            )

    def test_odd_counts_balanced_partition(self):
        """Verify that odd game counts partition as closely as possible (|p0 - p1| == 1)."""
        test_counts = [1, 3, 5, 7, 9, 15, 25, 51]
        for n in test_counts:
            res = self._simulate_pairing_logic(n, symmetric=True)
            self.assertEqual(res["p0_count"] + res["p1_count"], n)
            self.assertEqual(res["mon_starts"] + res["opp_starts"], n)
            self.assertEqual(abs(res["p0_count"] - res["p1_count"]), 1)
            self.assertLessEqual(abs(res["mon_starts"] - res["opp_starts"]), 1)

    def test_tournament_standard_50_games(self):
        """Specific verification of the official 50-game tournament format."""
        res = self._simulate_pairing_logic(50, symmetric=True)
        self.assertEqual(res["p0_count"], 25)
        self.assertEqual(res["p1_count"], 25)
        self.assertEqual(res["mon_starts"], 25)
        self.assertEqual(res["opp_starts"], 25)

        # Verify exact alternation pattern in half 1 (mon-bot is p0)
        half1 = res["records"][:25]
        for item in half1:
            self.assertEqual(item["my_slot"], "p0")
            if item["sub_i"] % 2 == 0:
                self.assertEqual(item["dealer"], 1)
                self.assertEqual(item["starter_bot"], "mon-bot")
            else:
                self.assertEqual(item["dealer"], 0)
                self.assertEqual(item["starter_bot"], "opp")

        # Verify exact alternation pattern in half 2 (mon-bot is p1)
        half2 = res["records"][25:]
        for item in half2:
            self.assertEqual(item["my_slot"], "p1")
            if item["sub_i"] % 2 == 0:
                self.assertEqual(item["dealer"], 1)
                self.assertEqual(item["starter_bot"], "opp")
            else:
                self.assertEqual(item["dealer"], 0)
                self.assertEqual(item["starter_bot"], "mon-bot")


class TestBenchmarkRunnerLiveSymmetricExecution(unittest.TestCase):
    """Executes live match series using BenchmarkRunner to empirically test symmetric splits and win accounting."""

    @classmethod
    def setUpClass(cls):
        cls.runner = BenchmarkRunner(
            bot_path=PROJECT_ROOT / "bot.py",
            target_score=151,
            verbose=False,
        )

    def test_live_series_n_2(self):
        """Empirically run 2 games vs builtin:random to verify 1 p0 and 1 p1 game."""
        res = self.runner.run_series("builtin:random", games=2, base_seed=100, symmetric=True)
        self.assertEqual(res["games"], 2)
        self.assertEqual(res["p0_games"], 1)
        self.assertEqual(res["p1_games"], 1)
        self.assertEqual(res["starter_me_games"], 1)
        self.assertEqual(res["starter_opp_games"], 1)
        self.assertEqual(len(res["matches"]), 2)
        self.assertEqual(res["matches"][0]["my_slot"], "p0")
        self.assertEqual(res["matches"][1]["my_slot"], "p1")

    def test_live_series_n_6(self):
        """Empirically run 6 games vs builtin:random to verify 3 p0 and 3 p1 games, 3 starter me and 3 starter opp."""
        res = self.runner.run_series("builtin:random", games=6, base_seed=200, symmetric=True)
        self.assertEqual(res["games"], 6)
        self.assertEqual(res["p0_games"], 3)
        self.assertEqual(res["p1_games"], 3)
        self.assertEqual(res["starter_me_games"], 3)
        self.assertEqual(res["starter_opp_games"], 3)
        self.assertEqual(len(res["matches"]), 6)
        
        # Verify slots for all 6 games
        for idx in range(3):
            self.assertEqual(res["matches"][idx]["my_slot"], "p0")
        for idx in range(3, 6):
            self.assertEqual(res["matches"][idx]["my_slot"], "p1")

        # Verify win/loss calculations are consistent
        self.assertEqual(res["wins"] + res["losses"] + res["draws"], 6)
        self.assertEqual(res["p0_wins"] + res["p1_wins"], res["wins"])
        self.assertEqual(res["starter_me_wins"] + res["starter_opp_wins"], res["wins"])

    def test_live_series_n_10(self):
        """Empirically run 10 games vs builtin:random to verify 5 p0 and 5 p1 games, 5 starter me and 5 starter opp."""
        res = self.runner.run_series("builtin:random", games=10, base_seed=300, symmetric=True)
        self.assertEqual(res["games"], 10)
        self.assertEqual(res["p0_games"], 5)
        self.assertEqual(res["p1_games"], 5)
        self.assertEqual(res["starter_me_games"], 5)
        self.assertEqual(res["starter_opp_games"], 5)
        self.assertEqual(len(res["matches"]), 10)
        for idx in range(5):
            self.assertEqual(res["matches"][idx]["my_slot"], "p0")
        for idx in range(5, 10):
            self.assertEqual(res["matches"][idx]["my_slot"], "p1")
        self.assertEqual(res["p0_wins"] + res["p1_wins"], res["wins"])
        self.assertEqual(res["starter_me_wins"] + res["starter_opp_wins"], res["wins"])

    def test_series_n_50_end_to_end_accounting(self):
        """Verify full 50-game run_series execution and dictionary accounting with mocked engine results."""
        from unittest.mock import patch
        from arena_sdk import MatchResult

        call_args_list = []

        def fake_play_bots_match(*args, **kwargs):
            call_args_list.append((args, kwargs))
            # Return p0 as winner
            return MatchResult(
                winner_id="p0",
                opponent_id="student:opp",
                reason="normal",
                forfeited_player_id=None,
                final_scores={"p0": 151, "p1": 40},
                rounds_played=4,
                steps_played=80,
                replay=None,
            )

        with patch("benchmark_suite.play_bots_match", side_effect=fake_play_bots_match):
            res = self.runner.run_series("builtin:random", games=50, base_seed=42, symmetric=True)

        self.assertEqual(res["games"], 50)
        self.assertEqual(res["p0_games"], 25)
        self.assertEqual(res["p1_games"], 25)
        self.assertEqual(res["starter_me_games"], 25)
        self.assertEqual(res["starter_opp_games"], 25)
        self.assertEqual(len(call_args_list), 50)

        # In call_args_list, the first 25 calls must have mon-bot as challenger (first arg)
        for idx in range(25):
            _, kwargs = call_args_list[idx]
            self.assertEqual(kwargs["challenger_name"], "mon-bot")
            self.assertEqual(kwargs["opponent_name"], "Aléatoire")

        # The last 25 calls must have opp as challenger (first arg)
        for idx in range(25, 50):
            _, kwargs = call_args_list[idx]
            self.assertEqual(kwargs["challenger_name"], "Aléatoire")
            self.assertEqual(kwargs["opponent_name"], "mon-bot")

        # Since fake_play_bots_match always returns winner_id="p0":
        # In games 0..24, my_slot is "p0", so mon-bot won all 25
        # In games 25..49, my_slot is "p1", so opp ("p0") won all 25
        self.assertEqual(res["p0_wins"], 25)
        self.assertEqual(res["p1_wins"], 0)
        self.assertEqual(res["wins"], 25)
        self.assertEqual(res["losses"], 25)
        self.assertEqual(res["win_rate_pct"], 50.0)
        self.assertEqual(res["p0_win_rate_pct"], 100.0)
        self.assertEqual(res["p1_win_rate_pct"], 0.0)


if __name__ == "__main__":
    unittest.main()
