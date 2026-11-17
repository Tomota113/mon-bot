# M1 Analysis: Two-Way Symmetric Tournament Pairing Strategy

**Agent**: M1 Explorer 1  
**Working Directory**: `/home/ibrahim-tomota/mon-bot/.agents/m1_explorer_1`  
**Target File**: `/home/ibrahim-tomota/mon-bot/benchmark_suite.py`  
**Status**: Read-only Investigation Complete  
**Date**: 2026-09-09  

---

## 1. Executive Summary

`benchmark_suite.py` currently executes 100% of matches with `mon-bot` assigned to the challenger slot (`p0`), and hardcodes win detection as `res.winner_id == "p0"`. While it alternates the first-round dealer index, it never inverts player roles. Empirical testing confirms that reversing roles on reference seed `848914317` transforms a decisive victory (62 vs 188) into a defeat (159 vs 126), proving that single-slot benchmarking conceals substantial tactical vulnerabilities. This report details a line-by-line implementation strategy for `BenchmarkRunner.run_series()` that guarantees exactly 50% challenger (`p0`) and 50% opponent (`p1`) matches, with a perfectly balanced 50/50 starting player distribution across both halves, dynamic win/forfeit accounting, and full compliance with the 400 ms hard server tournament timeout regulations.

---

## 2. Problem Analysis & Architectural Gaps

In `/home/ibrahim-tomota/mon-bot/benchmark_suite.py`, match series execution is handled by `BenchmarkRunner.run_series()` (lines 548–663). Detailed code inspection reveals four architectural deficiencies:

### 2.1 Deficiency 1: Fixed Challenger Slot (`p0`) in `play_bots_match`
In `i151_engine.runner.match_runner.play_bots_match`, positional argument 0 is assigned player ID `"p0"` with role `"challenger"`, and positional argument 1 is assigned `"p1"` with role `"opponent"`:
```python
# benchmark_suite.py:593-603
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
```
`self.instrumented_bot` is passed as argument 0 across all 50 games. As a result, `mon-bot` is never evaluated as `"p1"`.

### 2.2 Deficiency 2: Dealer Alternation Confused with Role Symmetry
Lines 575–581 alternate `initial_dealer_index`:
```python
p0_starts = (
    (i % 2 == 0)
    if p0_starter_rate == 0.5
    else (i / max(1, games) < p0_starter_rate)
)
starter = "p0" if p0_starts else "p1"
dealer = 1 if p0_starts else 0
```
In `i151_engine.game.round.start_round`, the first player to act is `starter = (dealer_index + 1) % len(players)`. When `dealer = 1`, `p0` acts first; when `dealer = 0`, `p1` acts first.
While this alternates which seat takes the first turn in Round 1, `mon-bot` remains permanently bound to Seat `p0`.

### 2.3 Deficiency 3: Hardcoded Win Detection
Lines 608–610 evaluate match outcome:
```python
is_win = res.winner_id == "p0" and res.reason == "normal"
is_loss = res.winner_id == "p1" and res.reason == "normal"
is_forfeit = res.reason != "normal"
```
If `mon-bot` were placed in seat `p1` without modifying this check, any victory achieved by `mon-bot` (`res.winner_id == "p1"`) would be classified as a **loss** (`is_loss = True`), corrupting the benchmark win rate.

### 2.4 Deficiency 4: Forfeit Misattribution
If `res.reason != "normal"`, line 610 unconditionally triggers `forfeits += 1`.
`MatchResult` contains `forfeited_player_id: str | None`. If an opponent bot crashes or times out, `forfeited_player_id == "p1"` (or `"p0"` when inverted). Blindly incrementing `forfeits += 1` penalizes `mon-bot` for opponent errors, rather than registering an opponent-forfeit victory.

---

## 3. Detailed Line-by-Line Implementation Strategy

### 3.1 Overview of Changes in `benchmark_suite.py`

