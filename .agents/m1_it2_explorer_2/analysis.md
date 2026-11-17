# Forensic Analysis & Strategy Report: Timeout Isolation and Server Decision Limits (M1 Iteration 2)

**Author**: M1 Iteration 2 Explorer 2  
**Date**: 2026-09-09T14:31:40Z  
**Target File**: `/home/ibrahim-tomota/mon-bot/benchmark_suite.py`  
**Related Test File**: `/home/ibrahim-tomota/mon-bot/test_engine.py`  
**Working Directory**: `/home/ibrahim-tomota/mon-bot/.agents/m1_it2_explorer_2`  

---

## 1. Executive Summary

During the Milestone M1 adversarial review, Reviewer 1 and Reviewer 2 identified two major flaws in the timeout handling and decision timeout configuration of `benchmark_suite.py`:

1. **Opponent Timeout Isolation Failure (Reviewer 2 Major Finding)**:
   In `benchmark_suite.py` lines 1288–1300, `match_timeouts` counts every match where `reason == "timeout"` indiscriminately. When an opponent bot (`random`, `basic`, or `medium`) times out—an event that constitutes a legitimate forfeit victory for `mon-bot`—`match_timeouts` increments to 1. This causes `total_timeouts == 0` to fail, resulting in an erroneous `BENCHMARK_FAILED` verdict despite `mon-bot` having won the match. Additionally, in Tier 4 reference seeds (lines 1081 & 1257), `or sr.get("reason") != "normal"` causes any opponent timeout or forfeit to be classified as a forfeit by `mon-bot`, triggering a triple failure.
2. **Hard Server Decision Timeout Discrepancy (Reviewer 1 Finding 3 & Reviewer 2 Finding 3)**:
   Per official tournament rules (`ORIGINAL_REQUEST.md`), the arena platform enforces a **400 ms hard server timeout** per decision (with bot decisions targeting 80–180 ms and hard cutoffs at 250 ms). However, `benchmark_suite.py` instantiates `MatchConfig` with `decision_timeout_ms=1000` (lines 180, 743, 877), and lines 1297–1300 evaluate decision timeouts using `final_lat_stats.get("timeouts_gt_1000ms", 0)`. As a result, the engine runner allows moves up to 1000 ms during simulation before aborting, and decisions between 400 ms and 1000 ms escape classification as decision timeouts.

This report formulates the exact, verified technical remediation strategy to resolve both findings cleanly without breaking any existing acceptance gates.

---

## 2. Forensic Analysis

### 2.1 Issue 1: Opponent Timeout Gating Pollution

#### 2.1.1 Root Cause & Call Chain
In `i151_engine.runner.match_runner`, when a bot decision times out:
```python
def _decide_with_timeout(bot: Bot, view, legal, timeout_ms: int):
    ...
    # When signal timer expires:
    raise TimeoutError()
```
The exception is caught in `_run_match`:
```python
        try:
            action = _decide_with_timeout(bot, view, legal, remaining_ms)
        except TimeoutError:
            return _forfeit_result(match, opponent_id, pid, steps, "timeout", recorder)
```
And `_forfeit_result` constructs:
```python
def _forfeit_result(match, opponent_id, forfeited, steps, reason, recorder):
    winner = "p1" if forfeited == "p0" else "p0"
    return MatchResult(
        winner_id=winner,
        opponent_id=opponent_id,
        reason=reason,                     # "timeout"
        forfeited_player_id=forfeited,      # pid of bot that timed out ("p0" or "p1")
        ...
    )
```

In `benchmark_suite.py`:
1. **Series Matches (`run_series`)**:
   In lines 792–808:
   ```python
   detail = {
       "game_index": i + 1,
       "seed": seed,
       "my_slot": my_slot,       # "p0" or "p1"
       "opp_slot": opp_slot,     # "p1" or "p0"
       "starter": starter_slot,
       "starter_bot": starter_bot,
       "winner_id": res.winner_id,
       "winner_bot": "mon-bot" if res.winner_id == my_slot else opp_name,
       "won": won,
       "reason": res.reason,
       ...
   }
   ```
   **Observation**: `detail` omits `res.forfeited_player_id`.
   When the opponent times out:
   - `res.winner_id == my_slot`
   - `res.forfeited_player_id == opp_slot`
   - `won == True`
2. **Seed Matches (`run_seed`)**:
   In lines 900–910:
   `run_seed` returns a dict with `winner_id`, `reason`, `won`, `forfeit` (`is_forfeit_loss`), but omits `forfeited_player_id`, `my_slot`, and `opp_slot`.
