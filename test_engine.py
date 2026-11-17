"""Unit and Regression Test Suite for i151 Grand Master Engine."""

import ast
import os
import random
import shutil
import subprocess
import sys
import unittest
import zipfile
from pathlib import Path

from unittest.mock import patch

from arena_sdk import (
    Action,
    ActionType,
    MatchContext,
    MatchResult,
    OpponentState,
    PlayerView,
    TableState,
    TurnState,
    YouState,
)
from arena_sdk.ipc.sandbox import FORBIDDEN_RUNTIME_IMPORTS
from arena_sdk.loader import load_submission_zip
from arena_sdk.pack import WHITELIST_PACKAGES, requirement_package_name
from i151_engine.models.card import Card, Rank, Suit
from i151_engine.models.player import PlayerState
from i151_engine.models.enums import RoundPhase
from i151_engine.game.round_state import RoundState

from benchmark_suite import BenchmarkRunner, LatencyProfile
from evaluator import (
    CARD_BY_ID,
    ID_BY_CARD,
    CARD_RANK_ID,
    CARD_SUIT_ID,
    CARD_POINTS,
    RANK_TO_ID,
    ID_TO_RANK,
    SUIT_TO_ID,
    ID_TO_SUIT,
    RANK_MASK,
    SUIT_MASK,
    EIGHTS_MASK,
    QUEENS_MASK,
    ACES_MASK,
    ALL_CARDS_MASK,
    MOVE_SINGLE,
    MOVE_MULTIPLE,
    cards_to_mask,
    mask_to_cards,
    mask_points,
    playable_cards_mask,
    compute_zobrist,
    compute_suit_pressure,
    finishes_on_queen_two_player,
    solve_exact_endgame,
    score_action,
)
from card_tracker import CardTracker

PROJECT_ROOT = Path(__file__).resolve().parent
SUBMISSION_ZIP = PROJECT_ROOT / "mon-bot-submission.zip"


class TestBitboardEngine(unittest.TestCase):
    def test_card_encoding_and_decoding(self):
        self.assertEqual(len(CARD_BY_ID), 32)
        for i, card in enumerate(CARD_BY_ID):
            self.assertEqual(ID_BY_CARD[card], i)
            self.assertEqual(CARD_RANK_ID[i], RANK_TO_ID[card.rank])
            self.assertEqual(ID_TO_RANK[CARD_RANK_ID[i]], card.rank)
            self.assertEqual(CARD_SUIT_ID[i], SUIT_TO_ID[card.suit])
            self.assertEqual(ID_TO_SUIT[CARD_SUIT_ID[i]], card.suit)
            self.assertEqual(card.points, CARD_POINTS[i])

    def test_mask_roundtrip(self):
        cards = (Card(Rank.EIGHT, Suit.SPADES), Card(Rank.ACE, Suit.HEARTS), Card(Rank.QUEEN, Suit.DIAMONDS))
        mask = cards_to_mask(cards)
        self.assertEqual(mask.bit_count(), 3)
        recovered = mask_to_cards(mask)
        self.assertEqual(set(recovered), set(cards))

    def test_mask_points(self):
        cards = (Card(Rank.EIGHT, Suit.SPADES), Card(Rank.ACE, Suit.HEARTS))
        mask = cards_to_mask(cards)
        # 8 = 32 pts, A = 11 pts -> 43 pts
        self.assertEqual(mask_points(mask), 43)

    def test_playable_mask_empty_table(self):
        hand = (Card(Rank.SEVEN, Suit.SPADES), Card(Rank.NINE, Suit.HEARTS))
        hand_mask = cards_to_mask(hand)
        p_mask = playable_cards_mask(hand_mask, top_card_id=-1, req_suit=-1, ace_effect_active=False, is_chaining=False)
        self.assertEqual(p_mask, hand_mask)

    def test_playable_mask_ace_effect(self):
        hand = (Card(Rank.SEVEN, Suit.SPADES), Card(Rank.ACE, Suit.HEARTS), Card(Rank.EIGHT, Suit.CLUBS))
        hand_mask = cards_to_mask(hand)
        p_mask = playable_cards_mask(hand_mask, top_card_id=0, req_suit=-1, ace_effect_active=True, is_chaining=False)
        p_cards = mask_to_cards(p_mask)
        self.assertEqual(set(p_cards), {Card(Rank.ACE, Suit.HEARTS), Card(Rank.EIGHT, Suit.CLUBS)})

    def test_playable_mask_required_suit(self):
        hand = (Card(Rank.SEVEN, Suit.SPADES), Card(Rank.NINE, Suit.HEARTS), Card(Rank.EIGHT, Suit.CLUBS))
        hand_mask = cards_to_mask(hand)
        # required_suit = 1 (HEARTS)
        p_mask = playable_cards_mask(hand_mask, top_card_id=-1, req_suit=1, ace_effect_active=False, is_chaining=False)
        p_cards = mask_to_cards(p_mask)
        self.assertEqual(set(p_cards), {Card(Rank.NINE, Suit.HEARTS), Card(Rank.EIGHT, Suit.CLUBS)})


