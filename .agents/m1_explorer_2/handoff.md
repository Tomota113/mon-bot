# Handoff Report: Benchmark Threshold Alignment & Hard Latency Gating (M1)

**Agent**: M1 Explorer 2  
**Date**: 2026-09-09  
**Working Directory**: `/home/ibrahim-tomota/mon-bot/.agents/m1_explorer_2`  
**Handoff Type**: Hard (Investigation & Strategy Complete)  
**Target File**: `/home/ibrahim-tomota/mon-bot/benchmark_suite.py`  

---

## 1. Observation

### Observation 1.1: Tier 2 Thresholds in `benchmark_suite.py`
In `/home/ibrahim-tomota/mon-bot/benchmark_suite.py:963-968`:
```python
t2_passed = (
    t2_random["win_rate_pct"] >= 95.0
    and t2_random["forfeits"] == 0
    and t2_basic["win_rate_pct"] >= 80.0
    and t2_basic["forfeits"] == 0
)
```
And in `/home/ibrahim-tomota/mon-bot/benchmark_suite.py:772-774`:
```python
target_wr = 95.0 if "random" in r["opponent_spec"] else 80.0
passed = r["win_rate_pct"] >= target_wr and r["forfeits"] == 0
```
Running `python3 benchmark_suite.py --quick --tier 2` produced:
```
[TIER 2: BASELINE OPPONENTS (Target >= 95% WR)]
  ✓ PASSED vs builtin:random  ( 5 games) :     5-0 (100.0% WR) | Forfeits: 0  [Aléatoire]
  ✓ PASSED vs basic           ( 5 games) :     4-1 (80.0% WR) | Forfeits: 0  [basic_bot]
  Tier 2 Result: 9/10 Games Won (90.0% Aggregate WR)

════════════════════════════════════════════════════════════════════════════════
 OVERALL VERDICT: GRAND_MASTER_READY ★★★★★ (ALL ACCEPTANCE CRITERIA SATISFIED)
════════════════════════════════════════════════════════════════════════════════
```
Verbatim observed: `basic_bot` achieved only 80.0% win rate yet was declared `PASSED` and triggered `OVERALL VERDICT: GRAND_MASTER_READY`. `ORIGINAL_REQUEST.md:52` strictly mandates: `"Win rate >= 98% vs builtin:random and builtin:basic."`

### Observation 1.2: Tier 3 Threshold in `benchmark_suite.py`
In `/home/ibrahim-tomota/mon-bot/benchmark_suite.py:982`:
```python
t3_passed = t3_medium["win_rate_pct"] >= 65.0 and t3_medium["forfeits"] == 0
```
And in `/home/ibrahim-tomota/mon-bot/benchmark_suite.py:811-814`:
```python
print(f"\n{Colors.BOLD}[TIER 3: COMPETITIVE TACTICAL MATCH (Target >= 65% WR vs Medium)]{Colors.RESET}")
passed = medium_res["win_rate_pct"] >= 65.0 and medium_res["forfeits"] == 0
```
`ORIGINAL_REQUEST.md:53` mandates: `"Win rate >= 70% vs builtin:medium across 50 symmetric matches (alternating p0/p1)."`

### Observation 1.3: Tier 4 Threshold in `benchmark_suite.py`
In `/home/ibrahim-tomota/mon-bot/benchmark_suite.py:1001-1002`:
```python
ref_seeds = [848914317, 1477911113, 2063595735, 329389206]
...
t4_passed = all(sr["won"] for sr in seed_results)
```
And in `/home/ibrahim-tomota/mon-bot/benchmark_suite.py:856-857`:
```python
print(f"\n{Colors.BOLD}[TIER 4: LEADERBOARD REFERENCE SEEDS (Target: 100% Win Rate)]{Colors.RESET}")
```
`ORIGINAL_REQUEST.md:54` specifies: `"Win rate >= 75% across the top leaderboard reference seeds (848914317, 1477911113, 2063595735, 329389206)."`, meaning at least 3 of 4 seeds must be won.

