# Handoff Report: Milestone M1 Adversarial Review

**Role**: M1 Reviewer 2 (reviewer, critic)  
**Date**: 2026-09-09T14:24:30Z  
**Working Directory**: `/home/ibrahim-tomota/mon-bot/.agents/m1_reviewer_2`  
**Handoff Type**: Hard (Review Complete)  
**Verdict**: **REQUEST_CHANGES**

---

## 1. Review Summary

**Verdict**: **REQUEST_CHANGES**  
**Overall Risk Assessment**: **HIGH**

While the M1 Worker successfully implemented two-way symmetric slot allocation (25 $p_0$ / 25 $p_1$, 25 starts / 25 second for $N=50$), AST sandbox audits, and expanded `test_engine.py` from 12 to 27 passing unit tests, adversarial stress-testing identified **critical flaws in the benchmark accounting logic**:

1. **[Critical Finding] Forfeit Accounting Blindspot**: `benchmark_suite.py` checks `res.reason in ("timeout", "illegal_action", "error")` to detect forfeits. However, `i151_engine.runner.match_runner` returns `reason="forfeit"` for any illegal move, uncaught exception, or bot crash, and `reason="max_steps"` for step limit exhaustion. Because `"forfeit"` and `"max_steps"` are omitted from the tuple, **any bot forfeit is recorded as a DRAW with 0 forfeits and excluded from the win rate denominator**, allowing a crashing or rule-violating bot to falsely pass with 100% win rate and 0 reported forfeits.
2. **[Major Finding] Opponent Timeout Penalizes Challenger**: In `benchmark_suite.py` lines 1288–1300, `match_timeouts` counts every match where `m["reason"] == "timeout"`. If an opponent bot suffers a timeout (which is a legitimate forfeit win for `mon-bot`), `match_timeouts` increments to 1, causing `total_timeouts == 0` to fail and marking the entire benchmark run as `BENCHMARK_FAILED`.
3. **[Minor Finding] Decision Timeout Parameter in MatchConfig**: `benchmark_suite.py` sets `decision_timeout_ms=1000` in `MatchConfig` instead of the 400ms official tournament hard server timeout. While `slow_moves_300 == 0` prevents moves $> 300\text{ms}$ from passing when profiling is enabled, the match runner process allows up to 1000ms per decision before terminating the turn.

---

## 2. Findings

### [Critical] Finding 1: Engine Forfeits (`reason="forfeit"` / `"max_steps"`) Misclassified as Draws
- **Where**: `/home/ibrahim-tomota/mon-bot/benchmark_suite.py`, lines 774–788 (`run_series`) and lines 895–898 (`run_seed`).
- **Observation**:
  In `benchmark_suite.py`:
  ```python
  is_win = res.winner_id == my_slot and res.reason == "normal"
  is_loss = res.winner_id == opp_slot and res.reason == "normal"
  is_forfeit_loss = res.winner_id == opp_slot and res.reason in ("timeout", "illegal_action", "error")
  is_forfeit_win = res.winner_id == my_slot and res.reason in ("timeout", "illegal_action", "error")

  won = is_win or is_forfeit_win
  if won:
      wins += 1
  elif is_loss or is_forfeit_loss:
      losses += 1
      if is_forfeit_loss:
          forfeits += 1
  else:
      draws += 1
  ```
  In `i151_engine.runner.match_runner._forfeit_result`:
  ```python
  def _forfeit_result(
      match: MatchState,
      opponent_id: str,
      forfeited: str,
      steps: int,
      reason: Literal["forfeit", "max_steps", "timeout"],
      recorder: MatchRecorder,
  ) -> MatchResult:
  ```
  The engine exclusively sets `reason="forfeit"` when an exception is raised or an illegal action is returned. It never sets `reason="illegal_action"` or `"error"`.
- **Why this is a problem**:
  When `mon-bot` commits an illegal action or throws an exception:
  - `res.winner_id == opp_slot` and `res.reason == "forfeit"`.
  - `is_win` is `False`.
  - `is_loss` is `False`.
  - `is_forfeit_loss` is `False` because `"forfeit"` is NOT in `("timeout", "illegal_action", "error")`.
  - Execution drops into `else: draws += 1`.
  - `forfeits` remains `0`.
  - `losses` remains `0`.
  - `win_rate = wins / (wins + losses)` does NOT penalize the bot because draws are excluded from the denominator.
  - Acceptance criterion `forfeits == 0` is satisfied.
  - A bot with illegal actions or crashing turns can falsely score 100% win rate and 0 forfeits, evading acceptance gating.