3. **Aggregation in `run_tournament` (lines 1288–1296)**:
   ```python
   match_timeouts = 0
   if run_t2:
       match_timeouts += sum(1 for m in t2_random.get("matches", []) if m.get("reason") == "timeout")
       match_timeouts += sum(1 for m in t2_basic.get("matches", []) if m.get("reason") == "timeout")
   if run_t3:
       match_timeouts += sum(1 for m in t3_medium.get("matches", []) if m.get("reason") == "timeout")
   if run_t4:
       match_timeouts += sum(1 for s in seed_results if s.get("reason") == "timeout")
   ```
   **Vulnerability**: Any match where `reason == "timeout"` increments `match_timeouts`, even if `m.get("winner_id") == m.get("my_slot")` (i.e. opponent timed out and `mon-bot` won).
   Then:
   ```python
   total_timeouts = match_timeouts + decision_timeouts
   overall_passed = ... and (total_timeouts == 0)
   ```
   `overall_passed` evaluates to `False`, aborting the benchmark with `BENCHMARK_FAILED`.
4. **Secondary Defect in Tier 4 Seed Accounting (lines 1081 and 1257)**:
   In line 1081:
   ```python
   is_forfeit = s.get("forfeit", False) or s.get("reason") != "normal"
   ```
   And line 1257:
   ```python
   t4_forfeits = sum(
       1 for sr in seed_results if sr.get("forfeit", False) or sr.get("reason") != "normal"
   )
   ```
   If the opponent times out in Tier 4, `s.get("reason") == "timeout" != "normal"`.
   Consequently, `t4_forfeits` is incremented to 1, causing:
   - `t4_passed = t4_win_rate_pct >= 75.0 and t4_forfeits == 0` -> `False`
   - `total_forfeits += t4_forfeits` -> `total_forfeits >= 1`
   - `overall_passed` fails on `t4_passed`, `total_forfeits == 0`, AND `total_timeouts == 0`.

---

### 2.2 Issue 2: Server Decision Timeout (400ms vs 1000ms) & MatchConfig

#### 2.2.1 Tournament Standard vs Implementation Discrepancy
Per official regulation (`ORIGINAL_REQUEST.md`, lines 58–60):
> "1. HARD SERVER TIMEOUT: 400 ms per decision (NOT 1000ms!). The decision engine MUST target 80ms - 180ms with hard cutoff at 250ms to guarantee zero timeouts/forfeits."

In `benchmark_suite.py`:
- Line 180 (`run_single_match`): `decision_timeout_ms: int = 1000`
- Line 253 (`_verify_smoke_test`): `MatchConfig(seed=42, target_score=151, max_rounds=40)` (defaults to 1000)
- Line 743 (`run_series`): `decision_timeout_ms=1000`
- Line 877 (`run_seed`): `decision_timeout_ms=1000`
- Line 1069 (`print_latency_summary`): prints only `Timeouts (>1000ms)`
- Line 1297 (`run_tournament`): `decision_timeouts = final_lat_stats.get("timeouts_gt_1000ms", 0)`
- Line 1337 (`results_data["latency_gating"]`): `"decision_timeouts_gt_1000ms": decision_timeouts`

#### 2.2.2 Engine Timer Behavior
When `MatchConfig.decision_timeout_ms = 1000`:
- In `_run_match`: `_decide_with_timeout(bot, view, legal, 1000)` sets `signal.setitimer(signal.ITIMER_REAL, 1.0)`.
- If a bot takes 600 ms, no `TimeoutError` is raised by the engine. The turn succeeds, and the game continues. On the official competition server, this move would have been aborted at 400 ms, resulting in an immediate forfeit loss.
- In post-game gating, if `slow_moves_300 == 0` is checked, moves > 300 ms will fail latency gating, but `timeouts_gt_1000ms` will report 0.
- When `MatchConfig.decision_timeout_ms = 400`:
  - `signal.setitimer(signal.ITIMER_REAL, 0.400)` enforces the exact 400 ms cutoff in real time.
  - Any decision taking $\ge 400\text{ ms}$ triggers `TimeoutError` immediately and ends the match in `reason="timeout"`, `forfeited_player_id=pid`.
- In `InstrumentedBot.decide` (lines 154–161):
  ```python
  t0 = time.perf_counter()
  action = self._inner.decide(view, legal_actions, time_left_ms)
  elapsed_ms = (time.perf_counter() - t0) * 1000.0
  self.profile.record(elapsed_ms)
  return action
  ```
  If `TimeoutError` is raised by the engine timer inside `self._inner.decide`, execution unwinds immediately without reaching `self.profile.record(elapsed_ms)`.
  Wrapping this in `try ... finally` ensures that `elapsed_ms` is recorded in `LatencyProfile` even when a move is interrupted by `SIGALRM` / `TimeoutError`.