### Observation 1.4: Lack of Latency Gating in `overall_passed`
In `/home/ibrahim-tomota/mon-bot/benchmark_suite.py:1009-1028`:
```python
    overall_passed = (
        (not run_t1 or t1_passed)
        and (not run_t2 or t2_passed)
        and (not run_t3 or t3_passed)
        and (not run_t4 or t4_passed)
    )

    final_lat_stats = runner.latency_profile.compute_stats()
    results_data["summary"] = {
        "tier1_passed": t1_passed if run_t1 else None,
        "tier2_passed": t2_passed if run_t2 else None,
        "tier3_passed": t3_passed if run_t3 else None,
        "tier4_passed": t4_passed if run_t4 else None,
        "overall_passed": overall_passed,
        "verdict": "GRAND_MASTER_READY" if overall_passed else "BENCHMARK_FAILED",
    }
    if "latency_profile_ms" not in results_data:
        results_data["latency_profile_ms"] = final_lat_stats

    ReportFormatter.print_verdict(overall_passed, final_lat_stats)
```
`overall_passed` ignores `final_lat_stats` entirely. Furthermore, in `ReportFormatter.print_verdict` (`benchmark_suite.py:884-900`), `latency_stats` is accepted as a parameter but never displayed or checked.

### Observation 1.5: Empirical Measured Latency of Current Engine
Running `python3 benchmark_suite.py --tier 4 --json-out /tmp/t4.json`:
- `count`: 1622 decisions
- `mean`: 6.240 ms
- `median`: 0.009 ms
- `p90`: 18.621 ms
- `p95`: 30.579 ms
- `p99`: 101.674 ms
- `max`: 190.147 ms
- `slow_moves_gt_300ms`: 0
- `timeouts_gt_1000ms`: 0

Running `python3 benchmark_suite.py --quick --tier 3 --json-out /tmp/t3.json`:
- `count`: 2803 decisions
- `mean`: 6.679 ms
- `max`: 203.797 ms
- `slow_moves_gt_300ms`: 0
- `timeouts_gt_1000ms`: 0

---

## 2. Logic Chain

1. **Premise**: Per `ORIGINAL_REQUEST.md` (lines 45-55) and dispatch instructions, acceptance criteria require:
   - Baselines win rate >= 98% vs both `builtin:random` and `builtin:basic` with 0 forfeits.
   - Tier 3 win rate >= 70% vs `builtin:medium` across 50 symmetric games with 0 forfeits.
   - Tier 4 win rate >= 75% across the 4 leaderboard seeds (at least 3/4 wins) with 0 forfeits.
   - Average decision latency strictly < 50.0 ms.
   - Max decision latency < 300.0 ms.
   - 0 timeouts and 0 forfeits across all tiers.
2. **Step 1 (Threshold Discrepancy)**:
   From Observation 1.1, `benchmark_suite.py` accepts 80.0% win rate vs `builtin:basic` and 95.0% vs `builtin:random`.
   From Observation 1.2, it accepts 65.0% vs `builtin:medium`.
   From Observation 1.3, it demands 100% (4/4) instead of 75% (3/4) on reference seeds.
   Therefore, the evaluation predicates and formatted labels across Tiers 2, 3, and 4 must be updated to 98.0%, 70.0%, and 75.0% respectively.
3. **Step 2 (Forfeits & Timeouts Integration)**:
   In Observation 1.1 and 1.2, forfeits are checked per tier in Tiers 2 and 3, but Tier 4 does not explicitly check for forfeit reasons (`res.reason != "normal"`).
   Furthermore, any match-level timeout (`res.reason == "timeout"`) or decision-level timeout (`timeouts_gt_1000ms > 0` or move >= 300ms) is an immediate failure.
   Therefore, global aggregations `total_forfeits` and `total_timeouts` must be computed across all executed tiers and matches.
4. **Step 3 (Hard Latency Gating in `overall_passed`)**:
   From Observation 1.4, `overall_passed` currently ignores latency statistics.
   To enforce the requirements, `latency_passed` must be computed when profiling is enabled and timed matches are run:
   ```python
   latency_passed = (
       final_lat_stats["count"] > 0
       and final_lat_stats["mean"] < 50.0
       and final_lat_stats["max"] < 300.0
       and decision_timeouts == 0
       and slow_moves_300 == 0
   )
   ```
   And `overall_passed` must require:
   `all_tiers_passed and latency_passed and (total_forfeits == 0) and (total_timeouts == 0)`.