- **Suggestion**:
  In `benchmark_suite.py` (`run_series` and `run_seed`), use the engine's explicit `res.forfeited_player_id` attribute or include `"forfeit"` and `"max_steps"`:
  ```python
  forfeit_reasons = ("timeout", "forfeit", "max_steps", "illegal_action", "error")
  forfeited_by_me = (res.forfeited_player_id == my_slot) or (res.winner_id == opp_slot and res.reason in forfeit_reasons)
  forfeited_by_opp = (res.forfeited_player_id == opp_slot) or (res.winner_id == my_slot and res.reason in forfeit_reasons)

  is_win = (res.winner_id == my_slot and res.reason == "normal") or forfeited_by_opp
  is_loss = (res.winner_id == opp_slot and res.reason == "normal") or forfeited_by_me
  is_forfeit_loss = forfeited_by_me
  is_forfeit_win = forfeited_by_opp
  ```
  And in `run_series`, store `"forfeited_player_id": res.forfeited_player_id` in `match_details`.

---

### [Major] Finding 2: Opponent Timeouts Cause Challenger To Fail
- **Where**: `/home/ibrahim-tomota/mon-bot/benchmark_suite.py`, lines 1288–1300 and line 1324.
- **Observation**:
  ```python
  match_timeouts = 0
  if run_t2:
      match_timeouts += sum(1 for m in t2_random.get("matches", []) if m.get("reason") == "timeout")
      match_timeouts += sum(1 for m in t2_basic.get("matches", []) if m.get("reason") == "timeout")
  if run_t3:
      match_timeouts += sum(1 for m in t3_medium.get("matches", []) if m.get("reason") == "timeout")
  if run_t4:
      match_timeouts += sum(1 for s in seed_results if s.get("reason") == "timeout")

  decision_timeouts = final_lat_stats.get("timeouts_gt_1000ms", 0)
  total_timeouts = match_timeouts + decision_timeouts
  ...
  overall_passed = ... and (total_timeouts == 0)
  ```
- **Why this is a problem**:
  `match_timeouts` counts ALL matches where `reason == "timeout"`, without checking who timed out. If the opponent bot (`medium_bot`, `basic_bot`, etc.) times out:
  - `mon-bot` legitimately won the game via opponent forfeit.
  - However, `match_timeouts` becomes 1.
  - `total_timeouts` becomes 1.
  - `overall_passed = ... and (total_timeouts == 0)` evaluates to `False`.
  - The entire benchmark fails due to an opponent flaw.
- **Suggestion**:
  Only count timeouts where `mon-bot` was the player that timed out:
  ```python
  match_timeouts = 0
  if run_t2:
      match_timeouts += sum(1 for m in t2_random.get("matches", []) if m.get("reason") == "timeout" and m.get("winner_id") != m.get("my_slot"))
      match_timeouts += sum(1 for m in t2_basic.get("matches", []) if m.get("reason") == "timeout" and m.get("winner_id") != m.get("my_slot"))
  if run_t3:
      match_timeouts += sum(1 for m in t3_medium.get("matches", []) if m.get("reason") == "timeout" and m.get("winner_id") != m.get("my_slot"))
  if run_t4:
      match_timeouts += sum(1 for s in seed_results if s.get("reason") == "timeout" and s.get("winner_id") != "p0")
  ```

---

### [Minor] Finding 3: `decision_timeout_ms=1000` in MatchConfig vs 400ms Server Limit
- **Where**: `/home/ibrahim-tomota/mon-bot/benchmark_suite.py`, line 743 and line 877.
- **Observation**:
  `MatchConfig` is instantiated with `decision_timeout_ms=1000`. Per `ORIGINAL_REQUEST.md`, official server hard timeout is 400ms.
- **Why this is a problem**:
  If the bot freezes or exceeds 400ms during an actual engine step, the engine runner will allow up to 1000ms before aborting. Although `slow_moves_300 == 0` catches moves $> 300\text{ms}$ in post-analysis when profiling is enabled, the match simulation environment should ideally mirror the real 400ms cutoff or track `timeouts_gt_400ms`.