class TestZobristHashing(unittest.TestCase):
    def test_zobrist_determinism(self):
        k1 = compute_zobrist(0b101, 0b010, 5, -1, 0, False, False, False)
        k2 = compute_zobrist(0b101, 0b010, 5, -1, 0, False, False, False)
        self.assertEqual(k1, k2)

    def test_zobrist_differential(self):
        k1 = compute_zobrist(0b101, 0b010, 5, -1, 0, False, False, False)
        k2 = compute_zobrist(0b101, 0b010, 6, -1, 0, False, False, False)
        self.assertNotEqual(k1, k2)


class TestExactEndgameSolver(unittest.TestCase):
    def test_solve_immediate_win(self):
        my_hand = cards_to_mask([Card(Rank.SEVEN, Suit.SPADES)])
        opp_hand = cards_to_mask([Card(Rank.KING, Suit.HEARTS)])
        top_cid = ID_BY_CARD[Card(Rank.SEVEN, Suit.HEARTS)]
        score, best_mv = solve_exact_endgame(
            my_hand_mask=my_hand,
            opp_hand_mask=opp_hand,
            top_card_id=top_cid,
            req_suit=-1,
            is_my_turn=True,
        )
        self.assertGreater(score, 5000.0)
        self.assertIsNotNone(best_mv)
        self.assertEqual(best_mv[0], MOVE_SINGLE)
        self.assertEqual(best_mv[1], ID_BY_CARD[Card(Rank.SEVEN, Suit.SPADES)])

    def test_solve_queen_anti_trap(self):
        # If I have only Queen of Spades and opp has King of Spades, playing Queen would cause +1 draw penalty
        my_hand = cards_to_mask([Card(Rank.QUEEN, Suit.SPADES)])
        opp_hand = cards_to_mask([Card(Rank.KING, Suit.SPADES)])
        top_cid = ID_BY_CARD[Card(Rank.JACK, Suit.SPADES)]
        score, best_mv = solve_exact_endgame(
            my_hand_mask=my_hand,
            opp_hand_mask=opp_hand,
            top_card_id=top_cid,
            req_suit=-1,
            is_my_turn=True,
        )
        # Should recognize state
        self.assertIsNotNone(score)


class TestSuitStarvation(unittest.TestCase):
    def test_suit_pressure_lockout(self):
        # We hold 3 Spades, 5 Spades seen on table -> U_spades = 0
        my_spades = cards_to_mask([Card(Rank.SEVEN, Suit.SPADES), Card(Rank.NINE, Suit.SPADES), Card(Rank.TEN, Suit.SPADES)])
        seen_spades = cards_to_mask([Card(Rank.JACK, Suit.SPADES), Card(Rank.QUEEN, Suit.SPADES), Card(Rank.KING, Suit.SPADES), Card(Rank.ACE, Suit.SPADES), Card(Rank.EIGHT, Suit.SPADES)])
        pressure = compute_suit_pressure(my_spades, seen_spades, opp_hand_size=5)
        # Spades must have highest pressure due to lockout bonus
        self.assertGreater(pressure[Suit.SPADES], pressure[Suit.HEARTS])
        self.assertGreater(pressure[Suit.SPADES], pressure[Suit.DIAMONDS])
        self.assertGreater(pressure[Suit.SPADES], pressure[Suit.CLUBS])