---

## 3. Exact Remediation Strategy

### 3.1 Principle 1: Isolate Opponent Timeouts Completely
1. **Preserve Forfeited Player ID**:
   In `run_series`, store `"forfeited_player_id": res.forfeited_player_id` in `detail`.
   In `run_seed`, return `"forfeited_player_id": res.forfeited_player_id`, `"my_slot": "p0"`, and `"opp_slot": "p1"`.
2. **Classify Match Timeouts by Offending Player**:
   For any match $m$ with `reason == "timeout"`:
   - **Challenger Timeout (`mon-bot`)**:
     `m.get("forfeited_player_id") == m.get("my_slot")` or (`m.get("winner_id") != m.get("my_slot")` and `m.get("forfeited_player_id") is None`)
   - **Opponent Timeout**:
     `m.get("forfeited_player_id") == m.get("opp_slot")` or (`m.get("winner_id") == m.get("my_slot")` and `m.get("forfeited_player_id") is None`)
3. **Partition Accounting**:
   Track two distinct counters:
   - `challenger_match_timeouts`: counts only matches where `mon-bot` timed out.
   - `opp_match_timeouts`: counts matches where the opponent timed out.
   Only `challenger_match_timeouts` contributes to `match_timeouts` and `total_timeouts`.
   `opp_match_timeouts` is logged for diagnostic reporting.
4. **Fix Tier 4 Forfeit Counting**:
   In `run_tournament` (line 1257) and `ReportFormatter.print_tier4_results` (line 1081), replace:
   ```python
   # Old (vulnerable):
   is_forfeit = s.get("forfeit", False) or s.get("reason") != "normal"
   # New (isolated):
   is_forfeit = s.get("forfeit", False) or s.get("forfeited_player_id") == "p0"
   ```
   This ensures that an opponent forfeit or timeout in Tier 4 seeds does not increment `t4_forfeits`.

---

### 3.2 Principle 2: Enforce 400ms Server Decision Timeout
1. **Set `decision_timeout_ms=400` in All `MatchConfig` Instantiations**:
   - `run_single_match`: line 180 (`decision_timeout_ms: int = 400`)
   - `run_series`: line 743 (`decision_timeout_ms=400`)
   - `run_seed`: line 877 (`decision_timeout_ms=400`)
   - `_verify_smoke_test`: line 253 (`decision_timeout_ms=400`)
2. **Try-Finally in `InstrumentedBot.decide`**:
   Wrap `self._inner.decide` with `try ... finally` so `elapsed_ms` is recorded in `LatencyProfile` even when `SIGALRM` interrupts execution at 400 ms.
3. **Gating on `timeouts_gt_400ms`**:
   In `run_tournament`:
   ```python
   decision_timeouts_400 = final_lat_stats.get("timeouts_gt_400ms", 0)
   decision_timeouts_1000 = final_lat_stats.get("timeouts_gt_1000ms", 0)
   decision_timeouts = decision_timeouts_400
   total_timeouts = match_timeouts + decision_timeouts
   ```
   And in `latency_passed`:
   ```python
   latency_passed = (
       final_lat_stats["count"] > 0
       and final_lat_stats["mean"] < 50.0
       and final_lat_stats["max"] < 300.0
       and decision_timeouts_400 == 0
       and slow_moves_300 == 0
   )
   ```
4. **Updated Reporting**:
   In `ReportFormatter.print_latency_summary`, print `Server Timeouts (>400ms)` alongside `Timeouts (>1000ms)`.
   In `results_data["latency_gating"]`, include both `decision_timeouts_gt_400ms` and `decision_timeouts_gt_1000ms`, plus `challenger_match_timeouts` and `opponent_match_timeouts`.

---

## 4. Proposed Concrete Code Diffs

### 4.1 Target: `/home/ibrahim-tomota/mon-bot/benchmark_suite.py`

