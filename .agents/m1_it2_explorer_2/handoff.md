# Handoff Report: Timeout Isolation & Server Decision Limit Strategy (Milestone M1 Iteration 2)

**Role**: M1 Iteration 2 Explorer 2  
**Date**: 2026-09-09T14:32:00Z  
**Working Directory**: `/home/ibrahim-tomota/mon-bot/.agents/m1_it2_explorer_2`  
**Handoff Type**: Hard (Investigation & Fix Strategy Complete)  
**Target File**: `/home/ibrahim-tomota/mon-bot/benchmark_suite.py`  
**Related File**: `/home/ibrahim-tomota/mon-bot/test_engine.py`  

---

## 1. Observation

### 1.1 Opponent Timeout Falsely Fails Challenger
In `/home/ibrahim-tomota/mon-bot/benchmark_suite.py` lines 1288–1300 and line 1324:
```python
1288:     match_timeouts = 0
1289:     if run_t2:
1290:         match_timeouts += sum(1 for m in t2_random.get("matches", []) if m.get("reason") == "timeout")
1291:         match_timeouts += sum(1 for m in t2_basic.get("matches", []) if m.get("reason") == "timeout")
1292:     if run_t3:
1293:         match_timeouts += sum(1 for m in t3_medium.get("matches", []) if m.get("reason") == "timeout")
1294:     if run_t4:
1295:         match_timeouts += sum(1 for s in seed_results if s.get("reason") == "timeout")
1296: 
1297:     decision_timeouts = final_lat_stats.get("timeouts_gt_1000ms", 0)
1298:     slow_moves_300 = final_lat_stats.get("slow_moves_gt_300ms", 0)
1299:     total_timeouts = match_timeouts + decision_timeouts
...
1324:         and (total_timeouts == 0)
```
When an opponent bot times out:
- `m["reason"] == "timeout"`
- `m["winner_id"] == m["my_slot"]` (mon-bot won!)
- `match_timeouts` increments to 1, causing `total_timeouts == 0` to evaluate to `False`.
- `overall_passed` evaluates to `False`, aborting the benchmark with `BENCHMARK_FAILED`.

### 1.2 Opponent Non-Normal Finish Erroneously Flags Tier 4 Forfeit
In `/home/ibrahim-tomota/mon-bot/benchmark_suite.py` lines 1081 and 1257:
```python
1081:             is_forfeit = s.get("forfeit", False) or s.get("reason") != "normal"
...
1257:             1 for sr in seed_results if sr.get("forfeit", False) or sr.get("reason") != "normal"
```
When an opponent times out or forfeits in Tier 4 reference seeds:
- `sr.get("reason") != "normal"` is `True`.
- `t4_forfeits` increments to 1, causing `t4_passed` to be `False`.
- `total_forfeits` increments to 1, causing `total_forfeits == 0` in line 1323 to fail.

### 1.3 Missing `forfeited_player_id` in Match Details
In `run_series` (lines 792–809) and `run_seed` (lines 900–910):
- `detail` dictionary in `run_series` records `game_index`, `seed`, `my_slot`, `opp_slot`, `winner_id`, `won`, `reason`, `scores`, but omits `res.forfeited_player_id`.
- `run_seed` return dict similarly omits `res.forfeited_player_id` and slot assignments.

### 1.4 Hard Server Limit Discrepancy (400ms vs 1000ms)
In `/home/ibrahim-tomota/mon-bot/benchmark_suite.py`:
- Line 180: `def run_single_match(..., decision_timeout_ms: int = 1000)`
- Line 743: `config = MatchConfig(..., decision_timeout_ms=1000)`
- Line 877: `config = MatchConfig(..., decision_timeout_ms=1000)`
- Line 1297: `decision_timeouts = final_lat_stats.get("timeouts_gt_1000ms", 0)`
- Line 1069: prints `Timeouts (>1000ms)`
Per `ORIGINAL_REQUEST.md` lines 58–60:
```
1. HARD SERVER TIMEOUT: 400 ms per decision (NOT 1000ms!). The decision engine MUST target 80ms - 180ms with hard cutoff at 250ms to guarantee zero timeouts/forfeits.
```
In `i151_engine.runner.match_runner._run_match`:
`_decide_with_timeout` arms `signal.setitimer(signal.ITIMER_REAL, timeout_ms / 1000.0)`. With 1000ms, the engine allows moves up to 1000ms before aborting, failing to mirror the official 400ms cutoff. In addition, moves taking between 400.1ms and 999.9ms are not flagged as decision timeouts.

### 1.5 Exception Unwind Skips Profile Record
In `InstrumentedBot.decide` (lines 154–161):
```python
        t0 = time.perf_counter()
        action = self._inner.decide(view, legal_actions, time_left_ms)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        self.profile.record(elapsed_ms)
        return action
```
If `TimeoutError` is raised by `signal.setitimer` at 400ms, execution unwinds before `self.profile.record` is reached.

---

## 2. Logic Chain

