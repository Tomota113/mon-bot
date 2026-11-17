# Survey Report: Benchmark Suite Capabilities & R4 Compliance Analysis

**Investigator**: Survey Explorer 3  
**Date**: 2026-09-09  
**Working Directory**: `/home/ibrahim-tomota/mon-bot/.agents/survey_explorer_r2_3`  
**Target File**: `/home/ibrahim-tomota/mon-bot/benchmark_suite.py`  
**Referenced Specifications**:
- `/home/ibrahim-tomota/mon-bot/.agents/ORIGINAL_REQUEST.md`
- `/home/ibrahim-tomota/mon-bot/.agents/TEST_INFRA.md`
- `/home/ibrahim-tomota/mon-bot/.agents/TEST_READY.md`
- `/home/ibrahim-tomota/mon-bot/.agents/skills/i151-master-bot/SKILL.md`

---

## Executive Summary

1. **Symmetric 50-match Tournament vs `builtin:medium`**:
   `benchmark_suite.py` does **NOT** implement the required symmetric 50-match tournament (25 games as challenger `p0`, 25 games as opponent `p1`). Although it alternates the initial dealer index (`dealer = 1` vs `dealer = 0`), `mon-bot` is hardcoded as `p0` (challenger role) in 100% of matches, and win detection hardcodes `res.winner_id == "p0"`. Zero games are played with `mon-bot` in the `p1` slot.

2. **Testing Against Reference Seeds (848914317, 1477911113, 2063595735, 329389206)**:
   Reference seeds are executed in Tier 4 as 4 single deterministic matches vs `builtin:medium`. In all 4 runs, `mon-bot` is hardcoded as `p0` with `initial_dealer_index = 1` (`p0` starts). It enforces a 100% win rate threshold (4/4 wins), whereas the updated Acceptance Criteria in `ORIGINAL_REQUEST.md` specifies $\ge 75\%$. Empirical testing confirms `mon-bot` currently wins all 4 seeds as `p0`, but testing revealed that if player roles are inverted on seed 848914317 (`medium` as `p0`, `mon-bot` as `p1`), `medium_bot` wins 126 vs 159, underscoring the critical necessity of symmetric evaluation.

3. **Testing Against `builtin:random` and `builtin:basic`**:
   Baseline testing runs in Tier 2 (50 games each by default). While alternating dealers is used, `mon-bot` is always `p0`. Furthermore, there is a critical threshold discrepancy: `benchmark_suite.py` only requires $\ge 80.0\%$ win rate against `builtin:basic` (and $\ge 95.0\%$ vs `builtin:random`), whereas `ORIGINAL_REQUEST.md` strictly demands $\ge 95\%$ (initial) and $\ge 98\%$ (follow-up) against **both** baselines.

4. **Harness Structure & Required Changes to Satisfy R4**:
   The current harness is well-modularized (`LatencyProfile`, `InstrumentedBot`, `Tier1Verifier`, `BenchmarkRunner`, `ReportFormatter`), but requires 5 key modifications:
   - Implement true two-way slot/role symmetry (25 matches as `p0`, 25 matches as `p1`) with alternating dealers in both configurations.
   - Update win/forfeit accounting to track `my_slot` (`"p0"` or `"p1"`).
   - Align win rate thresholds: Medium $\ge 70\%$, Baselines $\ge 95\text{--}98\%$, Seeds $\ge 75\text{--}100\%$.
   - Enforce hard latency gating in pass/fail criteria (`mean < 50ms`, `max < 300ms`, `timeouts == 0`).
   - Validate the real packaging artifact (`mon-bot-submission.zip` generated via `arena pack .`).

---

## 1. Investigation: Symmetric Tournament Against `builtin:medium`

