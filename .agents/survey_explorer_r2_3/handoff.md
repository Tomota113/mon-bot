# Handoff Report: Benchmark Suite Capabilities & R4 Compliance (Survey Explorer 3)

**Date**: 2026-09-09  
**Agent**: Survey Explorer 3  
**Working Directory**: `/home/ibrahim-tomota/mon-bot/.agents/survey_explorer_r2_3`  
**Report Artifact**: `/home/ibrahim-tomota/mon-bot/.agents/survey_explorer_r2_3/benchmark_report.md`

---

## 1. Observation

### Obs 1: Asymmetric Match Invocation in `benchmark_suite.py`
In `/home/ibrahim-tomota/mon-bot/benchmark_suite.py`, lines 586-610:
```python
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
In `i151_engine.runner.match_runner.play_bots_match`, the first argument is mapped to `{"id": "p0", "role": "challenger"}` and the second argument to `{"id": "p1", "role": "opponent"}`.
`self.instrumented_bot` is passed strictly as the first argument in 100% of matches. Zero matches are played where `mon-bot` is passed as the second argument (`p1`).

### Obs 2: Dealer Alternation vs Slot Role
In `benchmark_suite.py`, lines 575-581:
```python
p0_starts = (
    (i % 2 == 0)
    if p0_starter_rate == 0.5
    else (i / max(1, games) < p0_starter_rate)
)
starter = "p0" if p0_starts else "p1"
dealer = 1 if p0_starts else 0
```
This toggles `initial_dealer_index` between 1 and 0 (which decides who plays first in round 1), but leaves `mon-bot` permanently in the `p0` slot.

### Obs 3: Reference Seeds Testing
In `benchmark_suite.py`, lines 665-677 and 996-1001:
```python
def run_seed(self, opponent_spec: str, seed: int) -> dict[str, Any]:
    opp = resolve_opponent_arg(opponent_spec)
    ...
    config = MatchConfig(
        seed=seed,
        target_score=self.target_score,
        initial_dealer_index=1,  # p0 starts
        decision_timeout_ms=1000,
    )
...
ref_seeds = [848914317, 1477911113, 2063595735, 329389206]
seed_results: list[dict[str, Any]] = []
for s in ref_seeds:
    s_res = runner.run_seed("medium", s)
    seed_results.append(s_res)