1. **Step 1 (From Obs 1.1)**: `match_timeouts` counts all matches where `reason == "timeout"`. When `mon-bot` plays an opponent that times out, `mon-bot` was not at fault and won the match (`winner_id == my_slot`). Counting this in `match_timeouts` and gating on `total_timeouts == 0` erroneously penalizes `mon-bot` for opponent flaws.
2. **Step 2 (From Obs 1.2)**: Checking `sr.get("reason") != "normal"` in Tier 4 penalizes `mon-bot` whenever an opponent finishes non-normally. Because `s.get("forfeit")` already correctly tracks whether `mon-bot` forfeited (`is_forfeit_loss`), the clause `or s.get("reason") != "normal"` is redundant and harmful.
3. **Step 3 (From Obs 1.3)**: Adding `"forfeited_player_id": res.forfeited_player_id` to both `detail` (in `run_series`) and the return dict of `run_seed` provides unambiguous data to distinguish challenger timeouts (`forfeited_player_id == my_slot`) from opponent timeouts (`forfeited_player_id == opp_slot`).
4. **Step 4 (From Obs 1.4)**: The official competition platform enforces a 400ms hard server limit. Setting `decision_timeout_ms=400` in `MatchConfig` aligns the engine runner with the official competition cutoff. Furthermore, defining `decision_timeouts = final_lat_stats.get("timeouts_gt_400ms", 0)` ensures that any move exceeding 400ms is captured as a decision timeout.
5. **Step 5 (From Obs 1.5)**: Adding `try ... finally` in `InstrumentedBot.decide` guarantees that latency duration is recorded even if `SIGALRM` / `TimeoutError` interrupts the decision call.
6. **Conclusion**: Implementing these targeted adjustments completely isolates opponent timeouts, restores fairness to `overall_passed` gating, and strictly enforces the official 400ms server limit.

---

## 3. Caveats

- **No Caveats**: All findings and proposed fixes were empirically validated using synthetic test harnesses, live engine runs against builtin opponents (`random`, `basic`, `medium`), and adversarial test reproduction.

---

## 4. Conclusion

The timeout accounting and configuration in `benchmark_suite.py` can be fully corrected by:
1. Storing `"forfeited_player_id": res.forfeited_player_id` in `run_series` details and `run_seed` results.
2. Isolating `challenger_match_timeouts` from `opponent_match_timeouts` and gating `total_timeouts` solely on challenger timeouts.
3. Removing `or sr.get("reason") != "normal"` in Tier 4 forfeit accounting.
4. Updating `MatchConfig` to `decision_timeout_ms=400` across `run_single_match`, `run_series`, `run_seed`, and `_verify_smoke_test`.
5. Wrapping `InstrumentedBot.decide` with `try ... finally`.
6. Querying `timeouts_gt_400ms` as the primary metric for `decision_timeouts`.

Full diffs and rationale are detailed in `/home/ibrahim-tomota/mon-bot/.agents/m1_it2_explorer_2/analysis.md`.

---

## 5. Verification Method

To independently verify the strategy:

1. **Verify Opponent Timeout Isolation Logic**:
   ```bash
   python3 -c "
   m_opp = {'reason': 'timeout', 'winner_id': 'p0', 'my_slot': 'p0', 'forfeited_player_id': 'p1'}
   m_me = {'reason': 'timeout', 'winner_id': 'p1', 'my_slot': 'p0', 'forfeited_player_id': 'p0'}
   is_chal_timeout = lambda m: m.get('reason') == 'timeout' and (m.get('forfeited_player_id') == m.get('my_slot') or (m.get('winner_id') != m.get('my_slot') and m.get('forfeited_player_id') is None))
   assert not is_chal_timeout(m_opp), 'Opponent timeout must not be challenger timeout'
   assert is_chal_timeout(m_me), 'Challenger timeout must be detected'
   print('Verification Passed: Opponent timeout correctly isolated!')
   "
   ```

2. **Verify 400ms MatchConfig Execution**:
   ```bash
   python3 -c "
   from arena_sdk import MatchConfig
   from i151_engine.runner.match_runner import play_bots_match
   from arena_sdk.opponents import resolve_opponent_arg
   from pathlib import Path
   from benchmark_suite import BenchmarkRunner

   runner = BenchmarkRunner(Path('bot.py'), profile_latency=True)
   opp = resolve_opponent_arg('basic')
   runner.instrumented_bot.setup(Path('.'))
   opp.bot.setup(opp.submission_dir or Path('.'))

   config = MatchConfig(seed=42, target_score=151, decision_timeout_ms=400)
   res = play_bots_match(runner.instrumented_bot, opp.bot, config, challenger_name='mon-bot', opponent_name=opp.name, manage_lifecycle=False)
   assert res.reason == 'normal' and res.winner_id is not None
   print('Verification Passed: 400ms MatchConfig runs successfully!')
   runner.instrumented_bot.teardown()
   opp.bot.teardown()
   "
   ```

3. **Verify Existing Suites**:
   ```bash
   python3 -m unittest test_engine.py
   python3 benchmark_suite.py --tier 1
   ```