### 1.1 Requirements Specification
From `ORIGINAL_REQUEST.md`:
- **Section R4**: *"Benchmark the bot on symmetric two-way matches against builtin:medium (50 games total: 25 as challenger p0, 25 as opponent p1) with alternating dealers to eliminate first-player bias."*
- **Acceptance Criteria**: *"Win rate >= 70% vs builtin:medium across 50 symmetric matches (alternating p0/p1)."*

### 1.2 Current Implementation Analysis in `benchmark_suite.py`
In `benchmark_suite.py`, match series execution is handled by `BenchmarkRunner.run_series()`:

```python
# benchmark_suite.py:573-611
for i, seed in enumerate(seeds):
    # Alternate or sample starter based on rate
    p0_starts = (
        (i % 2 == 0)
        if p0_starter_rate == 0.5
        else (i / max(1, games) < p0_starter_rate)
    )
    starter = "p0" if p0_starts else "p1"
    dealer = 1 if p0_starts else 0

    self.instrumented_bot.setup(self.challenger_dir)
    opp.bot.setup(opp.submission_dir or Path("."))

    config = MatchConfig(
        seed=seed,
        target_score=self.target_score,
        initial_dealer_index=dealer,
        decision_timeout_ms=1000,
    )

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
    ...
    is_win = res.winner_id == "p0" and res.reason == "normal"
    is_loss = res.winner_id == "p1" and res.reason == "normal"
```

### 1.3 Identification of Deficiencies
1. **Hardcoded Challenger Slot (`p0`)**:
   In `play_bots_match` (`i151_engine.runner.match_runner:play_bots_match`), the first positional argument is assigned `{"id": "p0", "name": challenger_name, "role": "challenger"}`, and the second is assigned `{"id": "p1", "name": opponent_name, "role": "opponent"}`. `self.instrumented_bot` is always passed as the first parameter. Consequently, `mon-bot` plays as `p0` in all 50 games.
2. **Dealer Alternation vs Role Symmetry Confusion**:
   The code alternates `dealer = 1` vs `dealer = 0` via `p0_starts = (i % 2 == 0)`. While this alternates who begins the first round of the match, it does **not** alter the bot's player slot (`p0` vs `p1`).
3. **Hardcoded Win Detection**:
   Lines 608-609 hardcode `is_win = res.winner_id == "p0"`. If the bot were placed in the `p1` slot, a victory would result in `res.winner_id == "p1"` and be incorrectly registered as a loss.
4. **Conclusion on Question 1**:
   The current `benchmark_suite.py` does **not** implement symmetric two-way tournament play (25 as `p0`, 25 as `p1`). It is asymmetric in player slot allocation.

---

## 2. Investigation: Leaderboard Reference Seeds Testing

### 2.1 Requirements Specification
- `ORIGINAL_REQUEST.md` (Initial §2): *"Wins benchmark seeds against top leaderboard bots (848914317, 1477911113, 2063595735, 329389206)."*
- `ORIGINAL_REQUEST.md` (Follow-up Acceptance Criteria): *"Win rate >= 75% across the top leaderboard reference seeds (848914317, 1477911113, 2063595735, 329389206)."*
- `TEST_INFRA.md` (§3): Tactical Ace warfare, survival endgame, Queen combos, 29-round endurance vs `builtin:medium`.

### 2.2 Current Implementation Analysis
In `benchmark_suite.py:992-1006` and `665-705`:
```python
# benchmark_suite.py:665-680
def run_seed(self, opponent_spec: str, seed: int) -> dict[str, Any]:
    """Runs a single deterministic seed match vs opponent (p0 starts)."""
    opp = resolve_opponent_arg(opponent_spec)
    self.instrumented_bot.setup(self.challenger_dir)
    opp.bot.setup(opp.submission_dir or Path("."))

    config = MatchConfig(
        seed=seed,
        target_score=self.target_score,
        initial_dealer_index=1,  # p0 starts
        decision_timeout_ms=1000,
    )
    ...
```
```python
# benchmark_suite.py:996-1001
ref_seeds = [848914317, 1477911113, 2063595735, 329389206]
seed_results: list[dict[str, Any]] = []
for s in ref_seeds:
    s_res = runner.run_seed("medium", s)
    seed_results.append(s_res)
t4_passed = all(sr["won"] for sr in seed_results)
```