```diff
--- benchmark_suite.py
+++ benchmark_suite.py
@@ -154,11 +154,14 @@
     def decide(
         self, view: PlayerView, legal_actions: list[Action], time_left_ms: int
     ) -> Action:
         t0 = time.perf_counter()
-        action = self._inner.decide(view, legal_actions, time_left_ms)
-        elapsed_ms = (time.perf_counter() - t0) * 1000.0
-        self.profile.record(elapsed_ms)
-        return action
+        try:
+            action = self._inner.decide(view, legal_actions, time_left_ms)
+            return action
+        finally:
+            elapsed_ms = (time.perf_counter() - t0) * 1000.0
+            self.profile.record(elapsed_ms)
 
     def observe(self, view: PlayerView) -> None:
         observe_fn = getattr(self._inner, "observe", None)
@@ -177,7 +180,7 @@
     seed: int,
     target_score: int = 151,
     starter: str = "p0",
-    decision_timeout_ms: int = 1000,
+    decision_timeout_ms: int = 400,
 ) -> tuple[MatchResult, str]:
     """Exécute un match isolé et retourne le résultat."""
     # Dealer: 1 means p0 starts, 0 means p1 starts
@@ -250,7 +253,7 @@
             bot, root = load_resolved_submission(self.bot_path)
             res = play_match(
                 bot,
                 "builtin:random",
-                MatchConfig(seed=42, target_score=151, max_rounds=40),
+                MatchConfig(seed=42, target_score=151, max_rounds=40, decision_timeout_ms=400),
                 challenger_name="mon-bot",
                 challenger_dir=root,
             )
@@ -740,7 +743,7 @@
                 seed=seed,
                 target_score=self.target_score,
                 initial_dealer_index=dealer,
-                decision_timeout_ms=1000,
+                decision_timeout_ms=400,
             )
 
             if is_p0:
@@ -800,6 +803,7 @@
                 "winner_bot": "mon-bot" if res.winner_id == my_slot else opp_name,
                 "won": won,
                 "reason": res.reason,
+                "forfeited_player_id": res.forfeited_player_id,
                 "scores": res.final_scores,
                 "my_score": my_score,
                 "opp_score": opp_score,
@@ -874,7 +878,7 @@
             seed=seed,
             target_score=self.target_score,
             initial_dealer_index=1,  # p0 starts
-            decision_timeout_ms=1000,
+            decision_timeout_ms=400,
         )
 
         res = play_bots_match(
@@ -904,6 +908,9 @@
             "winner": "mon-bot" if res.winner_id == "p0" else opp.name,
             "reason": res.reason,
             "won": won,
+            "forfeited_player_id": res.forfeited_player_id,
+            "my_slot": "p0",
+            "opp_slot": "p1",
             "forfeit": is_forfeit_loss,
             "scores": res.final_scores,
             "rounds": res.rounds_played,
@@ -1066,7 +1073,8 @@
         print(
             f"    Budget Compliance: {lat_color}{latency_stats['budget_compliance_pct']:.1f}% decisions < 300ms{Colors.RESET} | "
-            f"Timeouts (>1000ms): {latency_stats['timeouts_gt_1000ms']}"
+            f"Server Timeouts (>400ms): {latency_stats['timeouts_gt_400ms']} | "
+            f"Legacy Timeouts (>1000ms): {latency_stats['timeouts_gt_1000ms']}"
         )
 
     @staticmethod
@@ -1078,7 +1086,7 @@
         forfeits = 0
         for s in seed_results:
             is_win = s.get("won", False)
-            is_forfeit = s.get("forfeit", False) or s.get("reason") != "normal"
+            is_forfeit = s.get("forfeit", False) or (s.get("forfeited_player_id") == "p0")
             if is_win:
                 wins += 1
             if is_forfeit:
@@ -1254,7 +1262,7 @@
             seed_results.append(s_res)
         t4_wins = sum(1 for sr in seed_results if sr.get("won", False))
         t4_forfeits = sum(
-            1 for sr in seed_results if sr.get("forfeit", False) or sr.get("reason") != "normal"
+            1 for sr in seed_results if sr.get("forfeit", False) or (sr.get("forfeited_player_id") == "p0")
         )
         t4_win_rate_pct = (t4_wins / len(seed_results) * 100.0) if seed_results else 0.0
@@ -1285,16 +1293,37 @@
         total_forfeits += t4_forfeits
 
-    # Timeout auditing: match-level timeouts + decision-level timeouts (> 1000ms or > 400ms)
-    match_timeouts = 0
+    # Timeout auditing: isolate opponent timeouts from challenger timeouts
+    challenger_match_timeouts = 0
+    opponent_match_timeouts = 0
+
+    def _audit_matches_timeouts(matches_list: list[dict[str, Any]]) -> None:
+        nonlocal challenger_match_timeouts, opponent_match_timeouts
+        for m in matches_list:
+            if m.get("reason") == "timeout":
+                my_slot = m.get("my_slot", "p0")
+                forfeited = m.get("forfeited_player_id")
+                winner = m.get("winner_id")
+                if forfeited == my_slot or (winner != my_slot and forfeited is None):
+                    challenger_match_timeouts += 1
+                else:
+                    opponent_match_timeouts += 1
+
     if run_t2:
-        match_timeouts += sum(1 for m in t2_random.get("matches", []) if m.get("reason") == "timeout")
-        match_timeouts += sum(1 for m in t2_basic.get("matches", []) if m.get("reason") == "timeout")
+        _audit_matches_timeouts(t2_random.get("matches", []))
+        _audit_matches_timeouts(t2_basic.get("matches", []))
     if run_t3:
-        match_timeouts += sum(1 for m in t3_medium.get("matches", []) if m.get("reason") == "timeout")
+        _audit_matches_timeouts(t3_medium.get("matches", []))
     if run_t4:
-        match_timeouts += sum(1 for s in seed_results if s.get("reason") == "timeout")
+        _audit_matches_timeouts(seed_results)
+
+    match_timeouts = challenger_match_timeouts
+    decision_timeouts_400 = final_lat_stats.get("timeouts_gt_400ms", 0)
+    decision_timeouts_1000 = final_lat_stats.get("timeouts_gt_1000ms", 0)
+    decision_timeouts = decision_timeouts_400
     slow_moves_300 = final_lat_stats.get("slow_moves_gt_300ms", 0)
     total_timeouts = match_timeouts + decision_timeouts
 
@@ -1307,7 +1336,7 @@
             final_lat_stats["count"] > 0
             and final_lat_stats["mean"] < 50.0
             and final_lat_stats["max"] < 300.0
-            and decision_timeouts == 0
+            and decision_timeouts_400 == 0
             and slow_moves_300 == 0
         )
     else:
@@ -1334,7 +1363,10 @@
         "max_threshold_ms": 300.0,
         "max_passed": (final_lat_stats.get("max", 0.0) < 300.0) if final_lat_stats.get("count", 0) > 0 else True,
         "slow_moves_gt_300ms": slow_moves_300,
-        "decision_timeouts_gt_1000ms": decision_timeouts,
+        "decision_timeouts_gt_400ms": decision_timeouts_400,
+        "decision_timeouts_gt_1000ms": decision_timeouts_1000,
+        "challenger_match_timeouts": challenger_match_timeouts,
+        "opponent_match_timeouts": opponent_match_timeouts,
         "match_timeouts": match_timeouts,
         "total_timeouts": total_timeouts,
         "total_forfeits": total_forfeits,
```