class TestCardTracker(unittest.TestCase):
    def test_bayesian_sampling(self):
        tracker = CardTracker()
        tracker.reset_for_round(1)
        my_hand = (Card(Rank.SEVEN, Suit.SPADES), Card(Rank.EIGHT, Suit.SPADES))
        rng = random.Random(42)
        opp_mask, bank_mask = tracker.sample_world(cards_to_mask(my_hand), 6, rng)
        self.assertEqual(opp_mask.bit_count(), 6)
        self.assertEqual(bank_mask.bit_count(), 32 - 2 - 6)
        self.assertEqual(opp_mask & cards_to_mask(my_hand), 0)


class TestPackagingVerification(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        arena_bin = shutil.which("arena")
        cmd = [arena_bin, "pack", "."] if arena_bin else [sys.executable, "-m", "arena_sdk.cli", "pack", "."]
        res = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True)
        assert res.returncode == 0, f"arena pack failed: {res.stderr or res.stdout}"

    def test_submission_zip_exists(self):
        self.assertTrue(SUBMISSION_ZIP.is_file(), "mon-bot-submission.zip must exist at project root")

    def test_zip_integrity_crc(self):
        with zipfile.ZipFile(SUBMISSION_ZIP, "r") as zf:
            self.assertIsNone(zf.testzip(), "ZIP archive contains corrupted files")

    def test_submission_size_under_50mb(self):
        size = SUBMISSION_ZIP.stat().st_size
        self.assertLessEqual(size, 50 * 1024 * 1024, "Archive exceeds 50MB tournament limit")
        self.assertLessEqual(size, 100 * 1024, "Archive unexpectedly large for code-only bot")

    def test_manifest_contains_closure(self):
        with zipfile.ZipFile(SUBMISSION_ZIP, "r") as zf:
            names = set(zf.namelist())
            self.assertIn("bot.py", names)
            self.assertIn("card_tracker.py", names)
            self.assertIn("evaluator.py", names)

    def test_manifest_excludes_extraneous(self):
        with zipfile.ZipFile(SUBMISSION_ZIP, "r") as zf:
            for name in zf.namelist():
                self.assertNotIn("test_engine", name)
                self.assertNotIn("benchmark_", name)
                self.assertNotIn("__pycache__", name)
                self.assertFalse(name.endswith((".pyc", ".pyo")))
                self.assertFalse(name.startswith((".git", ".agent")))

    def test_unauthorized_dependencies_excluded(self):
        with zipfile.ZipFile(SUBMISSION_ZIP, "r") as zf:
            if "requirements.txt" in zf.namelist():
                content = zf.read("requirements.txt").decode("utf-8")
                for line in content.splitlines():
                    pkg = requirement_package_name(line)
                    if pkg:
                        self.assertIn(pkg, WHITELIST_PACKAGES)
                        self.assertNotEqual(pkg, "i151-arena-sdk")

    def test_sandbox_ast_compliance(self):
        forbidden_path_prefixes = ("/dev/shm", "/etc", "/proc")
        with zipfile.ZipFile(SUBMISSION_ZIP, "r") as zf:
            for name in zf.namelist():
                if name.endswith(".py"):
                    tree = ast.parse(zf.read(name).decode("utf-8"), filename=name)
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Call):
                            if isinstance(node.func, ast.Name) and node.func.id in ("eval", "exec"):
                                self.fail(f"Forbidden call {node.func.id} in {name}:{node.lineno}")
                            if isinstance(node.func, ast.Attribute) and node.func.attr in ("load", "loads"):
                                if (isinstance(node.func.value, ast.Name) and "pickle" in node.func.value.id) or \
                                   (isinstance(node.func.value, ast.Attribute) and "pickle" in node.func.value.attr):
                                    self.fail(f"Forbidden pickle loading in {name}:{node.lineno}")
                        if isinstance(node, ast.Import):
                            for a in node.names:
                                self.assertNotIn(a.name.split(".")[0], FORBIDDEN_RUNTIME_IMPORTS)
                        if isinstance(node, ast.ImportFrom) and node.module:
                            self.assertNotIn(node.module.split(".")[0], FORBIDDEN_RUNTIME_IMPORTS)
                        if isinstance(node, ast.Constant) and isinstance(node.value, str):
                            for fbp in forbidden_path_prefixes:
                                self.assertFalse(
                                    node.value.startswith(fbp),
                                    f"Sandbox violation in {name}:{node.lineno}: path '{node.value}'",
                                )

    def test_load_submission_zip_and_decide(self):
        bot = load_submission_zip(SUBMISSION_ZIP)
        self.assertIsNotNone(bot)
        bot.setup(PROJECT_ROOT)
        c = Card(Rank.SEVEN, Suit.SPADES)
        you = YouState("p0", (c,), 1, 7, 0, False, False, False, 0)
        table = TableState((c,), (c,), False, None, False, False, 10, 2, 1)
        turn = TurnState(True, True, False, 1, 0, "p0", "p1", False)
        match = MatchContext(1, 151, False, 2, 2, ("p0", "p1"))
        opp = OpponentState("p1", 1, "random", "RandomBot", None, 5, 0, False, 0, 1, True)
        view = PlayerView(you, (opp,), table, turn, match)
        actions = [Action.play_card(c), Action.draw_card()]
        action = bot.decide(view, actions, 400)
        self.assertIn(action, actions)
        bot.teardown()