### 2.3 Verification Results & Findings
1. **Execution Verification**:
   Running `python3 benchmark_suite.py --tier 4` against the current `bot.py` produced:
   - Seed `848914317`: `mon-bot` Won (Score: 62 vs 188, 20 rounds, 1024 steps)
   - Seed `1477911113`: `mon-bot` Won (Score: 59 vs 155, 16 rounds, 694 steps)
   - Seed `2063595735`: `mon-bot` Won (Score: 102 vs 153, 21 rounds, 827 steps)
   - Seed `329389206`: `mon-bot` Won (Score: 41 vs 151, 16 rounds, 623 steps)
   - Outcome: 4/4 Won (100.0%) in ~12 seconds.
2. **Fixed Starter Bias**:
   `initial_dealer_index` is hardcoded to `1` (`p0` always starts round 1).
3. **Threshold Discrepancy**:
   `benchmark_suite.py` requires $100\%$ (`all(sr["won"])`), whereas the follow-up Acceptance Criteria allows $\ge 75\%$ (3/4 wins).
4. **Asymmetry Finding**:
   To test role sensitivity, we executed `arena match medium --vs bot.py --seed 848914317`. With roles reversed (`medium` as `p0`, `mon-bot` as `p1`), `medium_bot` won 126 vs 159 across 26 rounds. This demonstrates that seed dominance is strongly affected by player perspective.

---

## 3. Investigation: Baselines Testing (`builtin:random` and `builtin:basic`)

### 3.1 Requirements Specification
- `ORIGINAL_REQUEST.md` (Initial §2): *"Win rate >= 95% vs builtin:random and builtin:basic."*
- `ORIGINAL_REQUEST.md` (Follow-up Acceptance Criteria): *"Win rate >= 98% vs builtin:random and builtin:basic."*
- `TEST_INFRA.md`: *"$\ge 95\%$ win rate across 50 games vs builtin:random and 50 games vs builtin:basic."*

### 3.2 Current Implementation Analysis
In `benchmark_suite.py:955-975`:
```python
# benchmark_suite.py:959-968
t2_random = runner.run_series("builtin:random", games=games, base_seed=base_seed)
t2_basic = runner.run_series("basic", games=games, base_seed=base_seed)
t2_passed = (
    t2_random["win_rate_pct"] >= 95.0
    and t2_random["forfeits"] == 0
    and t2_basic["win_rate_pct"] >= 80.0
    and t2_basic["forfeits"] == 0
)
```
And in formatting (`benchmark_suite.py:771-800`):
```python
target_wr = 95.0 if "random" in r["opponent_spec"] else 80.0
```

### 3.3 Key Findings
1. **Lax Basic Threshold**:
   The pass threshold for `builtin:basic` in `benchmark_suite.py` is set to **`80.0%`**. This directly contradicts `ORIGINAL_REQUEST.md`, which requires $\ge 95\%$ (initial) or $\ge 98\%$ (follow-up).
2. **Match Count & Seeds**:
   By default, `games = 50`, generating seeds `42` to `91` (`base_seed + i`).
3. **Role Limitation**:
   Like Tier 3, `mon-bot` is always challenger `p0`, and baseline bots are always `p1`. Dealer index alternates.
4. **Smoke Test in Tier 1**:
   In addition to Tier 2, Tier 1 includes `_verify_smoke_test()` which runs 1 match vs `builtin:random` with seed 42, ensuring 0 forfeits/crashes.

---

## 4. Benchmark Harness Structure & Required Changes for R4