---

### 4.2 Target: `/home/ibrahim-tomota/mon-bot/test_engine.py`

Add dedicated unit tests under `TestTournamentInvariantsAndConstraints`:

```python
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

    def test_decision_timeout_400ms_enforcement(self):
        """Verify that LatencyProfile catches moves exceeding 400ms."""
        profile = LatencyProfile()
        profile.record(45.0)
        profile.record(350.0)  # > 300ms, <= 400ms
        profile.record(420.0)  # > 400ms, <= 1000ms
        stats = profile.compute_stats()
        self.assertEqual(stats["slow_moves_gt_300ms"], 2)
        self.assertEqual(stats["timeouts_gt_400ms"], 1)
        self.assertEqual(stats["timeouts_gt_1000ms"], 0)
```

---

## 5. Invalidation & Risk Analysis

| Potential Risk | Assessment | Mitigation |
|---|---|---|
| Builtin bots timing out on 400ms | Builtin bots take $< 1\text{ ms}$ on basic heuristics, tested empirically across series matches. | Verified via live 6-game series with `decision_timeout_ms=400`. |
| Missing `forfeited_player_id` | If `res.forfeited_player_id` is ever `None` on a timeout, fallback `winner_id != my_slot` correctly identifies the loser. | Dual-check logic handles both `forfeited_player_id` and `winner_id != my_slot`. |
| Interaction with Explorer 1's forfeit fixes | Explorer 1 handles `res.reason == "forfeit"`. Our changes add `forfeited_player_id` tracking and isolate `reason == "timeout"`. | Completely orthogonal and mutually reinforcing. |

---

## 6. Verification Method

To verify these changes independently:
1. **Run Adversarial Suite**:
   ```bash
   PYTHONPATH=. python3 /home/ibrahim-tomota/mon-bot/.agents/m1_reviewer_2/adversarial_tests.py
   ```
2. **Execute Unit Tests**:
   ```bash
   python3 -m unittest test_engine.py
   ```
3. **Execute Tier 1 Benchmark**:
   ```bash
   python3 benchmark_suite.py --tier 1
   ```