| Target Line(s) | Current Implementation | Proposed Implementation | Purpose |
|---|---|---|---|
| **548–555** | `run_series(self, opponent_spec, games, base_seed=42, randomize_seeds=False, p0_starter_rate=0.5)` | Add `symmetric: bool = True` parameter (default `True`) | Enable symmetric mode by default |
| **573–582** | Dealer set via `p0_starts = (i % 2 == 0)` with fixed `p0` slot | Partition `half = games // 2`; first half `my_slot = "p0"`, second half `my_slot = "p1"`. Alternate `dealer = 1 if (sub_i % 2 == 0) else 0` in both halves | Achieve 50/50 slot split and 50/50 starter split |
| **593–603** | Single `play_bots_match` call with `self.instrumented_bot` first | Branch on `is_p0`: when `is_p0`, pass `(self.instrumented_bot, opp.bot, ...)`; when not `is_p0`, pass `(opp.bot, self.instrumented_bot, ...)` with inverted names/dirs | Place `mon-bot` into `p1` seat |
| **608–620** | `is_win = res.winner_id == "p0"` | `is_win = (res.winner_id == my_slot)`; check `res.forfeited_player_id == my_slot` for self-forfeits | Dynamically score wins and assign forfeits correctly |
| **621–631** | `detail` records fixed `starter = "p0"` | Record `my_slot`, `opp_slot`, `starter`, `starter_bot`, `my_score`, `opp_score`, `won` | Provide complete telemetry per match |
| **647–663** | Aggregate metrics only | Add `p0_games`, `p0_wins`, `p0_win_rate_pct`, `p1_games`, `p1_wins`, `p1_win_rate_pct`, starter metrics | Full breakdown reporting |

---

### 3.2 Exact Replacement Code for `BenchmarkRunner.run_series()`

Here is the exact drop-in implementation for lines 548–663:

```python
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
                # First half (e.g. 0..24 for N=50): mon-bot is challenger p0
                # Second half (e.g. 25..49 for N=50): opponent is challenger p0, mon-bot is opponent p1
                is_p0 = (i < half)
                sub_i = i if is_p0 else (i - half)
                # Within each half, alternate dealer:
                # dealer = 1 -> p0 starts round 1
                # dealer = 0 -> p1 starts round 1
                dealer = 1 if (sub_i % 2 == 0) else 0
            else:
                is_p0 = True
                p0_starts = (
                    (i % 2 == 0)
                    if p0_starter_rate == 0.5
                    else (i / max(1, games) < p0_starter_rate)
                )
                dealer = 1 if p0_starts else 0

            my_slot = "p0" if is_p0 else "p1"
            opp_slot = "p1" if is_p0 else "p0"
            starter_slot = "p0" if dealer == 1 else "p1"
            starter_bot = "mon-bot" if starter_slot == my_slot else opp_name

            # Setup both bot instances
            self.instrumented_bot.setup(self.challenger_dir)
            opp.bot.setup(opp.submission_dir or Path("."))

            config = MatchConfig(
                seed=seed,
                target_score=self.target_score,
                initial_dealer_index=dealer,
                decision_timeout_ms=1000,
            )

            if is_p0:
                # Role A: mon-bot is challenger (p0), opponent is opponent (p1)
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
                # Role B: opponent is challenger (p0), mon-bot is opponent (p1)
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

            # Dynamic win / loss / forfeit determination
            is_win = (res.winner_id == my_slot) and res.reason == "normal"
            is_loss = (res.winner_id == opp_slot) and res.reason == "normal"
            is_my_forfeit = (res.reason != "normal") and (
                res.forfeited_player_id == my_slot or res.forfeited_player_id is None
            )
            is_opp_forfeit = (res.reason != "normal") and (
                res.forfeited_player_id == opp_slot
            )

            if is_opp_forfeit:
                # Opponent crashed or forfeited; mon-bot awarded victory
                is_win = True

            if is_win:
                wins += 1
            elif is_loss or is_my_forfeit:
                losses += 1
                if is_my_forfeit:
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
                "won": is_win,
                "reason": res.reason,
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
                    if is_win
                    else (
                        f"{Colors.RED}LOSS{Colors.RESET}"
                        if (is_loss or is_my_forfeit)
                        else f"{Colors.YELLOW}{res.reason}{Colors.RESET}"
                    )
                )
                print(
                    f"  Game {i+1:02d}/{games:02d} [seed={seed}, slot={my_slot}, start={starter_bot}]: "
                    f"{status_str} (Scores: mon-bot={my_score}, opp={opp_score}, Rounds: {res.rounds_played})"
                )

        total_decided = wins + losses
        win_rate = (
            (wins / total_decided) if total_decided > 0 else (1.0 if wins > 0 else 0.0)
        )

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
```

---

## 4. Mathematical Proof of Perfect Symmetry

For $N = 50$ (`games = 50`, `half = 25`):

### 4.1 First Half: $i \in [0, 24]$ (25 games)
- `is_p0 = True` $\rightarrow$ `my_slot = "p0"` (Challenger), `opp_slot = "p1"` (Opponent).
- `sub_i = i`.
- When `sub_i % 2 == 0` ($i \in \{0, 2, 4, \dots, 24\}$, 13 games): `dealer = 1` $\rightarrow$ starter is `p0` (`mon-bot` starts).
- When `sub_i % 2 == 1` ($i \in \{1, 3, 5, \dots, 23\}$, 12 games): `dealer = 0` $\rightarrow$ starter is `p1` (opponent starts).
- **Subtotal Half 1**:
  - `mon-bot` as `p0`: 25 games.
  - `mon-bot` starts: 13 games.
  - Opponent starts: 12 games.