t4_passed = all(sr["won"] for sr in seed_results)
```
- All 4 seeds are executed with `mon-bot` as `p0` and `initial_dealer_index=1`.
- `t4_passed` enforces 100% win rate (4/4 wins).
- When executed (`python3 benchmark_suite.py --tier 4`), all 4 passed:
  - Seed 848914317: won 62 vs 188
  - Seed 1477911113: won 59 vs 155
  - Seed 2063595735: won 102 vs 153
  - Seed 329389206: won 41 vs 151
- When tested with inverted slot (`arena match medium --vs bot.py --seed 848914317`), `medium_bot` won 126 vs 159 across 26 rounds.

### Obs 4: Baseline Testing and Threshold Discrepancy
In `benchmark_suite.py`, lines 964-967:
```python
t2_passed = (
    t2_random["win_rate_pct"] >= 95.0
    and t2_random["forfeits"] == 0
    and t2_basic["win_rate_pct"] >= 80.0
    and t2_basic["forfeits"] == 0
)
```
In `ReportFormatter.print_tier2_results`, line 771:
```python
target_wr = 95.0 if "random" in r["opponent_spec"] else 80.0
```
In `/home/ibrahim-tomota/mon-bot/.agents/ORIGINAL_REQUEST.md`:
- Line 17: "Win rate >= 95% vs builtin:random and builtin:basic."
- Line 52: "Win rate >= 98% vs builtin:random and builtin:basic."
- Line 53: "Win rate >= 70% vs builtin:medium across 50 symmetric matches (alternating p0/p1)."
- Line 54: "Win rate >= 75% across the top leaderboard reference seeds (848914317, 1477911113, 2063595735, 329389206)."

### Obs 5: Lack of Latency Gating
In `benchmark_suite.py`, lines 1009-1024:
```python
overall_passed = (
    (not run_t1 or t1_passed)
    and (not run_t2 or t2_passed)
    and (not run_t3 or t3_passed)
    and (not run_t4 or t4_passed)
)
```
Latency statistics are computed and printed, but `overall_passed` never checks `lat_stats["mean"] < 50.0` or timeouts. A bot taking 200 ms average would still be marked `GRAND_MASTER_READY`.

---

## 2. Logic Chain

1. **Premise 1 (R4 Mandate)**: R4 specifies: *"Benchmark the bot on symmetric two-way matches against builtin:medium (50 games total: 25 as challenger p0, 25 as opponent p1) with alternating dealers to eliminate first-player bias."* (Obs 4).
2. **Premise 2 (Role Hardcoding)**: In `benchmark_suite.py`, `self.instrumented_bot` is unconditionally passed as argument 1 to `play_bots_match`, which designates it as `player_id="p0"` and role `"challenger"`. Win accounting unconditionally checks `res.winner_id == "p0"` (Obs 1).
3. **Inference 1**: While `benchmark_suite.py` alternates who starts round 1 via `dealer = 1` vs `dealer = 0` (Obs 2), it never switches player slots. Therefore, it executes 50 matches as challenger `p0` and 0 matches as opponent `p1`. It fails to satisfy R4's two-way symmetric match requirement.
4. **Premise 3 (Seed Asymmetry)**: Seed 848914317 was won decisively as `p0` (62 vs 188) but lost as `p1` (126 vs 159) against the same `builtin:medium` (Obs 3).
5. **Inference 2**: Player slot assignment introduces significant strategic divergence in i151 game flow. Without true slot inversion in the benchmark harness, reported win rates are biased towards challenger dynamics.
6. **Premise 4 (Threshold Discrepancy)**: `benchmark_suite.py` uses an 80% threshold for `builtin:basic` (Obs 4), while the specification mandates $\ge 95\%$ or $\ge 98\%$. Furthermore, Tier 3 checks $\ge 65\%$ while Acceptance Criteria mandates $\ge 70\%$.
7. **Premise 5 (Latency Ungated)**: Acceptance criteria requires average latency $< 50$ ms and max $< 300$ ms. `overall_passed` currently ignores latency stats completely (Obs 5).
8. **Inference 3**: To completely satisfy R4 and acceptance criteria, `benchmark_suite.py` requires code modifications across tournament pairing (25 p0 / 25 p1), threshold alignment, latency pass/fail gating, and submission archive verification.

---

## 3. Caveats

- **Network Mode**: Investigation was conducted locally with offline access to `i151_engine` and `arena_sdk`. Remote tournament bots (Oureiba Oumar, Anw Djigui) are not runnable locally; `builtin:medium` on the 4 reference seeds serves as the local gold-standard proxy as documented in `TEST_INFRA.md`.
- **Existing `bot.py` Performance**: Running the full 50-game symmetric series was not executed to completion in this investigation turn to preserve compute and adhere to read-only survey scope; however, individual component tests (Tier 1, Tier 4, inverted match) were executed and confirmed.

---

## 4. Conclusion

1. `benchmark_suite.py` currently implements alternating dealer indices for player 0, but does **not** implement the required two-way symmetric tournament against `builtin:medium` (25 as `p0`, 25 as `p1`).
2. Reference seeds are tested only with `p0` starting and require 100% win rate (vs 75% in Acceptance Criteria). All 4 seeds currently pass as `p0`, but role inversion reveals distinct vulnerability when starting as `p1`.
3. Baseline opponent testing has an under-specified threshold (80% vs `basic`) compared to user requirements ($\ge 95\text{--}98\%$).
4. The benchmark harness requires 5 structural updates detailed in `benchmark_report.md`:
   - Slot-role symmetry pairing in `run_series` (25 games as challenger `p0`, 25 games as opponent `p1`).
   - Dynamic win/loss evaluation based on assigned slot (`my_slot`).
   - Threshold alignment (Medium $\ge 70\%$, Baselines $\ge 95\text{--}98\%$, Seeds $\ge 75\%$).
   - Hard latency gating in `overall_passed` (mean $< 50$ms, max $< 300$ms, 0 timeouts).
   - Artifact check validating `mon-bot-submission.zip` generated via `arena pack .`.

---

## 5. Verification Method

To independently verify all findings and observations:

1. **Verify Role Hardcoding**:
   Inspect lines 586-610 in `benchmark_suite.py`:
   ```bash
   sed -n '585,615p' /home/ibrahim-tomota/mon-bot/benchmark_suite.py
   ```
   Note `play_bots_match(self.instrumented_bot, opp.bot, ...)` and `is_win = res.winner_id == "p0"`.

2. **Verify Baseline Threshold Discrepancy**:
   Inspect lines 963-968 in `benchmark_suite.py`:
   ```bash
   sed -n '963,968p' /home/ibrahim-tomota/mon-bot/benchmark_suite.py
   ```
   Observe `t2_basic["win_rate_pct"] >= 80.0`.

3. **Verify Reference Seeds Execution as p0**:
   ```bash
   python3 /home/ibrahim-tomota/mon-bot/benchmark_suite.py --tier 4
   ```
   Confirms 4/4 wins with `mon-bot` as `p0`.

4. **Verify Asymmetry on Seed 848914317**:
   ```bash
   arena match medium --vs /home/ibrahim-tomota/mon-bot/bot.py --seed 848914317
   ```
   Confirms `medium_bot` victory when roles are inverted.

5. **Verify Inverted `play_bots_match` Support**:
   ```bash
   python3 -c "from arena_sdk.opponents import resolve_opponent_arg; from i151_engine.runner.match_runner import play_bots_match; from arena_sdk import MatchConfig; from pathlib import Path; import bot; opp = resolve_opponent_arg('medium'); cfg = MatchConfig(seed=42, target_score=151); res = play_bots_match(opp.bot, bot, cfg, challenger_name=opp.name, opponent_name='mon-bot', opponent_id='student:mon-bot', challenger_dir=opp.submission_dir, opponent_dir=Path('.'), manage_lifecycle=True); print('Winner:', res.winner_id, 'Scores:', res.final_scores)"
   ```
   Confirms the engine cleanly supports swapping challenger and opponent bots.