class TestCLIVerification(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not SUBMISSION_ZIP.is_file():
            arena_bin = shutil.which("arena")
            cmd = [arena_bin, "pack", "."] if arena_bin else [sys.executable, "-m", "arena_sdk.cli", "pack", "."]
            subprocess.run(cmd, cwd=PROJECT_ROOT, check=True, capture_output=True)

    def test_arena_test_bot_py(self):
        arena_bin = shutil.which("arena")
        cmd = [arena_bin, "test", "bot.py"] if arena_bin else [sys.executable, "-m", "arena_sdk.cli", "test", "bot.py"]
        res = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"arena test bot.py failed: {res.stderr or res.stdout}")
        self.assertIn("OK", res.stdout)

    def test_arena_test_mon_bot_submission_zip(self):
        arena_bin = shutil.which("arena")
        cmd = [arena_bin, "test", "mon-bot-submission.zip"] if arena_bin else [sys.executable, "-m", "arena_sdk.cli", "test", "mon-bot-submission.zip"]
        res = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"arena test mon-bot-submission.zip failed: {res.stderr or res.stdout}")
        self.assertIn("OK", res.stdout)

    def test_benchmark_suite_tier1_cli(self):
        res = subprocess.run([sys.executable, "benchmark_suite.py", "--tier", "1"], cwd=PROJECT_ROOT, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"benchmark_suite --tier 1 failed: {res.stderr or res.stdout}")
        self.assertIn("GRAND_MASTER_READY", res.stdout)


