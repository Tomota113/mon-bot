#!/usr/bin/env python3
"""i151 Grand Master Automated Tournament Benchmark & Verification Suite (R4).

Comprehensive automated test harness for validating i151 arena bots:
- Tier 1: Smoke test, packaging & AST integrity, anti-Queen 2P invariant filter, suit choice & legality.
- Tier 2: Baselines vs builtin:random and builtin:basic (>= 98% win rate, 0 forfeits).
- Tier 3: Tactical match vs builtin:medium (>= 70% win rate across 50 symmetric games, 0 forfeits, move latency profiling).
- Tier 4: Leaderboard reference seeds (848914317, 1477911113, 2063595735, 329389206) vs builtin:medium (>= 75% win rate, 0 forfeits).
"""

from __future__ import annotations

import argparse
import ast
import datetime
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Sequence

from arena_sdk import (
    Action,
    ActionType,
    MatchConfig,
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
from arena_sdk.opponents import (
    load_resolved_submission,
    resolve_opponent_arg,
    resolve_submission_path,
)
from arena_sdk.pack import (
    PackError,
    WHITELIST_PACKAGES,
    build_submission_zip,
    collect_local_module_closure,
    requirement_package_name,
    validate_submission_project,
    validate_submission_zip,
)
from i151_engine.bots.protocol import Bot
from i151_engine.models.card import Card, Rank, Suit
from i151_engine.runner.match_runner import play_bots_match, play_match


# ANSI Color formatting helper
class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

    @classmethod
    def disable_if_no_color(cls) -> None:
        if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
            cls.RESET = ""
            cls.BOLD = ""
            cls.DIM = ""
            cls.RED = ""
            cls.GREEN = ""
            cls.YELLOW = ""
            cls.BLUE = ""
            cls.MAGENTA = ""
            cls.CYAN = ""
            cls.WHITE = ""


# Latency Statistics Tracker
@dataclass
class LatencyProfile:
    latencies_ms: list[float] = field(default_factory=list)

    def record(self, duration_ms: float) -> None:
        self.latencies_ms.append(duration_ms)

    def compute_stats(self) -> dict[str, Any]:
        if not self.latencies_ms:
            return {
                "count": 0,
                "min": 0.0,
                "mean": 0.0,
                "median": 0.0,
                "p90": 0.0,
                "p95": 0.0,
                "p99": 0.0,
                "max": 0.0,
                "slow_moves_gt_300ms": 0,
                "timeouts_gt_400ms": 0,
                "timeouts_gt_1000ms": 0,
                "budget_compliance_pct": 100.0,
            }
        s = sorted(self.latencies_ms)
        n = len(s)

        def percentile(pct: float) -> float:
            k = (n - 1) * (pct / 100.0)
            f = int(k)
            c = min(f + 1, n - 1)
            d = k - f
            return round(s[f] + d * (s[c] - s[f]), 3)

        gt_300 = sum(1 for x in s if x > 300.0)
        gt_400 = sum(1 for x in s if x > 400.0)
        gt_1000 = sum(1 for x in s if x > 1000.0)
        compliance = round(100.0 * (1.0 - gt_300 / n), 2)

        return {
            "count": n,
            "min": round(s[0], 3),
            "mean": round(sum(s) / n, 3),
            "median": percentile(50.0),
            "p90": percentile(90.0),
            "p95": percentile(95.0),
            "p99": percentile(99.0),
            "max": round(s[-1], 3),
            "slow_moves_gt_300ms": gt_300,
            "timeouts_gt_400ms": gt_400,
            "timeouts_gt_1000ms": gt_1000,
            "budget_compliance_pct": compliance,
        }


# Instrumented Bot wrapper to measure per-move decision latency
class InstrumentedBot:
    def __init__(self, inner: Bot, profile: LatencyProfile | None = None) -> None:
        self._inner = inner
        self.profile = profile or LatencyProfile()

    def setup(self, submission_dir: Path) -> None:
        self._inner.setup(submission_dir)

    def decide(
        self, view: PlayerView, legal_actions: list[Action], time_left_ms: int
    ) -> Action:
        t0 = time.perf_counter()
        try:
            action = self._inner.decide(view, legal_actions, time_left_ms)
            return action
        finally:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            self.profile.record(elapsed_ms)

    def observe(self, view: PlayerView) -> None:
        observe_fn = getattr(self._inner, "observe", None)
        if callable(observe_fn):
            observe_fn(view)

    def teardown(self) -> None:
        self._inner.teardown()


# Match execution helper
def run_single_match(
    challenger_bot: Bot,
    challenger_dir: Path,
    opponent_spec: str,
    seed: int,
    target_score: int = 151,
    starter: str = "p0",
    decision_timeout_ms: int = 400,
) -> tuple[MatchResult, str]:
    """Exécute un match isolé et retourne le résultat."""
    # Dealer: 1 means p0 starts, 0 means p1 starts
    dealer = 1 if starter == "p0" else 0
    opp = resolve_opponent_arg(opponent_spec)

    challenger_bot.setup(challenger_dir)
    opp.bot.setup(opp.submission_dir or Path("."))

    config = MatchConfig(
        seed=seed,
        target_score=target_score,
        initial_dealer_index=dealer,
        decision_timeout_ms=decision_timeout_ms,
    )

    result = play_bots_match(
        challenger_bot,
        opp.bot,
        config,
        challenger_name="mon-bot",
        opponent_name=opp.name,
        opponent_id=opp.opponent_id,
        challenger_dir=challenger_dir,
        opponent_dir=opp.submission_dir,
        manage_lifecycle=False,
    )

    challenger_bot.teardown()
    opp.bot.teardown()

    return result, opp.name


# Tier 1 Invariant & Sanity Verifier
class Tier1Verifier:
    def __init__(self, bot_path: Path, challenger_dir: Path) -> None:
        self.bot_path = bot_path
        self.challenger_dir = challenger_dir

    def run_all(self) -> dict[str, Any]:
        results: dict[str, Any] = {}

        # 1. Smoke test vs random (seed 42)
        results["smoke_test"] = self._verify_smoke_test()

        # 2. Packaging & AST check
        results["packaging"] = self._verify_packaging()

        # 3. Anti-Queen 2P Invariant
        results["anti_queen_2p"] = self._verify_anti_queen_invariant()

        # 4. Suit choice validity
        results["suit_choice"] = self._verify_suit_choice()

        # 5. Legal action adherence
        results["legality_adherence"] = self._verify_legality_adherence()

        all_passed = all(check.get("passed", False) for check in results.values())
        return {
            "passed": all_passed,
            "checks": results,
            "total_checks": len(results),
            "passed_checks": sum(1 for c in results.values() if c.get("passed", False)),
        }

    def _verify_smoke_test(self) -> dict[str, Any]:
        try:
            bot, root = load_resolved_submission(self.bot_path)
            res = play_match(
                bot,
                "builtin:random",
                MatchConfig(seed=42, target_score=151, max_rounds=40, decision_timeout_ms=400),
                challenger_name="mon-bot",
                challenger_dir=root,
            )
            passed = res.reason == "normal" and res.forfeited_player_id is None
            return {
                "passed": passed,
                "winner_id": res.winner_id,
                "reason": res.reason,
                "rounds": res.rounds_played,
                "scores": res.final_scores,
                "message": (
                    "Smoke test passed with 0 forfeits"
                    if passed
                    else f"Failed: {res.reason}"
                ),
            }
        except Exception as exc:
            return {"passed": False, "error": str(exc), "message": f"Exception: {exc}"}

    def _verify_packaging(self) -> dict[str, Any]:
        """Verify arena pack . CLI execution, zipfile validity, dependencies, and sandbox AST."""
        root = self.challenger_dir.resolve()
        expected_zip_name = f"{root.name}-submission.zip"
        zip_path = root / expected_zip_name

        # 1. Run official CLI command `arena pack .`
        arena_bin = shutil.which("arena")
        if arena_bin:
            cmd = [arena_bin, "pack", "."]
        else:
            cmd = [sys.executable, "-m", "arena_sdk.cli", "pack", "."]

        try:
            proc = subprocess.run(
                cmd,
                cwd=root,
                capture_output=True,
                text=True,
                timeout=15,
            )
            if proc.returncode != 0:
                return {
                    "passed": False,
                    "error": proc.stderr or proc.stdout,
                    "message": f"`arena pack .` failed (exit {proc.returncode}): {proc.stderr.strip()}",
                }
        except Exception as exc:
            return {
                "passed": False,
                "error": str(exc),
                "message": f"Failed to execute `arena pack .`: {exc}",
            }

        # 2. Check artifact existence & size limit (<= 50 MB)
        if not zip_path.is_file():
            return {
                "passed": False,
                "message": f"Artifact {expected_zip_name} was not generated at {root}",
            }

        zip_size_bytes = zip_path.stat().st_size
        max_size_bytes = 50 * 1024 * 1024  # 50 MB
        if zip_size_bytes > max_size_bytes:
            return {
                "passed": False,
                "message": f"ZIP size {zip_size_bytes} exceeds 50MB limit ({max_size_bytes} bytes)",
            }

        # 3. ZipFile structural integrity & CRC verification
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                corrupted = zf.testzip()
                if corrupted is not None:
                    return {
                        "passed": False,
                        "message": f"Corrupted file in ZIP archive: {corrupted}",
                    }
                namelist = zf.namelist()

                # 4. Manifest checks: bot.py and AST module closure
                if "bot.py" not in namelist:
                    return {"passed": False, "message": "bot.py missing from submission archive"}

                entry_path = root / "bot.py"
                closure = collect_local_module_closure(root, entry_path)
                for mod in closure:
                    expected_file = "bot.py" if mod == "bot" else f"{mod}.py"
                    if expected_file not in namelist:
                        return {
                            "passed": False,
                            "message": f"Required module closure file '{expected_file}' missing from archive",
                        }

                # Check forbidden/extraneous files
                forbidden_patterns = ("test_engine", "benchmark_", "__pycache__", ".pyc", ".git", ".agent")
                for item in namelist:
                    if any(fp in item for fp in forbidden_patterns):
                        return {
                            "passed": False,
                            "message": f"Extraneous/forbidden item packaged in ZIP: {item}",
                        }

                # 5. Dependency whitelist check
                if "requirements.txt" in namelist:
                    req_content = zf.read("requirements.txt").decode("utf-8")
                    for line in req_content.splitlines():
                        pkg = requirement_package_name(line)
                        if pkg and pkg not in WHITELIST_PACKAGES:
                            return {
                                "passed": False,
                                "message": f"Unauthorized dependency in packaged requirements.txt: {pkg}",
                            }

                # 6. Strict sandbox AST inspection
                forbidden_path_prefixes = ("/dev/shm", "/etc", "/proc")
                for arcname in namelist:
                    if arcname.endswith(".py"):
                        source_code = zf.read(arcname).decode("utf-8")
                        tree = ast.parse(source_code, filename=arcname)
                        for node in ast.walk(tree):
                            # Forbidden calls: eval, exec, pickle.load, pickle.loads
                            if isinstance(node, ast.Call):
                                if isinstance(node.func, ast.Name) and node.func.id in ("eval", "exec"):
                                    return {
                                        "passed": False,
                                        "message": f"Sandbox violation in {arcname}:{node.lineno}: forbidden call '{node.func.id}()'",
                                    }
                                if isinstance(node.func, ast.Attribute) and node.func.attr in ("load", "loads"):
                                    if (isinstance(node.func.value, ast.Name) and "pickle" in node.func.value.id) or \
                                       (isinstance(node.func.value, ast.Attribute) and "pickle" in node.func.value.attr):
                                        return {
                                            "passed": False,
                                            "message": f"Sandbox violation in {arcname}:{node.lineno}: forbidden pickle loading",
                                        }
                            # Forbidden imports
                            if isinstance(node, ast.Import):
                                for alias in node.names:
                                    mod_root = alias.name.split(".")[0]
                                    if mod_root in FORBIDDEN_RUNTIME_IMPORTS:
                                        return {
                                            "passed": False,
                                            "message": f"Sandbox violation in {arcname}:{node.lineno}: forbidden import '{mod_root}'",
                                        }
                            if isinstance(node, ast.ImportFrom) and node.module:
                                mod_root = node.module.split(".")[0]
                                if mod_root in FORBIDDEN_RUNTIME_IMPORTS:
                                    return {
                                        "passed": False,
                                        "message": f"Sandbox violation in {arcname}:{node.lineno}: forbidden import from '{mod_root}'",
                                    }
                            # Check string literals for forbidden paths (/dev/shm, /etc, /proc)
                            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                                for fbp in forbidden_path_prefixes:
                                    if node.value.startswith(fbp):
                                        return {
                                            "passed": False,
                                            "message": f"Sandbox violation in {arcname}:{node.lineno}: reading outside submission_dir ('{node.value}')",
                                        }

            # 7. Functional load verification using load_submission_zip
            loaded_bot = load_submission_zip(zip_path)
            if loaded_bot is None:
                return {"passed": False, "message": "load_submission_zip returned None"}

            return {
                "passed": True,
                "zip_path": str(zip_path),
                "size_bytes": zip_size_bytes,
                "entries": namelist,
                "message": f"Valid submission ZIP ({zip_size_bytes / 1024:.1f} KB, {len(namelist)} files, AST closure & sandbox compliant)",
            }
        except Exception as exc:
            return {
                "passed": False,
                "error": str(exc),
                "message": f"Packaging verification exception: {exc}",
            }

    def _verify_anti_queen_invariant(self) -> dict[str, Any]:
        """Verify the bot never chooses a solitary Queen finish in 2P mode."""
        try:
            bot, root = load_resolved_submission(self.bot_path)
            bot.setup(root)

            # Scenario 1: Hand has 1 Queen, 2-player match, legal action has PLAY_CARD(Queen) and DRAW_CARD
            queen_spades = Card(rank=Rank.QUEEN, suit=Suit.SPADES)
            you_state = YouState(
                player_id="p0",
                hand=(queen_spades,),
                hand_size=1,
                hand_points=3,
                total_score=50,
                is_excluded=False,
                has_drawn_this_turn=False,
                is_chaining=False,
                consecutive_round_wins=0,
            )
            table_state = TableState(
                recent_cards=(Card(rank=Rank.SEVEN, suit=Suit.SPADES),),
                last_play_cards=(Card(rank=Rank.SEVEN, suit=Suit.SPADES),),
                table_empty=False,
                required_suit=None,
                must_choose_suit=False,
                ace_effect_active=False,
                bank_size=12,
                played_pile_size=15,
                last_play_count=1,
            )
            turn_state = TurnState(
                is_your_turn=True,
                can_draw=True,
                can_pass=False,
                draw_count_if_draw=1,
                step_index=10,
                current_player_id="p0",
                next_player_id="p1",
                is_chaining=False,
            )
            match_ctx = MatchContext(
                round_number=1,
                target_score=151,
                you_are_dealer=False,
                player_count=2,
                active_player_count=2,
                seats=("p0", "p1"),
            )
            opp_state = OpponentState(
                player_id="p1",
                seat_index=1,
                opponent_id="random",
                name="RandomBot",
                tier=None,
                hand_size=5,
                total_score=60,
                is_excluded=False,
                consecutive_round_wins=0,
                turns_until_next=1,
                is_next_to_play=True,
            )
            view = PlayerView(
                you=you_state,
                opponents=(opp_state,),
                table=table_state,
                turn=turn_state,
                match=match_ctx,
            )

            play_queen = Action.play_card(queen_spades)
            draw_card = Action.draw_card()
            chosen = bot.decide(view, [play_queen, draw_card], time_left_ms=1000)

            # In 2P with 1 card remaining being Queen, playing it causes forced draw loop trap
            # Chosen action must NOT be play_queen when another legal alternative exists
            passed = chosen.type != ActionType.PLAY_CARD or chosen.card != queen_spades

            bot.teardown()
            return {
                "passed": passed,
                "chosen_action": str(chosen),
                "message": (
                    "Anti-Queen 2P trap successfully filtered (avoided solitary Queen play)"
                    if passed
                    else "FAILED: Bot chose solitary Queen in 2P endgame"
                ),
            }
        except Exception as exc:
            return {"passed": False, "error": str(exc), "message": f"Exception: {exc}"}

    def _verify_suit_choice(self) -> dict[str, Any]:
        """Verify the bot produces valid chosen_suit when required."""
        try:
            bot, root = load_resolved_submission(self.bot_path)
            bot.setup(root)

            you_state = YouState(
                player_id="p0",
                hand=(Card(Rank.SEVEN, Suit.HEARTS), Card(Rank.KING, Suit.HEARTS)),
                hand_size=2,
                hand_points=11,
                total_score=30,
                is_excluded=False,
                has_drawn_this_turn=False,
                is_chaining=False,
                consecutive_round_wins=0,
            )
            table_state = TableState(
                recent_cards=(Card(Rank.EIGHT, Suit.DIAMONDS),),
                last_play_cards=(Card(Rank.EIGHT, Suit.DIAMONDS),),
                table_empty=False,
                required_suit=None,
                must_choose_suit=True,
                ace_effect_active=False,
                bank_size=10,
                played_pile_size=10,
                last_play_count=1,
            )
            turn_state = TurnState(
                is_your_turn=True,
                can_draw=False,
                can_pass=False,
                draw_count_if_draw=1,
                step_index=5,
                current_player_id="p0",
                next_player_id="p1",
                is_chaining=False,
            )
            match_ctx = MatchContext(
                round_number=1,
                target_score=151,
                you_are_dealer=True,
                player_count=2,
                active_player_count=2,
                seats=("p0", "p1"),
            )
            opp_state = OpponentState(
                player_id="p1",
                seat_index=1,
                opponent_id="random",
                name="RandomBot",
                tier=None,
                hand_size=4,
                total_score=40,
                is_excluded=False,
                consecutive_round_wins=0,
                turns_until_next=1,
                is_next_to_play=True,
            )
            view = PlayerView(
                you=you_state,
                opponents=(opp_state,),
                table=table_state,
                turn=turn_state,
                match=match_ctx,
            )

            actions = [
                Action.choose_suit(s)
                for s in (Suit.SPADES, Suit.HEARTS, Suit.DIAMONDS, Suit.CLUBS)
            ]
            chosen = bot.decide(view, actions, time_left_ms=1000)

            passed = chosen.type == ActionType.CHOOSE_SUIT and chosen.chosen_suit in (
                Suit.SPADES,
                Suit.HEARTS,
                Suit.DIAMONDS,
                Suit.CLUBS,
            )

            bot.teardown()
            return {
                "passed": passed,
                "chosen_suit": chosen.chosen_suit.value if chosen.chosen_suit else None,
                "message": (
                    f"Suit choice valid: {chosen.chosen_suit}"
                    if passed
                    else "Invalid suit choice"
                ),
            }
        except Exception as exc:
            return {"passed": False, "error": str(exc), "message": f"Exception: {exc}"}

    def _verify_legality_adherence(self) -> dict[str, Any]:
        """Verify the bot always returns an action within legal_actions."""
        try:
            bot, root = load_resolved_submission(self.bot_path)
            bot.setup(root)

            # Test multiple synthetic action lists
            for i in range(10):
                c1 = Card(Rank.SEVEN, Suit.SPADES)
                c2 = Card(Rank.TEN, Suit.HEARTS)
                actions = [
                    Action.play_card(c1),
                    Action.play_card(c2),
                    Action.draw_card(),
                ]
                you_state = YouState("p0", (c1, c2), 2, 17, 0, False, False, False, 0)
                table_state = TableState(
                    (c1,), (c1,), False, None, False, False, 20, 2, 1
                )
                turn_state = TurnState(True, True, False, 1, i, "p0", "p1", False)
                match_ctx = MatchContext(1, 151, False, 2, 2, ("p0", "p1"))
                opp_state = OpponentState(
                    "p1", 1, "random", "RandomBot", None, 5, 0, False, 0, 1, True
                )
                view = PlayerView(
                    you_state, (opp_state,), table_state, turn_state, match_ctx
                )

                chosen = bot.decide(view, actions, 1000)
                if chosen not in actions:
                    bot.teardown()
                    return {
                        "passed": False,
                        "message": f"Action {chosen} was not in legal actions {actions}",
                    }

            bot.teardown()
            return {
                "passed": True,
                "message": "100% compliance: Returned actions strictly in legal_actions",
            }
        except Exception as exc:
            return {"passed": False, "error": str(exc), "message": f"Exception: {exc}"}


# Symmetric pairing helper
def compute_symmetric_slot(i: int, total_games: int) -> tuple[str, str, int, str]:
    """Computes (my_slot, opp_slot, dealer, starter_slot) for game i in a symmetric series."""
    half = total_games // 2
    is_p0 = (i < half)
    sub_i = i if is_p0 else (i - half)
    dealer = 1 if (sub_i % 2 == 0) else 0
    my_slot = "p0" if is_p0 else "p1"
    opp_slot = "p1" if is_p0 else "p0"
    starter_slot = "p0" if dealer == 1 else "p1"
    return my_slot, opp_slot, dealer, starter_slot


# Benchmark Series Runner
class BenchmarkRunner:
    def __init__(
        self,
        bot_path: Path,
        profile_latency: bool = True,
        target_score: int = 151,
        verbose: bool = False,
    ) -> None:
        self.bot_path = bot_path
        self.bot_raw, self.challenger_dir = load_resolved_submission(bot_path)
        self.latency_profile = LatencyProfile()
        self.instrumented_bot = (
            InstrumentedBot(self.bot_raw, self.latency_profile)
            if profile_latency
            else self.bot_raw
        )
        self.target_score = target_score
        self.verbose = verbose

    def run_series(
        self,
        opponent_spec: str,
        games: int,
        base_seed: int = 42,
        randomize_seeds: bool = False,
        p0_starter_rate: float = 0.5,
        symmetric: bool = True,
    ) -> dict[str, Any]:
        """Runs a series of matches against an opponent and gathers statistics.

        When symmetric=True (default), allocates exactly games // 2 matches with
        mon-bot as challenger p0 and the remaining matches with mon-bot as opponent p1.
        Alternates dealer=1 and dealer=0 in each half so starting player is split 50/50.
        """
        opp = resolve_opponent_arg(opponent_spec)
        seeds: list[int] = []
        if randomize_seeds:
            rng = random.Random(base_seed)
            seeds = [rng.randint(1, 2_000_000_000) for _ in range(games)]
        else:
            seeds = [base_seed + i for i in range(games)]

        wins = 0
        losses = 0
        draws = 0
        forfeits = 0
        match_details: list[dict[str, Any]] = []

        opp_name = opp.name
        half = games // 2

        for i, seed in enumerate(seeds):
            if symmetric:
                my_slot, opp_slot, dealer, starter_slot = compute_symmetric_slot(i, games)
                is_p0 = (my_slot == "p0")
            else:
                is_p0 = True
                p0_starts = (
                    (i % 2 == 0)
                    if p0_starter_rate == 0.5
                    else (i / max(1, games) < p0_starter_rate)
                )
                dealer = 1 if p0_starts else 0
                my_slot = "p0"
                opp_slot = "p1"
                starter_slot = "p0" if dealer == 1 else "p1"

            starter_bot = "mon-bot" if starter_slot == my_slot else opp_name

            self.instrumented_bot.setup(self.challenger_dir)
            opp.bot.setup(opp.submission_dir or Path("."))

            config = MatchConfig(
                seed=seed,
                target_score=self.target_score,
                initial_dealer_index=dealer,
                decision_timeout_ms=400,
            )

            if is_p0:
                res = play_bots_match(
                    self.instrumented_bot,
                    opp.bot,
                    config,
                    challenger_name="mon-bot",
                    opponent_name=opp_name,
                    opponent_id=opp.opponent_id,
                    challenger_dir=self.challenger_dir,
                    opponent_dir=opp.submission_dir,
                    manage_lifecycle=False,
                )
            else:
                res = play_bots_match(
                    opp.bot,
                    self.instrumented_bot,
                    config,
                    challenger_name=opp_name,
                    opponent_name="mon-bot",
                    opponent_id="student:mon-bot",
                    challenger_dir=opp.submission_dir,
                    opponent_dir=self.challenger_dir,
                    manage_lifecycle=False,
                )

            self.instrumented_bot.teardown()
            opp.bot.teardown()

            is_win = res.winner_id == my_slot and res.reason == "normal"
            is_loss = res.winner_id == opp_slot and res.reason == "normal"
            is_forfeit_loss = (
                res.winner_id == opp_slot or res.forfeited_player_id == my_slot
            ) and (res.reason != "normal")
            is_forfeit_win = (
                res.winner_id == my_slot or res.forfeited_player_id == opp_slot
            ) and (res.reason != "normal")

            won = is_win or is_forfeit_win
            if won:
                wins += 1
            elif is_loss or is_forfeit_loss:
                losses += 1
                if is_forfeit_loss:
                    forfeits += 1
            else:
                draws += 1

            my_score = res.final_scores.get(my_slot, 0)
            opp_score = res.final_scores.get(opp_slot, 0)

            detail = {
                "game_index": i + 1,
                "seed": seed,
                "my_slot": my_slot,
                "opp_slot": opp_slot,
                "starter": starter_slot,
                "starter_bot": starter_bot,
                "winner_id": res.winner_id,
                "winner_bot": "mon-bot" if res.winner_id == my_slot else opp_name,
                "won": won,
                "reason": res.reason,
                "forfeited_player_id": res.forfeited_player_id,
                "is_forfeit_loss": is_forfeit_loss,
                "scores": res.final_scores,
                "my_score": my_score,
                "opp_score": opp_score,
                "rounds": res.rounds_played,
                "steps": res.steps_played,
            }
            match_details.append(detail)

            if self.verbose:
                status_str = (
                    f"{Colors.GREEN}WIN{Colors.RESET}"
                    if won
                    else (
                        f"{Colors.RED}LOSS{Colors.RESET}"
                        if (is_loss or is_forfeit_loss)
                        else f"{Colors.YELLOW}{res.reason}{Colors.RESET}"
                    )
                )
                print(
                    f"  Game {i+1:02d}/{games:02d} [seed={seed}, slot={my_slot}, start={starter_bot}]: "
                    f"{status_str} (Scores: mon-bot={my_score}, opp={opp_score}, Rounds: {res.rounds_played})"
                )

        total_matches = len(match_details)
        win_rate = (wins / total_matches) if total_matches > 0 else 0.0

        p0_matches = [m for m in match_details if m["my_slot"] == "p0"]
        p1_matches = [m for m in match_details if m["my_slot"] == "p1"]
        p0_wins = sum(1 for m in p0_matches if m["won"])
        p1_wins = sum(1 for m in p1_matches if m["won"])

        starter_me_matches = [m for m in match_details if m["starter_bot"] == "mon-bot"]
        starter_opp_matches = [m for m in match_details if m["starter_bot"] != "mon-bot"]
        starter_me_wins = sum(1 for m in starter_me_matches if m["won"])
        starter_opp_wins = sum(1 for m in starter_opp_matches if m["won"])

        return {
            "opponent_spec": opponent_spec,
            "opponent_name": opp_name,
            "games": games,
            "wins": wins,
            "losses": losses,
            "draws": draws,
            "forfeits": forfeits,
            "win_rate": round(win_rate, 4),
            "win_rate_pct": round(win_rate * 100.0, 2),
            "symmetric": symmetric,
            "p0_games": len(p0_matches),
            "p0_wins": p0_wins,
            "p0_win_rate_pct": round(p0_wins / max(1, len(p0_matches)) * 100.0, 2) if p0_matches else 0.0,
            "p1_games": len(p1_matches),
            "p1_wins": p1_wins,
            "p1_win_rate_pct": round(p1_wins / max(1, len(p1_matches)) * 100.0, 2) if p1_matches else 0.0,
            "starter_me_games": len(starter_me_matches),
            "starter_me_wins": starter_me_wins,
            "starter_me_win_rate_pct": round(starter_me_wins / max(1, len(starter_me_matches)) * 100.0, 2) if starter_me_matches else 0.0,
            "starter_opp_games": len(starter_opp_matches),
            "starter_opp_wins": starter_opp_wins,
            "starter_opp_win_rate_pct": round(starter_opp_wins / max(1, len(starter_opp_matches)) * 100.0, 2) if starter_opp_matches else 0.0,
            "matches": match_details,
        }

    def run_seed(self, opponent_spec: str, seed: int) -> dict[str, Any]:
        """Runs a single deterministic seed match vs opponent (p0 starts)."""
        opp = resolve_opponent_arg(opponent_spec)
        self.instrumented_bot.setup(self.challenger_dir)
        opp.bot.setup(opp.submission_dir or Path("."))

        config = MatchConfig(
            seed=seed,
            target_score=self.target_score,
            initial_dealer_index=1,  # p0 starts
            decision_timeout_ms=400,
        )

        res = play_bots_match(
            self.instrumented_bot,
            opp.bot,
            config,
            challenger_name="mon-bot",
            opponent_name=opp.name,
            opponent_id=opp.opponent_id,
            challenger_dir=self.challenger_dir,
            opponent_dir=opp.submission_dir,
            manage_lifecycle=False,
        )

        self.instrumented_bot.teardown()
        opp.bot.teardown()

        is_win = res.winner_id == "p0" and res.reason == "normal"
        is_forfeit_win = (
            res.winner_id == "p0" or res.forfeited_player_id == "p1"
        ) and (res.reason != "normal")
        is_forfeit_loss = (
            res.winner_id == "p1" or res.forfeited_player_id == "p0"
        ) and (res.reason != "normal")
        won = is_win or is_forfeit_win

        return {
            "seed": seed,
            "opponent": opp.name,
            "winner_id": res.winner_id,
            "winner": "mon-bot" if res.winner_id == "p0" else opp.name,
            "reason": res.reason,
            "forfeited_player_id": res.forfeited_player_id,
            "my_slot": "p0",
            "opp_slot": "p1",
            "won": won,
            "forfeit": is_forfeit_loss,
            "scores": res.final_scores,
            "rounds": res.rounds_played,
            "steps": res.steps_played,
        }


# Formatting and Output Rendering
class ReportFormatter:
    @staticmethod
    def print_header(bot_path: Path, tier: str, timestamp: str) -> None:
        print(
            f"\n{Colors.BOLD}{Colors.CYAN}╔══════════════════════════════════════════════════════════════════════════════╗{Colors.RESET}"
        )
        print(
            f"{Colors.BOLD}{Colors.CYAN}║                i151 GRAND MASTER BENCHMARK & TEST SUITE (R4)                 ║{Colors.RESET}"
        )
        print(
            f"{Colors.BOLD}{Colors.CYAN}╚══════════════════════════════════════════════════════════════════════════════╝{Colors.RESET}"
        )
        print(f"  {Colors.BOLD}Target Bot:{Colors.RESET}   {bot_path.resolve()}")
        print(f"  {Colors.BOLD}Timestamp:{Colors.RESET}    {timestamp}")
        print(f"  {Colors.BOLD}Tier Mode:{Colors.RESET}    {tier.upper()}")
        print(
            f"{Colors.DIM}────────────────────────────────────────────────────────────────────────────────{Colors.RESET}"
        )

    @staticmethod
    def print_tier1_results(tier1_data: dict[str, Any]) -> None:
        print(
            f"\n{Colors.BOLD}[TIER 1: SANITY, PACKAGING & INVARIANT CHECKS]{Colors.RESET}"
        )
        checks = tier1_data["checks"]

        c_smoke = checks["smoke_test"]
        c_pack = checks["packaging"]
        c_queen = checks["anti_queen_2p"]
        c_suit = checks["suit_choice"]
        c_legal = checks["legality_adherence"]

        def fmt_chk(name: str, check: dict[str, Any]) -> str:
            status = (
                f"{Colors.GREEN}✓ PASSED{Colors.RESET}"
                if check.get("passed")
                else f"{Colors.RED}✗ FAILED{Colors.RESET}"
            )
            msg = check.get("message", "")
            return f"  {status} {Colors.BOLD}{name:<32}{Colors.RESET} : {msg}"

        print(fmt_chk("T1.1 Official Smoke Test", c_smoke))
        print(fmt_chk("T1.2 AST & Packaging Valid", c_pack))
        print(fmt_chk("T1.3 Anti-Queen 2P Invariant", c_queen))
        print(fmt_chk("T1.4 Suit Selection Invariant", c_suit))
        print(fmt_chk("T1.5 Legal Action Adherence", c_legal))

        total = tier1_data["total_checks"]
        passed = tier1_data["passed_checks"]
        pct = (passed / total) * 100.0
        c_color = Colors.GREEN if passed == total else Colors.RED
        print(
            f"  {Colors.BOLD}Tier 1 Result:{Colors.RESET} {c_color}{passed}/{total} Checks Passed ({pct:.1f}%){Colors.RESET}"
        )

    @staticmethod
    def print_tier2_results(
        random_res: dict[str, Any], basic_res: dict[str, Any]
    ) -> None:
        print(
            f"\n{Colors.BOLD}[TIER 2: BASELINE OPPONENTS (Target >= 98% WR, 0 Forfeits)]{Colors.RESET}"
        )

        def fmt_res(r: dict[str, Any]) -> str:
            target_wr = 98.0
            passed = r["win_rate_pct"] >= target_wr and r["forfeits"] == 0
            status = (
                f"{Colors.GREEN}✓ PASSED{Colors.RESET}"
                if passed
                else f"{Colors.RED}✗ FAILED{Colors.RESET}"
            )
            wr_str = f"{r['win_rate_pct']:.1f}% WR"
            score_str = f"{r['wins']}-{r['losses']}"
            if r["draws"]:
                score_str += f"-{r['draws']}"
            return (
                f"  {status} vs {Colors.CYAN}{r['opponent_spec']:<15}{Colors.RESET} "
                f"({r['games']:>2} games) : {score_str:>7} ({wr_str:>8}) | "
                f"Forfeits: {r['forfeits']}  [{r['opponent_name']}]"
            )

        print(fmt_res(random_res))
        print(fmt_res(basic_res))

        total_games = random_res["games"] + basic_res["games"]
        total_wins = random_res["wins"] + basic_res["wins"]
        total_wr = (total_wins / total_games) * 100.0 if total_games else 0.0
        c_color = (
            Colors.GREEN
            if (
                random_res["win_rate_pct"] >= 98.0
                and basic_res["win_rate_pct"] >= 98.0
                and random_res["forfeits"] == 0
                and basic_res["forfeits"] == 0
            )
            else Colors.RED
        )
        print(
            f"  {Colors.BOLD}Tier 2 Result:{Colors.RESET} {c_color}{total_wins}/{total_games} Games Won ({total_wr:.1f}% Aggregate WR){Colors.RESET}"
        )

    @staticmethod
    def print_tier3_results(
        medium_res: dict[str, Any], latency_stats: dict[str, Any]
    ) -> None:
        print(
            f"\n{Colors.BOLD}[TIER 3: COMPETITIVE TACTICAL MATCH (Target >= 70% WR vs Medium, 0 Forfeits)]{Colors.RESET}"
        )
        passed = medium_res["win_rate_pct"] >= 70.0 and medium_res["forfeits"] == 0
        status = (
            f"{Colors.GREEN}✓ PASSED{Colors.RESET}"
            if passed
            else f"{Colors.RED}✗ FAILED{Colors.RESET}"
        )
        score_str = f"{medium_res['wins']}-{medium_res['losses']}"
        if medium_res["draws"]:
            score_str += f"-{medium_res['draws']}"

        print(
            f"  {status} vs {Colors.CYAN}{medium_res['opponent_spec']:<15}{Colors.RESET} "
            f"({medium_res['games']:>2} games) : {score_str:>7} ({medium_res['win_rate_pct']:.1f}% WR) | "
            f"Forfeits: {medium_res['forfeits']}  [{medium_res['opponent_name']}]"
        )
        if "p0_wins" in medium_res and "p1_wins" in medium_res:
            p0_g = medium_res.get("p0_games", medium_res["games"] // 2)
            p1_g = medium_res.get("p1_games", medium_res["games"] - p0_g)
            p0_wr = (medium_res["p0_wins"] / p0_g * 100.0) if p0_g else 0.0
            p1_wr = (medium_res["p1_wins"] / p1_g * 100.0) if p1_g else 0.0
            print(
                f"    Symmetric split: P0 (Challenger): {medium_res['p0_wins']}/{p0_g} ({p0_wr:.1f}%) │ "
                f"P1 (Opponent): {medium_res['p1_wins']}/{p1_g} ({p1_wr:.1f}%)"
            )

        print(
            f"\n  {Colors.BOLD}Move Latency Distribution ({latency_stats['count']:,} decisions profile):{Colors.RESET}"
        )
        print(
            f"    Min: {Colors.CYAN}{latency_stats['min']:.2f}ms{Colors.RESET}  │  "
            f"Mean: {Colors.CYAN}{latency_stats['mean']:.2f}ms{Colors.RESET}  │  "
            f"Median (p50): {Colors.CYAN}{latency_stats['median']:.2f}ms{Colors.RESET}"
        )
        print(
            f"    p90: {Colors.CYAN}{latency_stats['p90']:.2f}ms{Colors.RESET}  │  "
            f"p95: {Colors.CYAN}{latency_stats['p95']:.2f}ms{Colors.RESET}   │  "
            f"p99: {Colors.CYAN}{latency_stats['p99']:.2f}ms{Colors.RESET}  │  "
            f"Max: {Colors.CYAN}{latency_stats['max']:.2f}ms{Colors.RESET}"
        )
        lat_color = (
            Colors.GREEN
            if latency_stats["budget_compliance_pct"] >= 99.0
            else Colors.YELLOW
        )
        print(
            f"    Budget Compliance: {lat_color}{latency_stats['budget_compliance_pct']:.1f}% decisions < 300ms{Colors.RESET} | "
            f"Server Timeouts (>400ms): {latency_stats['timeouts_gt_400ms']} | "
            f"Timeouts (>1000ms): {latency_stats['timeouts_gt_1000ms']}"
        )

    @staticmethod
    def print_tier4_results(seed_results: list[dict[str, Any]]) -> None:
        print(
            f"\n{Colors.BOLD}[TIER 4: LEADERBOARD REFERENCE SEEDS (Target >= 75% Win Rate, 0 Forfeits)]{Colors.RESET}"
        )
        wins = 0
        forfeits = 0
        for s in seed_results:
            is_win = s.get("won", False)
            is_forfeit = s.get("forfeit", False) or (s.get("forfeited_player_id") == "p0")
            if is_win:
                wins += 1
            if is_forfeit:
                forfeits += 1
            status = (
                f"{Colors.GREEN}✓ PASSED{Colors.RESET}"
                if is_win and not is_forfeit
                else f"{Colors.RED}✗ FAILED{Colors.RESET}"
            )
            p0_s = s["scores"].get("p0", 0)
            p1_s = s["scores"].get("p1", 0)
            score_fmt = f"{p0_s}/{p1_s}"
            print(
                f"  {status} Seed {Colors.CYAN}{s['seed']:<10}{Colors.RESET} vs {s['opponent']} : "
                f"Winner = {s['winner']:<8} (Score: {score_fmt:>7}, Rounds: {s['rounds']:>2}, Steps: {s['steps']:>4})"
            )

        total = len(seed_results)
        pct = (wins / total) * 100.0 if total else 0.0
        passed = pct >= 75.0 and forfeits == 0
        c_color = Colors.GREEN if passed else Colors.RED
        print(
            f"  {Colors.BOLD}Tier 4 Result:{Colors.RESET} {c_color}{wins}/{total} Benchmark Seeds Won ({pct:.1f}%), {forfeits} Forfeits{Colors.RESET}"
        )

    @staticmethod
    def print_verdict(
        all_passed: bool = True,
        latency_stats: dict[str, Any] | None = None,
        latency_passed: bool = True,
        total_forfeits: int = 0,
        total_timeouts: int = 0,
        overall_passed: bool | None = None,
    ) -> None:
        if overall_passed is not None:
            all_passed = overall_passed
        if latency_stats is None:
            latency_stats = {}
        print(
            f"\n{Colors.DIM}════════════════════════════════════════════════════════════════════════════════{Colors.RESET}"
        )
        if latency_stats.get("count", 0) > 0:
            lat_status = (
                f"{Colors.GREEN}✓ PASSED{Colors.RESET}"
                if latency_passed
                else f"{Colors.RED}✗ FAILED{Colors.RESET}"
            )
            mean_v = latency_stats.get("mean", 0.0)
            max_v = latency_stats.get("max", 0.0)
            mean_col = Colors.GREEN if mean_v < 50.0 else Colors.RED
            max_col = Colors.GREEN if max_v < 300.0 else Colors.RED
            tout_col = Colors.GREEN if total_timeouts == 0 else Colors.RED
            forfeit_col = Colors.GREEN if total_forfeits == 0 else Colors.RED
            print(
                f"  {Colors.BOLD}Hard Latency Gating:{Colors.RESET} {lat_status} "
                f"(Mean: {mean_col}{mean_v:.2f}ms{Colors.RESET} < 50.0ms │ "
                f"Max: {max_col}{max_v:.2f}ms{Colors.RESET} < 300.0ms │ "
                f"Timeouts: {tout_col}{total_timeouts}{Colors.RESET} │ "
                f"Forfeits: {forfeit_col}{total_forfeits}{Colors.RESET})"
            )
        if all_passed:
            print(
                f"{Colors.BOLD}{Colors.GREEN} OVERALL VERDICT: GRAND_MASTER_READY ★★★★★ "
                f"(ALL ACCEPTANCE CRITERIA SATISFIED){Colors.RESET}"
            )
        else:
            print(
                f"{Colors.BOLD}{Colors.RED} OVERALL VERDICT: BENCHMARK_FAILED ⚠️ "
                f"(ONE OR MORE ACCEPTANCE CRITERIA WERE NOT MET){Colors.RESET}"
            )
        print(
            f"{Colors.DIM}════════════════════════════════════════════════════════════════════════════════{Colors.RESET}\n"
        )


# Main Benchmark Execution Coordinator
def run_benchmark(
    bot_path_str: str = "bot.py",
    tier_choice: str = "all",
    games: int = 50,
    profile_latency: bool = True,
    json_out_path: str | None = None,
    target_score: int = 151,
    base_seed: int = 42,
    verbose: bool = False,
) -> int:
    Colors.disable_if_no_color()
    bot_path = resolve_submission_path(bot_path_str)
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

    ReportFormatter.print_header(bot_path, tier_choice, timestamp)

    runner = BenchmarkRunner(
        bot_path,
        profile_latency=profile_latency,
        target_score=target_score,
        verbose=verbose,
    )
    t1_verifier = Tier1Verifier(bot_path, runner.challenger_dir)

    results_data: dict[str, Any] = {
        "timestamp": timestamp,
        "bot_path": str(bot_path.resolve()),
        "tier_choice": tier_choice,
        "games_per_series": games,
        "target_score": target_score,
    }

    tier_choice = tier_choice.lower()
    run_t1 = tier_choice in ("all", "1", "smoke")
    run_t2 = tier_choice in ("all", "2", "baselines")
    run_t3 = tier_choice in ("all", "3", "medium", "tactical")
    run_t4 = tier_choice in ("all", "4", "seeds")

    t1_passed = True
    t2_passed = True
    t3_passed = True
    t4_passed = True

    # Execution TIER 1
    if run_t1:
        t1_results = t1_verifier.run_all()
        t1_passed = t1_results["passed"]
        results_data["tier1_sanity"] = t1_results
        ReportFormatter.print_tier1_results(t1_results)

    # Execution TIER 2
    if run_t2:
        print(
            f"\n{Colors.DIM}Running Tier 2 Baselines ({games} games vs Random, {games} games vs Basic)...{Colors.RESET}"
        )
        t2_random = runner.run_series(
            "builtin:random", games=games, base_seed=base_seed
        )
        t2_basic = runner.run_series("basic", games=games, base_seed=base_seed)
        t2_passed = (
            t2_random["win_rate_pct"] >= 98.0
            and t2_random["forfeits"] == 0
            and t2_basic["win_rate_pct"] >= 98.0
            and t2_basic["forfeits"] == 0
        )
        results_data["tier2_baselines"] = {
            "random": t2_random,
            "basic": t2_basic,
            "passed": t2_passed,
        }
        ReportFormatter.print_tier2_results(t2_random, t2_basic)

    # Execution TIER 3
    if run_t3:
        print(
            f"\n{Colors.DIM}Running Tier 3 Tactical Match ({games} games vs Medium)...{Colors.RESET}"
        )
        t3_medium = runner.run_series("medium", games=games, base_seed=base_seed)
        t3_passed = t3_medium["win_rate_pct"] >= 70.0 and t3_medium["forfeits"] == 0
        lat_stats = runner.latency_profile.compute_stats()
        results_data["tier3_tactical"] = {
            "medium": t3_medium,
            "passed": t3_passed,
        }
        results_data["latency_profile_ms"] = lat_stats
        ReportFormatter.print_tier3_results(t3_medium, lat_stats)

    # Execution TIER 4
    if run_t4:
        print(
            f"\n{Colors.DIM}Running Tier 4 Leaderboard Reference Seeds vs Medium...{Colors.RESET}"
        )
        ref_seeds = [848914317, 1477911113, 2063595735, 329389206]
        seed_results: list[dict[str, Any]] = []
        for s in ref_seeds:
            s_res = runner.run_seed("medium", s)
            seed_results.append(s_res)
        t4_wins = sum(1 for sr in seed_results if sr.get("won", False))
        t4_forfeits = sum(
            1 for sr in seed_results if sr.get("forfeit", False) or (sr.get("forfeited_player_id") == "p0")
        )
        t4_win_rate_pct = (t4_wins / len(seed_results) * 100.0) if seed_results else 0.0
        t4_passed = t4_win_rate_pct >= 75.0 and t4_forfeits == 0
        results_data["tier4_seeds"] = {
            "seeds": seed_results,
            "wins": t4_wins,
            "total": len(seed_results),
            "win_rate_pct": round(t4_win_rate_pct, 2),
            "forfeits": t4_forfeits,
            "passed": t4_passed,
        }
        ReportFormatter.print_tier4_results(seed_results)

    # Global latency profiling & reliability audit across all executed matches
    final_lat_stats = runner.latency_profile.compute_stats()

    # Aggregate forfeit counting across all executed tiers
    total_forfeits = 0
    if run_t1:
        smoke_chk = t1_results.get("checks", {}).get("smoke_test", {})
        if not smoke_chk.get("passed", False):
            total_forfeits += 1
    if run_t2:
        total_forfeits += t2_random.get("forfeits", 0) + t2_basic.get("forfeits", 0)
    if run_t3:
        total_forfeits += t3_medium.get("forfeits", 0)
    if run_t4:
        total_forfeits += t4_forfeits

    # Timeout auditing: isolate opponent timeouts from challenger timeouts
    challenger_match_timeouts = 0
    opponent_match_timeouts = 0

    def _audit_matches_timeouts(matches_list: list[dict[str, Any]]) -> None:
        nonlocal challenger_match_timeouts, opponent_match_timeouts
        for m in matches_list:
            if m.get("reason") == "timeout":
                my_slot = m.get("my_slot", "p0")
                forfeited = m.get("forfeited_player_id")
                winner = m.get("winner_id")
                if forfeited == my_slot or (winner != my_slot and forfeited is None):
                    challenger_match_timeouts += 1
                else:
                    opponent_match_timeouts += 1

    if run_t2:
        _audit_matches_timeouts(t2_random.get("matches", []))
        _audit_matches_timeouts(t2_basic.get("matches", []))
    if run_t3:
        _audit_matches_timeouts(t3_medium.get("matches", []))
    if run_t4:
        _audit_matches_timeouts(seed_results)

    match_timeouts = challenger_match_timeouts
    decision_timeouts_400 = final_lat_stats.get("timeouts_gt_400ms", 0)
    decision_timeouts_1000 = final_lat_stats.get("timeouts_gt_1000ms", 0)
    decision_timeouts = decision_timeouts_400
    slow_moves_300 = final_lat_stats.get("slow_moves_gt_300ms", 0)
    total_timeouts = match_timeouts + decision_timeouts

    # Hard Latency Gating:
    # 1. Average latency strictly < 50.0 ms
    # 2. Max latency < 300.0 ms
    # 3. 0 timeouts and 0 slow moves > 300ms
    if profile_latency and (run_t2 or run_t3 or run_t4):
        latency_passed = (
            final_lat_stats["count"] > 0
            and final_lat_stats["mean"] < 50.0
            and final_lat_stats["max"] < 300.0
            and decision_timeouts_400 == 0
            and slow_moves_300 == 0
        )
    else:
        latency_passed = True

    # Final overall status: all enabled tiers must pass + hard latency gating + zero forfeits/timeouts
    overall_passed = (
        (not run_t1 or t1_passed)
        and (not run_t2 or t2_passed)
        and (not run_t3 or t3_passed)
        and (not run_t4 or t4_passed)
        and latency_passed
        and (total_forfeits == 0)
        and (total_timeouts == 0)
    )

    results_data["latency_gating"] = {
        "profiled": profile_latency,
        "decisions_count": final_lat_stats.get("count", 0),
        "mean_latency_ms": final_lat_stats.get("mean", 0.0),
        "mean_threshold_ms": 50.0,
        "mean_passed": (final_lat_stats.get("mean", 0.0) < 50.0) if final_lat_stats.get("count", 0) > 0 else True,
        "max_latency_ms": final_lat_stats.get("max", 0.0),
        "max_threshold_ms": 300.0,
        "max_passed": (final_lat_stats.get("max", 0.0) < 300.0) if final_lat_stats.get("count", 0) > 0 else True,
        "slow_moves_gt_300ms": slow_moves_300,
        "decision_timeouts_gt_400ms": decision_timeouts_400,
        "decision_timeouts_gt_1000ms": decision_timeouts_1000,
        "challenger_match_timeouts": challenger_match_timeouts,
        "opponent_match_timeouts": opponent_match_timeouts,
        "match_timeouts": match_timeouts,
        "total_timeouts": total_timeouts,
        "total_forfeits": total_forfeits,
        "passed": latency_passed,
    }

    results_data["summary"] = {
        "tier1_passed": t1_passed if run_t1 else None,
        "tier2_passed": t2_passed if run_t2 else None,
        "tier3_passed": t3_passed if run_t3 else None,
        "tier4_passed": t4_passed if run_t4 else None,
        "latency_passed": latency_passed,
        "total_forfeits": total_forfeits,
        "total_timeouts": total_timeouts,
        "overall_passed": overall_passed,
        "verdict": "GRAND_MASTER_READY" if overall_passed else "BENCHMARK_FAILED",
    }
    if "latency_profile_ms" not in results_data:
        results_data["latency_profile_ms"] = final_lat_stats

    ReportFormatter.print_verdict(
        overall_passed=overall_passed,
        latency_stats=final_lat_stats,
        latency_passed=latency_passed,
        total_forfeits=total_forfeits,
        total_timeouts=total_timeouts,
    )

    if json_out_path:
        out_p = Path(json_out_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        with open(out_p, "w", encoding="utf-8") as f:
            json.dump(results_data, f, indent=2, ensure_ascii=False)
        print(f"{Colors.GREEN}✓ Structured report saved to:{Colors.RESET} {out_p}\n")

    return 0 if overall_passed else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="benchmark_suite.py",
        description="i151 Grand Master Bot Automated Tournament Benchmark & Verification Suite",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--bot",
        default="bot.py",
        help="Chemin vers le point d'entrée du bot (bot.py ou soumission ZIP)",
    )
    parser.add_argument(
        "--tier",
        choices=[
            "all",
            "1",
            "2",
            "3",
            "4",
            "smoke",
            "seeds",
            "baselines",
            "medium",
            "tactical",
        ],
        default="all",
        help="Tier de benchmark à exécuter : 1/smoke, 2/baselines, 3/medium, 4/seeds, all",
    )
    parser.add_argument(
        "--games",
        type=int,
        default=50,
        help="Nombre de parties pour chaque confrontation statistique (Tiers 2 et 3)",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Raccourci pour exécuter une vérification rapide (5 parties par série)",
    )
    parser.add_argument(
        "--profile-latency",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Activer le profilage statistique de latence par décision",
    )
    parser.add_argument(
        "--json-out",
        type=str,
        default=None,
        metavar="PATH",
        help="Chemin pour exporter le rapport structuré au format JSON",
    )
    parser.add_argument(
        "--target-score",
        type=int,
        default=151,
        help="Score cible de fin de partie",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Seed de départ pour les séries statistiques",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Affichage détaillé partie par partie",
    )

    args = parser.parse_args(argv)
    games = 5 if args.quick else max(1, args.games)

    return run_benchmark(
        bot_path_str=args.bot,
        tier_choice=args.tier,
        games=games,
        profile_latency=args.profile_latency,
        json_out_path=args.json_out,
        target_score=args.target_score,
        base_seed=args.seed,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    sys.exit(main())