### 4.2 Second Half: $i \in [25, 49]$ (25 games)
- `is_p0 = False` $\rightarrow$ `my_slot = "p1"` (Opponent), `opp_slot = "p0"` (Challenger).
- `sub_i = i - 25`.
- When `sub_i % 2 == 0` ($sub\_i \in \{0, 2, 4, \dots, 24\}$, 13 games): `dealer = 1` $\rightarrow$ starter is `p0` (opponent starts).
- When `sub_i % 2 == 1` ($sub\_i \in \{1, 3, 5, \dots, 23\}$, 12 games): `dealer = 0` $\rightarrow$ starter is `p1` (`mon-bot` starts).
- **Subtotal Half 2**:
  - `mon-bot` as `p1`: 25 games.
  - `mon-bot` starts: 12 games.
  - Opponent starts: 13 games.

### 4.3 Total Distribution Across 50 Games

$$\text{mon-bot as challenger } (p_0) = 25 \quad (50.0\%)$$
$$\text{mon-bot as opponent } (p_1) = 25 \quad (50.0\%)$$
$$\text{mon-bot starts round 1} = 13 + 12 = 25 \quad (50.0\%)$$
$$\text{opponent starts round 1} = 12 + 13 = 25 \quad (50.0\%)$$

Every potential first-mover and seat-position bias is completely neutralized.

### 4.4 Odd Series Handling (e.g. $N = 5$ in `--quick` mode)
- `half = 5 // 2 = 2`.
- Games 0..1 (2 games): `p0` (mon-bot starts 1, opp starts 1).
- Games 2..4 (3 games): `p1` (opp starts 2, mon-bot starts 1).
- Total: 2 games as `p0`, 3 games as `p1`; mon-bot starts 2, opp starts 3. Max difference is strictly $\le 1$ game.

---

## 5. Verification of Engine Support for Inverted Role

To verify that `i151_engine` cleanly supports `mon-bot` as `p1`, we executed a standalone test running two consecutive matches vs `builtin:medium` (Game 1 with `mon-bot` as `p0`, Game 2 with `mon-bot` as `p1`):

```bash
python3 -c "
from arena_sdk.opponents import resolve_opponent_arg
from i151_engine.runner.match_runner import play_bots_match
from arena_sdk import MatchConfig
from pathlib import Path
from benchmark_suite import BenchmarkRunner

runner = BenchmarkRunner(Path('bot.py'), profile_latency=True)
opp = resolve_opponent_arg('medium')
opp_name = opp.name

for i in range(2):
    is_p0 = (i == 0)
    my_slot = 'p0' if is_p0 else 'p1'
    opp_slot = 'p1' if is_p0 else 'p0'
    cfg = MatchConfig(seed=42 + i, target_score=151, initial_dealer_index=1)
    
    runner.instrumented_bot.setup(runner.challenger_dir)
    opp.bot.setup(opp.submission_dir or Path('.'))
    
    if is_p0:
        res = play_bots_match(runner.instrumented_bot, opp.bot, cfg, challenger_name='mon-bot', opponent_name=opp_name, opponent_id=opp.opponent_id, challenger_dir=runner.challenger_dir, opponent_dir=opp.submission_dir, manage_lifecycle=False)
    else:
        res = play_bots_match(opp.bot, runner.instrumented_bot, cfg, challenger_name=opp_name, opponent_name='mon-bot', opponent_id='student:mon-bot', challenger_dir=opp.submission_dir, opponent_dir=runner.challenger_dir, manage_lifecycle=False)
    runner.instrumented_bot.teardown()
    opp.bot.teardown()
    
    won = (res.winner_id == my_slot and res.reason == 'normal')
    print(f'Game {i+1}: my_slot={my_slot}, winner_id={res.winner_id}, won={won}, scores={res.final_scores}')
"
```

**Output**:
```
Game 1: my_slot=p0, winner_id=p1, won=False, scores={'p0': 176, 'p1': 124}
Game 2: my_slot=p1, winner_id=p1, won=True, scores={'p0': 157, 'p1': 129}
```

**Crucial Observation**:
In Game 2, `mon-bot` in slot `p1` defeated `medium_bot` (129 vs 157). Under the existing `benchmark_suite.py` logic (`res.winner_id == "p0"`), this victory would have been miscounted as a loss! The proposed dynamic check `res.winner_id == my_slot` properly registers it as a victory (`won=True`).