### 4.1 Current Architecture Breakdown
```
benchmark_suite.py
├── Colors                          # Terminal ANSI coloring
├── LatencyProfile                  # Statistical latency calculator (percentiles, slow moves, timeouts)
├── InstrumentedBot                 # Bot decorator timing decide() calls
├── run_single_match()              # Standalone match runner
├── Tier1Verifier                   # Invariants & sanity checks:
│   ├── _verify_smoke_test()        # Seed 42 vs random
│   ├── _verify_packaging()         # AST & build_submission_zip check
│   ├── _verify_anti_queen_invariant() # Solitary Queen endgame trap check
│   ├── _verify_suit_choice()       # Suit choice validity check
│   └── _verify_legality_adherence()# 10 synthetic turns legal action check
├── BenchmarkRunner                 # Series and seed runner:
│   ├── run_series()                # Series execution (currently asymmetric p0-only)
│   └── run_seed()                  # Deterministic seed runner (p0-only)
├── ReportFormatter                 # Formatted console outputs
├── run_benchmark()                 # Orchestrator across Tiers 1-4 & JSON writer
└── main()                          # CLI arguments & entry point
```

### 4.2 Comprehensive Gap Analysis Against Acceptance Criteria

| Requirement / Criterion | Specified in R4 / Acceptance Criteria | Current in `benchmark_suite.py` | Status / Gap |
|---|---|---|:---:|
| **Medium Match Count** | 50 games total | Default `--games 50` | Satisfied |
| **Medium Player Slot** | **25 as challenger p0, 25 as opponent p1** | **50 as challenger p0, 0 as opponent p1** | **VIOLATION** |
| **Alternating Dealers** | Eliminates first-mover advantage | Alternates `dealer = 1 if (i%2==0) else 0` | Partially satisfied (p0 only) |
| **Medium Win Rate** | $\ge 70\%$ (Acceptance Criteria) | Checked against $\ge 65.0\%$ | **DISCREPANCY** |
| **Baselines Win Rate** | $\ge 95\%$ (or $\ge 98\%$) vs Random & Basic | Random $\ge 95\%$, **Basic $\ge 80\%$** | **DISCREPANCY** |
| **Leaderboard Seeds** | Seeds: 848914317, 1477911113, 2063595735, 329389206; WR $\ge 75\%$ | 4 seeds tested vs medium; requires $100\%$ | Divergence (100% vs 75%) |
| **Decision Latency** | Mean $< 50$ ms, Max $< 300$ ms, Budget $1000$ ms | Measured & printed, but **NOT gated** in `overall_passed` | **GAP** |
| **Packaging Validation** | `arena pack .` produces valid `mon-bot-submission.zip` | SDK call creates temporary zip in `/tmp` | Minor gap (doesn't verify disk artifact) |
| **CLI & JSON Reporting** | Detailed output & structured export | Supported via `--json-out` | Satisfied |

---

## 5. Detailed Implementation Blueprint for Full R4 Compliance

To achieve 100% compliance with R4 and the user Acceptance Criteria, the following changes must be implemented in `benchmark_suite.py`:

### 5.1 Implement Symmetric Tournament Mode in `BenchmarkRunner`
Add a dedicated method `run_symmetric_series` (or update `run_series` with a `symmetric=True` flag):
- Run $N$ total games (default 50).
- Games $0 \dots \lfloor N/2 \rfloor - 1$ (25 games): `mon-bot` is challenger (`p0`), `opponent` is `p1`.
  - Initial dealer alternates: `dealer = 1 if (i % 2 == 0) else 0`.
  - My slot: `my_slot = "p0"`.
- Games $\lfloor N/2 \rfloor \dots N - 1$ (25 games): `opponent` is challenger (`p0`), `mon-bot` is opponent (`p1`).
  - Initial dealer alternates: `dealer = 0 if (i % 2 == 0) else 1`.
  - My slot: `my_slot = "p1"`.
- Dynamic Win/Loss Accounting:
  ```python
  is_win = (res.winner_id == my_slot) and res.reason == "normal"
  is_loss = (res.winner_id is not None and res.winner_id != my_slot) and res.reason == "normal"
  is_my_forfeit = (res.forfeited_player_id == my_slot)
  ```
- Track and report granular metrics:
  - `p0_games`, `p0_wins`, `p0_win_rate`
  - `p1_games`, `p1_wins`, `p1_win_rate`
  - `dealer_p0_win_rate`, `dealer_p1_win_rate`
  - Aggregate symmetric win rate

### 5.2 Update Acceptance Thresholds
In `run_benchmark()`:
- Tier 2 Basic threshold:
  Change `t2_basic["win_rate_pct"] >= 80.0` to `t2_basic["win_rate_pct"] >= 95.0` (or `98.0`).
- Tier 2 Random threshold:
  Change `t2_random["win_rate_pct"] >= 95.0` to `t2_random["win_rate_pct"] >= 98.0`.
- Tier 3 Medium threshold:
  Change `t3_medium["win_rate_pct"] >= 65.0` to `t3_medium["win_rate_pct"] >= 70.0`.
- Tier 4 Leaderboard seeds:
  Acceptance threshold: `win_rate_pct >= 75.0` (at least 3 of 4 seeds won), reporting individual seed outcomes.

### 5.3 Implement Latency Hard Gating
In `run_benchmark()`:
Evaluate the recorded `LatencyProfile`:
```python
lat_stats = runner.latency_profile.compute_stats()
latency_passed = (
    lat_stats["count"] > 0
    and lat_stats["mean"] < 50.0
    and lat_stats["timeouts_gt_1000ms"] == 0
    and lat_stats["budget_compliance_pct"] >= 99.0  # <300ms
)
results_data["latency_passed"] = latency_passed
```
Factor `latency_passed` into `overall_passed`:
```python
overall_passed = (
    (not run_t1 or t1_passed)
    and (not run_t2 or t2_passed)
    and (not run_t3 or t3_passed)
    and (not run_t4 or t4_passed)
    and latency_passed
)
```

### 5.4 Verify Real Packaging Artifact
In `Tier1Verifier._verify_packaging()`:
In addition to the SDK in-memory test, check if `mon-bot-submission.zip` exists in the project root (or run `arena pack .`), and validate it via `validate_submission_zip()` and `load_submission_zip()`.

### 5.5 CLI & Formatter Updates
- Add `--symmetric` flag to CLI (defaulting to `True` for Tier 3).
- Update `ReportFormatter` to display the symmetric breakdown table (`P0 (Challenger)` vs `P1 (Opponent)`).

---

## 6. Summary Table: Current vs Proposed Benchmark Behavior

| Metric / Behavior | Current Behavior | Proposed R4-Compliant Behavior |
|---|---|---|
| **Tier 3 Match Count** | 50 games vs medium | 50 games vs medium |
| **Tier 3 Roles** | 50 as p0, 0 as p1 | 25 as p0, 25 as p1 |
| **Tier 3 Dealer** | Alternates dealer for p0 | Alternates dealer in both p0 and p1 sets |
| **Tier 3 Win Threshold** | $\ge 65.0\%$ | $\ge 70.0\%$ |
| **Tier 2 Basic Threshold** | $\ge 80.0\%$ | $\ge 95.0\%$ (target 98%) |
| **Tier 2 Random Threshold**| $\ge 95.0\%$ | $\ge 95.0\%$ (target 98%) |
| **Tier 4 Seed Evaluation** | 4 seeds as p0, requires 100% | 4 seeds (optionally symmetric), requires $\ge 75\%$ |
| **Decision Latency Gating** | Informational only | Hard gate: mean $< 50$ms, max $< 300$ms, 0 timeouts |
| **Packaging Validation** | Validates temp zip | Validates temp zip + `mon-bot-submission.zip` |
