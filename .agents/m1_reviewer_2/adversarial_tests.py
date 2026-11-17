"""Adversarial stress-test suite for benchmark_suite.py and test_engine.py."""

import io
import sys
import unittest
from pathlib import Path
from arena_sdk import MatchResult
from benchmark_suite import LatencyProfile, BenchmarkRunner

class AdversarialChallengeTests(unittest.TestCase):
    def test_forfeit_reason_blindspot(self):
        """Challenge: Does run_series properly classify reason='forfeit' as a forfeit loss?"""
        # When an engine match ends in an unhandled exception or illegal move,
        # match_runner returns MatchResult(reason='forfeit', forfeited_player_id='p0', winner_id='p1')
        res = MatchResult(
            winner_id="p1",
            opponent_id="student:medium",
            reason="forfeit",
            forfeited_player_id="p0",
            final_scores={"p0": 50, "p1": 0},
            rounds_played=1,
            steps_played=10,
            replay=None,
        )
        my_slot = "p0"
        opp_slot = "p1"

        # The exact logic from benchmark_suite.py lines 774-788:
        is_win = res.winner_id == my_slot and res.reason == "normal"
        is_loss = res.winner_id == opp_slot and res.reason == "normal"
        is_forfeit_loss = res.winner_id == opp_slot and res.reason in ("timeout", "illegal_action", "error")
        is_forfeit_win = res.winner_id == my_slot and res.reason in ("timeout", "illegal_action", "error")

        won = is_win or is_forfeit_win
        wins, losses, draws, forfeits = 0, 0, 0, 0
        if won:
            wins += 1
        elif is_loss or is_forfeit_loss:
            losses += 1
            if is_forfeit_loss:
                forfeits += 1
        else:
            draws += 1

        # VULNERABILITY CONFIRMATION:
        # A bot forfeit (illegal action / crash) gets misclassified as a draw,
        # and forfeits count remains 0!
        self.assertEqual(draws, 1, "Vulnerability: forfeit misclassified as draw")
        self.assertEqual(forfeits, 0, "Vulnerability: forfeit count is 0 despite bot forfeiting")

    def test_opponent_timeout_penalizes_challenger(self):
        """Challenge: Does an opponent timeout penalize the challenger in total_timeouts?"""
        # In benchmark_suite.py lines 1288-1300:
        # match_timeouts counts ALL matches with reason == 'timeout', regardless of who timed out.
        m = {
            "game_index": 1,
            "my_slot": "p0",
            "opp_slot": "p1",
            "winner_id": "p0",
            "won": True,
            "reason": "timeout", # Opponent timed out, mon-bot won!
        }
        match_timeouts = 1 if m.get("reason") == "timeout" else 0
        total_timeouts = match_timeouts
        # In line 1324: overall_passed requires (total_timeouts == 0)
        overall_passed = (total_timeouts == 0)
        self.assertFalse(overall_passed, "Vulnerability: mon-bot fails overall because opponent timed out!")

    def test_latency_boundary_conditions(self):
        """Challenge: Check strict inequality bounds on latency gating."""
        p = LatencyProfile()
        p.record(50.0) # Exactly on mean boundary
        stats = p.compute_stats()
        # Requirement: strictly < 50.0ms
        mean_passed = stats["mean"] < 50.0
        self.assertFalse(mean_passed, "50.0ms exactly must fail strict < 50.0ms bound")

        p2 = LatencyProfile()
        p2.record(300.0) # Exactly on max boundary
        stats2 = p2.compute_stats()
        # Max bound: < 300.0ms
        max_passed = stats2["max"] < 300.0
        self.assertFalse(max_passed, "300.0ms exactly must fail strict < 300.0ms bound")

    def test_timeout_400ms_vs_1000ms(self):
        """Challenge: A move taking 450ms is within budget 1000ms but exceeds tournament 400ms."""
        p = LatencyProfile()
        p.record(450.0)
        stats = p.compute_stats()
        self.assertEqual(stats["slow_moves_gt_300ms"], 1)
        self.assertEqual(stats["timeouts_gt_400ms"], 1)
        self.assertEqual(stats["timeouts_gt_1000ms"], 0)
        # Because slow_moves_gt_300ms == 1, latency_passed will fail.
        # But if slow_moves_300 was not checked, timeouts_gt_1000ms would pass!
        self.assertGreater(stats["slow_moves_gt_300ms"], 0)

if __name__ == "__main__":
    unittest.main()