5. **Step 4 (Reporting and Verdict Transparency)**:
   From Observation 1.4, `ReportFormatter.print_verdict` must output a dedicated `Hard Latency Gating` status line displaying the measured mean latency, max latency, timeouts, and forfeits with color coding (green for pass, red for fail).
   The JSON export (`results_data["summary"]` and `results_data["latency_gating"]`) must include structured validation flags.

---

## 3. Caveats

1. **Slot Symmetry Delegation**: The two-way slot inversion architecture in `BenchmarkRunner.run_series()` (25 games as `p0`, 25 games as `p1`) is assigned to peer agent `m1_explorer_1`. Our Tier 3 threshold check (`win_rate_pct >= 70.0`) operates seamlessly regardless of whether `run_series` is asymmetric or symmetric, but symmetric play is necessary to satisfy R4 fully.
2. **Server Hard Cutoff (400ms)**: Official tournament regulations enforce a 400ms server cutoff. Since our gating enforces `max < 300.0 ms`, passing our max threshold guarantees compliance with both the 300ms internal requirement and the 400ms external server constraint.
3. **Zero Decisions Edge Case**: If a user runs only Tier 1 (`--tier 1` or `--tier smoke`), no decisions are timed (`final_lat_stats["count"] == 0`). In this case, `latency_passed` defaults to `True` so unit smoke tests do not trigger false latency failures.

---

## 4. Conclusion

The implementation strategy detailed in `/home/ibrahim-tomota/mon-bot/.agents/m1_explorer_2/analysis.md` provides exact, drop-in code replacements for `benchmark_suite.py` that:
1. Align Tier 2 to `>= 98.0%` for both `builtin:random` and `builtin:basic` with 0 forfeits.
2. Align Tier 3 to `>= 70.0%` for `builtin:medium` across 50 symmetric games with 0 forfeits.
3. Align Tier 4 to `>= 75.0%` for reference seeds (at least 3/4 wins) with 0 forfeits.
4. Implement hard latency gating in `overall_passed`: mean strictly < 50.0 ms, max < 300.0 ms, 0 timeouts, 0 slow moves > 300ms, and 0 forfeits across all tiers.
5. Upgrade `ReportFormatter.print_verdict` and JSON export to provide full visibility into latency gating and forfeit statistics.

---

## 5. Verification Method

### 5.1 Command Line Verification
After applying the changes to `benchmark_suite.py`, execute:
```bash
# 1. Tier 2 verification (Target >= 98% WR, 0 forfeits)
python3 benchmark_suite.py --tier 2 --games 50

# 2. Tier 3 verification (Target >= 70% WR, 0 forfeits)
python3 benchmark_suite.py --tier 3 --games 50

# 3. Tier 4 reference seeds verification (Target >= 75% WR, 0 forfeits)
python3 benchmark_suite.py --tier 4

# 4. Latency gating validation with JSON export
python3 benchmark_suite.py --tier 4 --json-out /tmp/bench_verify.json
python3 -c "
import json
d = json.load(open('/tmp/bench_verify.json'))
assert d['summary']['latency_passed'] is True, 'Latency gating failed!'
assert d['latency_gating']['mean_latency_ms'] < 50.0, 'Mean latency >= 50ms!'
assert d['latency_gating']['max_latency_ms'] < 300.0, 'Max latency >= 300ms!'
assert d['summary']['total_forfeits'] == 0, 'Forfeits > 0!'
print('ALL VERIFICATION CHECKS PASSED!')
"
```

### 5.2 Negative Invalidation Test
To verify that hard latency gating correctly blocks a faulty bot:
- In `InstrumentedBot.decide`, inject a dummy `time.sleep(0.350)`:
  `python3 benchmark_suite.py --tier 4`
  Must output `Hard Latency Gating: ✗ FAILED`, `OVERALL VERDICT: BENCHMARK_FAILED`, and exit with code `1`.