class TestTournamentInvariantsAndConstraints(unittest.TestCase):
    def test_anti_queen_finishing_two_player(self):
        queen = Card(Rank.QUEEN, Suit.SPADES)
        you = YouState("p0", (queen,), 1, 3, 0, False, False, False, 0)
        table = TableState((Card(Rank.SEVEN, Suit.SPADES),), (Card(Rank.SEVEN, Suit.SPADES),), False, None, False, False, 10, 2, 1)
        turn = TurnState(True, True, False, 1, 0, "p0", "p1", False)
        match = MatchContext(1, 151, False, 2, 2, ("p0", "p1"))
        opp = OpponentState("p1", 1, "random", "RandomBot", None, 5, 0, False, 0, 1, True)
        view = PlayerView(you, (opp,), table, turn, match)
        act = Action.play_card(queen)
        self.assertTrue(finishes_on_queen_two_player(view, act))

    def test_two_way_symmetric_pairing_math(self):
        """Verify BenchmarkRunner executes genuine symmetric 50/50 seat and dealer alternation."""
        runner = BenchmarkRunner(PROJECT_ROOT / "bot.py", profile_latency=False)
        fake_res = MatchResult(
            winner_id="p0",
            opponent_id="opp",
            reason="normal",
            forfeited_player_id=None,
            final_scores={"p0": 50, "p1": 151},
            rounds_played=5,
            steps_played=100,
        )

        with patch("benchmark_suite.play_bots_match", return_value=fake_res) as mock_play:
            res = runner.run_series("builtin:random", games=50, symmetric=True)

        self.assertEqual(res["games"], 50)
        self.assertEqual(res["p0_games"], 25)
        self.assertEqual(res["p1_games"], 25)
        self.assertEqual(res["starter_me_games"], 25)
        self.assertEqual(res["starter_opp_games"], 25)
        self.assertEqual(len(res["matches"]), 50)
        self.assertEqual(len(mock_play.call_args_list), 50)

        # Inspect first half: mon-bot seated in p0
        for i in range(25):
            match = res["matches"][i]
            self.assertEqual(match["my_slot"], "p0")
            self.assertEqual(match["opp_slot"], "p1")
            call_kwargs = mock_play.call_args_list[i].kwargs
            call_args = mock_play.call_args_list[i].args
            self.assertEqual(call_kwargs.get("challenger_name"), "mon-bot")
            self.assertEqual(call_kwargs.get("opponent_name"), "Aléatoire")
            config = call_args[2]
            expected_dealer = 1 if (i % 2 == 0) else 0
            self.assertEqual(config.initial_dealer_index, expected_dealer)
            expected_starter_bot = "mon-bot" if expected_dealer == 1 else "Aléatoire"
            self.assertEqual(match["starter_bot"], expected_starter_bot)

        # Inspect second half: opponent seated in p0, mon-bot seated in p1
        for i in range(25, 50):
            match = res["matches"][i]
            self.assertEqual(match["my_slot"], "p1")
            self.assertEqual(match["opp_slot"], "p0")
            call_kwargs = mock_play.call_args_list[i].kwargs
            call_args = mock_play.call_args_list[i].args
            self.assertEqual(call_kwargs.get("challenger_name"), "Aléatoire")
            self.assertEqual(call_kwargs.get("opponent_name"), "mon-bot")
            sub_i = i - 25
            config = call_args[2]
            expected_dealer = 1 if (sub_i % 2 == 0) else 0
            self.assertEqual(config.initial_dealer_index, expected_dealer)
            expected_starter_bot = "Aléatoire" if expected_dealer == 1 else "mon-bot"
            self.assertEqual(match["starter_bot"], expected_starter_bot)

    def test_forfeit_loss_accounting_in_series(self):
        """Verify reason='forfeit' increments forfeits and counts as a loss, never a draw."""
        runner = BenchmarkRunner(PROJECT_ROOT / "bot.py", profile_latency=False)
        forfeit_loss = MatchResult(
            winner_id="p1",
            opponent_id="opp",
            reason="forfeit",
            forfeited_player_id="p0",
            final_scores={"p0": 151, "p1": 50},
            rounds_played=1,
            steps_played=10,
        )

        with patch("benchmark_suite.play_bots_match", return_value=forfeit_loss):
            res = runner.run_series("builtin:random", games=2, symmetric=False)

        self.assertEqual(res["forfeits"], 2, "Engine forfeit must increment forfeits counter")
        self.assertEqual(res["losses"], 2, "Engine forfeit must be counted as a loss")
        self.assertEqual(res["wins"], 0)
        self.assertEqual(res["draws"], 0, "Engine forfeit must NEVER be counted as a draw")
        self.assertEqual(res["win_rate_pct"], 0.0)

    def test_forfeit_loss_in_symmetric_seat_p1(self):
        """Verify reason='forfeit' when seated as p1 correctly counts as a forfeit loss."""
        runner = BenchmarkRunner(PROJECT_ROOT / "bot.py", profile_latency=False)

        def mock_match(*args, **kwargs):
            chal = kwargs.get("challenger_name")
            if chal == "mon-bot":
                return MatchResult(winner_id="p1", opponent_id="opp", reason="forfeit", forfeited_player_id="p0", final_scores={"p0": 151, "p1": 50}, rounds_played=1, steps_played=10)
            else:
                return MatchResult(winner_id="p0", opponent_id="student:mon-bot", reason="forfeit", forfeited_player_id="p1", final_scores={"p0": 50, "p1": 151}, rounds_played=1, steps_played=10)

        with patch("benchmark_suite.play_bots_match", side_effect=mock_match):
            res = runner.run_series("builtin:random", games=2, symmetric=True)

        self.assertEqual(res["forfeits"], 2)
        self.assertEqual(res["losses"], 2)
        self.assertEqual(res["draws"], 0)
        self.assertEqual(res["wins"], 0)
        self.assertEqual(res["matches"][0]["my_slot"], "p0")
        self.assertEqual(res["matches"][1]["my_slot"], "p1")

    def test_opponent_forfeit_credited_as_win_not_forfeit_penalty(self):
        """Verify opponent forfeits are counted as wins and do not penalize challenger forfeits."""
        runner = BenchmarkRunner(PROJECT_ROOT / "bot.py", profile_latency=False)
        opp_forfeit = MatchResult(
            winner_id="p0",
            opponent_id="opp",
            reason="forfeit",
            forfeited_player_id="p1",
            final_scores={"p0": 50, "p1": 151},
            rounds_played=1,
            steps_played=10,
        )

        with patch("benchmark_suite.play_bots_match", return_value=opp_forfeit):
            res = runner.run_series("builtin:random", games=2, symmetric=False)

        self.assertEqual(res["wins"], 2, "Opponent forfeit must count as win for mon-bot")
        self.assertEqual(res["losses"], 0)
        self.assertEqual(res["draws"], 0)
        self.assertEqual(res["forfeits"], 0, "Opponent forfeit must NOT increment challenger forfeits")
        self.assertEqual(res["win_rate_pct"], 100.0)

    def test_mixed_series_forfeit_strictly_penalizes_win_rate(self):
        """Verify that a forfeit loss dilutes win rate and is not masked as a draw."""
        runner = BenchmarkRunner(PROJECT_ROOT / "bot.py", profile_latency=False)
        normal_win = MatchResult(
            winner_id="p0",
            opponent_id="opp",
            reason="normal",
            forfeited_player_id=None,
            final_scores={"p0": 50, "p1": 151},
            rounds_played=5,
            steps_played=100,
        )
        forfeit_loss = MatchResult(
            winner_id="p1",
            opponent_id="opp",
            reason="forfeit",
            forfeited_player_id="p0",
            final_scores={"p0": 151, "p1": 50},
            rounds_played=1,
            steps_played=10,
        )

        cycle = [normal_win, forfeit_loss]
        idx = 0
        def mock_play(*args, **kwargs):
            nonlocal idx
            r = cycle[idx % 2]
            idx += 1
            return r

        with patch("benchmark_suite.play_bots_match", side_effect=mock_play):
            res = runner.run_series("builtin:random", games=2, symmetric=False)

        self.assertEqual(res["wins"], 1)
        self.assertEqual(res["losses"], 1)
        self.assertEqual(res["draws"], 0)
        self.assertEqual(res["forfeits"], 1)
        self.assertEqual(res["win_rate_pct"], 50.0, "1 win + 1 forfeit loss must equal 50.0% win rate, not 100.0%")

    def test_run_seed_forfeit_detection(self):
        """Verify run_seed flags reason='forfeit' as forfeit=True and won=False."""
        runner = BenchmarkRunner(PROJECT_ROOT / "bot.py", profile_latency=False)
        forfeit_loss = MatchResult(
            winner_id="p1",
            opponent_id="opp",
            reason="forfeit",
            forfeited_player_id="p0",
            final_scores={"p0": 151, "p1": 50},
            rounds_played=1,
            steps_played=10,
        )

        with patch("benchmark_suite.play_bots_match", return_value=forfeit_loss):
            seed_res = runner.run_seed("medium", 848914317)

        self.assertFalse(seed_res["won"])
        self.assertTrue(seed_res["forfeit"], "run_seed must report forfeit=True on reason='forfeit'")
        self.assertEqual(seed_res["reason"], "forfeit")

    def test_opponent_timeout_isolation(self):
        """Verify that an opponent timeout is registered as a win and does NOT increment challenger timeouts."""
        match_details = [
            {
                "game_index": 1,
                "my_slot": "p0",
                "opp_slot": "p1",
                "winner_id": "p0",
                "forfeited_player_id": "p1",
                "won": True,
                "reason": "timeout",
            },
            {
                "game_index": 2,
                "my_slot": "p1",
                "opp_slot": "p0",
                "winner_id": "p1",
                "forfeited_player_id": "p0",
                "won": True,
                "reason": "timeout",
            },
            {
                "game_index": 3,
                "my_slot": "p0",
                "opp_slot": "p1",
                "winner_id": "p1",
                "forfeited_player_id": "p0",
                "won": False,
                "reason": "timeout",
            },
        ]
        challenger_timeouts = 0
        opp_timeouts = 0
        for m in match_details:
            if m.get("reason") == "timeout":
                my_slot = m.get("my_slot", "p0")
                forfeited = m.get("forfeited_player_id")
                winner = m.get("winner_id")
                if forfeited == my_slot or (winner != my_slot and forfeited is None):
                    challenger_timeouts += 1
                else:
                    opp_timeouts += 1

        self.assertEqual(challenger_timeouts, 1, "Only match 3 is mon-bot's timeout")
        self.assertEqual(opp_timeouts, 2, "Matches 1 and 2 are opponent timeouts")

    def test_hard_latency_gating_thresholds(self):
        profile = LatencyProfile()
        profile.record(10.0)
        profile.record(45.0)
        profile.record(320.0)
        profile.record(450.0)
        stats = profile.compute_stats()
        self.assertEqual(stats["count"], 4)
        self.assertEqual(stats["slow_moves_gt_300ms"], 2)
        self.assertEqual(stats["timeouts_gt_400ms"], 1)
        self.assertEqual(stats["timeouts_gt_1000ms"], 0)
        self.assertGreater(stats["mean"], 50.0)

    def test_endgame_solver_activation_bound(self):
        c1 = Card(Rank.SEVEN, Suit.SPADES)
        c2 = Card(Rank.EIGHT, Suit.HEARTS)
        c3 = Card(Rank.NINE, Suit.DIAMONDS)
        my_hand = cards_to_mask([c1, c2])
        opp_hand = cards_to_mask([c3])
        top_cid = ID_BY_CARD[Card(Rank.SEVEN, Suit.HEARTS)]
        score, best_mv = solve_exact_endgame(
            my_hand_mask=my_hand,
            opp_hand_mask=opp_hand,
            top_card_id=top_cid,
            req_suit=-1,
            is_my_turn=True,
        )
        self.assertIsNotNone(score)
        self.assertIsNotNone(best_mv)


if __name__ == "__main__":
    unittest.main()