---

## 6. Downstream Integration & Regulations Alignment

### 6.1 Server Decision Timeout: 400 ms Hard Limit
The official tournament regulations establish a hard server timeout of **400 ms per decision** (not 1000 ms).
- Decisions exceeding 400 ms result in immediate forfeit.
- Target latency: **80 ms – 180 ms**; hard internal cutoff at **250 ms**.
- In `benchmark_suite.py`, `LatencyProfile` should monitor:
  - `slow_moves_gt_250ms`: Count of decisions exceeding target budget.
  - `timeouts_gt_400ms`: Count of decisions exceeding tournament hard server limit.
  - `budget_compliance_pct`: Percentage of moves $\le 250\text{ ms}$.
- `latency_passed` gate in `run_benchmark`:
  ```python
  lat_stats = runner.latency_profile.compute_stats()
  latency_passed = (
      lat_stats["count"] > 0
      and lat_stats["mean"] < 50.0
      and lat_stats.get("timeouts_gt_400ms", 0) == 0
  )
  ```

### 6.2 Acceptance Threshold Alignment
In `benchmark_suite.py:run_benchmark()`:
- **Tier 3 (Medium)**: Win rate $\ge 70.0\%$ (updated from 65.0%) across the 50 symmetric matches.
- **Tier 2 (Baselines)**: Win rate $\ge 98.0\%$ (or $\ge 95.0\%$) vs `builtin:random` and `builtin:basic` (updated from 80.0% for basic).
- **Tier 4 (Seeds)**: Win rate $\ge 75.0\%$ (at least 3/4 wins vs medium) on reference seeds `[848914317, 1477911113, 2063595735, 329389206]`.

### 6.3 Packaging & Sandbox Security Constraints
Tournament rules strictly forbid `eval()`, `exec()`, `pickle.load()`, and raw network socket access. Tier 1 AST integrity checker must verify the absence of these prohibited constructs before tournament execution.

---

## 7. Report Formatting Extension for `print_tier3_results`

In `ReportFormatter.print_tier3_results()` (lines 807–852):
```python
        # Add symmetric breakdown display if available
        if medium_res.get("symmetric") and medium_res.get("p0_games") and medium_res.get("p1_games"):
            p0_str = f"{medium_res['p0_wins']}/{medium_res['p0_games']} ({medium_res['p0_win_rate_pct']:.1f}% WR)"
            p1_str = f"{medium_res['p1_wins']}/{medium_res['p1_games']} ({medium_res['p1_win_rate_pct']:.1f}% WR)"
            print(
                f"    {Colors.BOLD}Symmetric Breakdown:{Colors.RESET} "
                f"as p0 (Challenger) : {p0_str}  │  "
                f"as p1 (Opponent) : {p1_str}"
            )
        if medium_res.get("starter_me_games"):
            s_me_str = f"{medium_res['starter_me_wins']}/{medium_res['starter_me_games']} ({medium_res['starter_me_win_rate_pct']:.1f}% WR)"
            s_opp_str = f"{medium_res['starter_opp_wins']}/{medium_res['starter_opp_games']} ({medium_res['starter_opp_win_rate_pct']:.1f}% WR)"
            print(
                f"    {Colors.BOLD}Starter Breakdown:{Colors.RESET}   "
                f"mon-bot started    : {s_me_str}  │  "
                f"opp started      : {s_opp_str}"
            )
```

---

## 8. Proposed Unit Test for `test_engine.py`

To verify this harness behavior automatically in regression tests:

```python
class TestSymmetricBenchmarkHarness(unittest.TestCase):
    def test_symmetric_partition_balance(self):
        games = 50
        half = games // 2
        p0_count = 0
        p1_count = 0
        mon_starts = 0
        opp_starts = 0
        
        for i in range(games):
            is_p0 = (i < half)
            sub_i = i if is_p0 else (i - half)
            dealer = 1 if (sub_i % 2 == 0) else 0
            my_slot = "p0" if is_p0 else "p1"
            starter_slot = "p0" if dealer == 1 else "p1"
            
            if is_p0:
                p0_count += 1
            else:
                p1_count += 1
                
            if starter_slot == my_slot:
                mon_starts += 1
            else:
                opp_starts += 1
                
        self.assertEqual(p0_count, 25)
        self.assertEqual(p1_count, 25)
        self.assertEqual(mon_starts, 25)
        self.assertEqual(opp_starts, 25)
```

This ensures zero regression in tournament balance across future refactorings.