- **Suggestion**:
  Update `decision_timeout_ms=400` in `MatchConfig` or explicitly assert `stats["timeouts_gt_400ms"] == 0` in `latency_passed`.

---

## 3. Verified Claims

1. **Unit Test Suite**:
   - Command: `python3 -m unittest test_engine.py`
   - Result: 27/27 tests passed in 5.046s. 15 new tests were added covering packaging, CLI, and invariant math.
2. **Tier 1 Smoke & Packaging**:
   - Command: `python3 benchmark_suite.py --tier 1`
   - Result: 5/5 checks passed (Smoke test, AST & Packaging, Anti-Queen 2P, Suit selection, Action legality).
3. **Symmetric Rotation Math**:
   - In 50 games: Exactly 25 games as $p_0$, 25 games as $p_1$, 25 games starting, and 25 games second. Dealer alternation in each half ensures perfect 50/50 balance.
4. **Odd Game Handling**:
   - Tested $N=1, 3, 5$: No index errors or division-by-zero crashes.
5. **AST Sandbox Compliance**:
   - Tested `mon-bot-submission.zip` AST for `eval`, `exec`, `pickle.load`, forbidden imports, and path leaks. All passed.
6. **No Integrity Violations in M1 Worker Code**:
   - No hardcoded match results, dummy implementations, or bypassed verification artifacts. The issues found are logic bugs in error/forfeit reason mapping.

---

## 4. Adversarial Stress Test Results

Executed reproducible test suite (`/home/ibrahim-tomota/mon-bot/.agents/m1_reviewer_2/adversarial_tests.py`):

| Challenge Scenario | Expected Behavior | Actual Behavior | Result |
|---|---|---|---|
| Bot illegal action or exception (`reason="forfeit"`) | Counted as forfeit loss; `forfeits += 1` | Counted as `draw`; `forfeits` unchanged (0) | **FAIL (Vulnerability)** |
| Opponent bot times out (`reason="timeout"`, `winner="mon-bot"`) | Registered as challenger win; `total_timeouts` unchanged (0) | `match_timeouts` increments; `total_timeouts=1`; overall benchmark fails | **FAIL (Vulnerability)** |
| Move latency exactly 50.0ms mean or 300.0ms max | Gating fails on boundary (`< 50.0`, `< 300.0`) | Gating strictly fails as expected | **PASS** |
| Match series with odd game counts ($N=1, 3, 5$) | Handled gracefully without division by zero | Handled gracefully with split reporting | **PASS** |
| Symmetric mode seat distribution ($N=50$) | Exactly 25 $p_0$, 25 $p_1$, 25 starts, 25 second | Exactly 25/25/25/25 split verified | **PASS** |

---

## 5. Coverage Gaps & Unverified Items

- **Bot Strategy (M2–M4)**: Strategic 8 preservation, Minimax depth lookahead, and Bayesian void inference are planned for upcoming milestones and were not evaluated in this M1 review.
- **No unverified items** within M1 scope.

---

## 6. Logic Chain

1. **Premise**: Milestone M1 deliverable (`benchmark_suite.py`) is the foundational verification harness that will gate all subsequent milestones (M2 through M5). If the harness cannot accurately detect forfeits or if it falsely penalizes the bot when opponents time out, acceptance decisions in subsequent milestones are compromised.
2. **Evidence**:
   - Running `adversarial_tests.py::test_forfeit_reason_blindspot` proves that `res.reason="forfeit"` results in `is_forfeit_loss=False`, incrementing `draws` and leaving `forfeits=0`.
   - Running `adversarial_tests.py::test_opponent_timeout_penalizes_challenger` proves that an opponent timeout fails `overall_passed`.
3. **Conclusion**: While all unit tests and Tier 1 pass, the benchmark harness contains two major logic errors in forfeit/timeout accounting that must be resolved before proceeding to Milestone M2.

---

## 7. Verification Method

To reproduce all findings independently:

1. **Run Adversarial Suite**:
   ```bash
   PYTHONPATH=. python3 /home/ibrahim-tomota/mon-bot/.agents/m1_reviewer_2/adversarial_tests.py
   ```
   *Expected*: Confirms forfeit misclassification as draw and opponent timeout false failure.

2. **Run Existing Test Suite**:
   ```bash
   python3 -m unittest test_engine.py
   python3 benchmark_suite.py --tier 1
   ```
   *Expected*: Both pass with exit code 0.
