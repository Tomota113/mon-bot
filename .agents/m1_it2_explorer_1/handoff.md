# Handoff Report: M1 Iteration 2 Forensic Fix Strategy

**Agent**: M1 Iteration 2 Explorer 1  
**Working Directory**: `/home/ibrahim-tomota/mon-bot/.agents/m1_it2_explorer_1`  
**Date**: 2026-09-09T14:26:44Z  
**Handoff Type**: Hard (Investigation & Strategy Complete)  
**Target Files**:
- `/home/ibrahim-tomota/mon-bot/benchmark_suite.py`
- `/home/ibrahim-tomota/mon-bot/test_engine.py`  
**Analysis Reference**: `/home/ibrahim-tomota/mon-bot/.agents/m1_it2_explorer_1/analysis.md`

---

## 1. Observation

1. **Forfeit Classification Code in `benchmark_suite.py`**:
   - At `/home/ibrahim-tomota/mon-bot/benchmark_suite.py` lines 774–788:
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
   - At `/home/ibrahim-tomota/mon-bot/benchmark_suite.py` lines 895–898:
     ```python
     is_win = res.winner_id == "p0" and res.reason == "normal"
     is_forfeit_win = res.winner_id == "p0" and res.reason in ("timeout", "illegal_action", "error")
     is_forfeit_loss = res.winner_id == "p1" and res.reason in ("timeout", "illegal_action", "error")
     won = is_win or is_forfeit_win
     ```

2. **Ground-Truth Engine Return Schema**:
   - In `/home/ibrahim-tomota/.platformio/penv/lib/python3.14/site-packages/i151_engine/runner/match_runner.py`:
     - Line 28: `reason: Literal["normal", "forfeit", "timeout", "max_steps"]`
     - Lines 208–218: Uncaught exceptions and illegal actions execute `_forfeit_result(match, opponent_id, pid, steps, "forfeit", recorder)`.
     - Lines 301–326: `_forfeit_result` defines:
       ```python
       winner = "p1" if forfeited == "p0" else "p0"
       ...
       return MatchResult(
           winner_id=winner,
           opponent_id=opponent_id,
           reason=reason,
           forfeited_player_id=forfeited,
           final_scores=scores,
           rounds_played=match.round_number,
           steps_played=steps,
           replay=replay,
       )
       ```
   - String grep across `i151_engine` and `arena_sdk` confirms:
     - `"illegal_action"`: 0 occurrences.
     - `"error"`: 0 occurrences.

3. **Verbatim Reproduction of Integrity Violation**:
   Executing the auditor's reproduction test on current `benchmark_suite.py`:
   ```bash
   python3 -c "
   from unittest.mock import MagicMock
   import benchmark_suite
   from pathlib import Path
   from arena_sdk import MatchResult

   runner = benchmark_suite.BenchmarkRunner(Path('bot.py'), profile_latency=False)
   fake_forfeit = MatchResult(winner_id='p1', opponent_id='opp', reason='forfeit', forfeited_player_id='p0', final_scores={'p0': 151, 'p1': 50}, rounds_played=1, steps_played=10)
   fake_win = MatchResult(winner_id='p0', opponent_id='opp', reason='normal', forfeited_player_id=None, final_scores={'p0': 50, 'p1': 151}, rounds_played=5, steps_played=100)
   call_idx = 0
   def mock_match(*args, **kwargs):
       global call_idx
       r = [fake_win, fake_forfeit][call_idx % 2]
       call_idx += 1
       return r
   benchmark_suite.play_bots_match = mock_match
   res = runner.run_series('medium', games=2, symmetric=False)
   print('Wins:', res['wins'], 'Losses:', res['losses'], 'Draws:', res['draws'], 'Forfeits:', res['forfeits'], 'Win rate:', res['win_rate_pct'])
   assert res['forfeits'] == 1, 'INTEGRITY FLAW: Forfeit was not recorded!'
   "
   ```
   Verbatim output:
   ```
   Wins: 1 Losses: 0 Draws: 1 Forfeits: 0 Win rate: 100.0
   Traceback (most recent call last):
     File "<string>", line 19, in <module>
       assert res['forfeits'] == 1, 'INTEGRITY FLAW: Forfeit was not recorded!'
              ^^^^^^^^^^^^^^^^^^^^
   AssertionError: INTEGRITY FLAW: Forfeit was not recorded!
   ```

4. **Win Rate Denominator Flaw**:
   - In `benchmark_suite.py` lines 826–829:
     ```python
     total_decided = wins + losses
     win_rate = (
         (wins / total_decided) if total_decided > 0 else (1.0 if wins > 0 else 0.0)
     )
     ```
   - When a forfeit or drawn game occurs, it is excluded from `total_decided`, artificially elevating the win rate.

5. **Opponent Timeout & Seed Accounting Flaws**:
   - In `benchmark_suite.py` lines 1288–1300:
     `match_timeouts` counts all matches where `reason == "timeout"` unconditionally. If an opponent bot times out, `total_timeouts` increments to 1, causing `total_timeouts == 0` to fail and aborting the entire benchmark run.
   - In lines 1256–1257:
     `t4_forfeits = sum(1 for sr in seed_results if sr.get("forfeit", False) or sr.get("reason") != "normal")`.
     An opponent forfeit in a seed match causes `sr.get("reason") != "normal"` to be True, falsely incrementing challenger forfeits.

6. **Flaws in `test_engine.py`**:
   - Line 67 contains a tautology:
     `self.assertEqual(CARD_RANK_ID[i], [r for r in Rank].index(card.rank) if False else card.rank.sort_order if False else None or CARD_RANK_ID[i])`.
     Testing `RANK_TO_ID[card.rank]` confirms it matches `CARD_RANK_ID[i]` for all 32 cards.
   - Lines 296–321 (`test_two_way_symmetric_pairing_math`): A self-certifying loop that does not test production code.

---

## 2. Logic Chain

1. **Premise**: Per `ORIGINAL_REQUEST.md` (R4 & Acceptance Criteria), the benchmark harness must strictly enforce 0 forfeits, 0 timeouts, and 0 illegal moves, and must never mask forfeits as draws or inflate win rates.
2. **From Observation 2**: In `i151_engine`, any unhandled exception or illegal action sets `reason = "forfeit"` and `forfeited_player_id = pid`.
3. **From Observation 1 & 3**: In `benchmark_suite.py`, forfeit classification requires `res.reason in ("timeout", "illegal_action", "error")`. Because `"forfeit"` is omitted, when a bot forfeits due to an illegal move or exception, `is_forfeit_loss` evaluates to `False`.
4. **From Observation 1 & 3**: The forfeited match falls into `else: draws += 1`. Consequently, `forfeits` remains 0, and `losses` remains 0.
5. **From Observation 4**: Because `win_rate` is computed as `wins / (wins + losses)`, the draw/forfeit is excluded from the denominator. A bot that wins 1 match and forfeits 1 match receives `100.0% WR | Forfeits: 0`, completely bypassing Tier 2 and Tier 3 gates.
6. **From Observation 5**: Because `match_timeouts` and `t4_forfeits` fail to filter by `winner_id` / `forfeited_player_id`, opponent forfeits/timeouts erroneously penalize the challenger bot.
7. **Resolution**:
   - Redefine forfeit detection: Any `res.reason != "normal"` where `res.winner_id == opp_slot or res.forfeited_player_id == my_slot` is a forfeit loss (`losses += 1`, `forfeits += 1`).
   - Any `res.reason != "normal"` where `res.winner_id == my_slot or res.forfeited_player_id == opp_slot` is a forfeit win (`wins += 1`).
   - Redefine win rate: `win_rate = (wins / total_matches)` where `total_matches = len(match_details)`.
   - Update timeout and seed audit filters to count only challenger infractions (`is_forfeit_loss == True`).

---

## 3. Caveats

- **Scope Boundary**: This analysis is strictly read-only. No source code modifications were made during this investigation. Implementation must be carried out by `m1_worker_1`.
- **Bot Behavior Unchanged**: `bot.py` currently plays legally in clean smoke tests, but the benchmark suite was defective as an acceptance harness. Correcting the benchmark ensures all subsequent milestones (M2–M5) are evaluated under authentic, uncompromising conditions.

---

## 4. Conclusion

The Forensic Auditor's verdict of **INTEGRITY VIOLATION** is 100% verified and reproducible. The remediation is clear, precise, and fully specified:

1. **`benchmark_suite.py` lines 774–788**:
   ```python
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
   ```
2. **`benchmark_suite.py` lines 826–829**:
   ```python
   total_matches = len(match_details)
   win_rate = (wins / total_matches) if total_matches > 0 else 0.0
   ```
3. **`benchmark_suite.py` lines 895–898**:
   ```python
   is_win = res.winner_id == "p0" and res.reason == "normal"
   is_forfeit_win = (
       res.winner_id == "p0" or res.forfeited_player_id == "p1"
   ) and (res.reason != "normal")
   is_forfeit_loss = (
       res.winner_id == "p1" or res.forfeited_player_id == "p0"
   ) and (res.reason != "normal")
   won = is_win or is_forfeit_win
   ```
4. **`benchmark_suite.py` lines 1256–1258 and 1288–1300**:
   - `t4_forfeits = sum(1 for sr in seed_results if sr.get("forfeit", False))`
   - `match_timeouts` counts only where `m.get("is_forfeit_loss", False)` is True.
   - `decision_timeouts = final_lat_stats.get("timeouts_gt_400ms", 0)`.
5. **`test_engine.py`**:
   - Line 67: `self.assertEqual(CARD_RANK_ID[i], RANK_TO_ID[card.rank])`.
   - Lines 296–321: Test `benchmark_suite.compute_symmetric_slot` directly.
   - Add unit test `test_benchmark_forfeit_accounting` verifying `reason="forfeit"` records 1 forfeit, 1 loss, and 50.0% WR in a 2-game series.

---

## 5. Verification Method

To independently verify the fix once implemented by the worker:

1. **Verify Forfeit Accounting via Mock Test**:
   ```bash
   python3 -c "
   from unittest.mock import MagicMock
   import benchmark_suite
   from pathlib import Path
   from arena_sdk import MatchResult

   runner = benchmark_suite.BenchmarkRunner(Path('bot.py'), profile_latency=False)
   fake_forfeit = MatchResult(winner_id='p1', opponent_id='opp', reason='forfeit', forfeited_player_id='p0', final_scores={'p0': 151, 'p1': 50}, rounds_played=1, steps_played=10)
   fake_win = MatchResult(winner_id='p0', opponent_id='opp', reason='normal', forfeited_player_id=None, final_scores={'p0': 50, 'p1': 151}, rounds_played=5, steps_played=100)
   call_idx = 0
   def mock_match(*args, **kwargs):
       global call_idx
       r = [fake_win, fake_forfeit][call_idx % 2]
       call_idx += 1
       return r
   benchmark_suite.play_bots_match = mock_match
   res = runner.run_series('medium', games=2, symmetric=False)
   print('Wins:', res['wins'], 'Losses:', res['losses'], 'Draws:', res['draws'], 'Forfeits:', res['forfeits'], 'Win rate:', res['win_rate_pct'])
   assert res['forfeits'] == 1, 'Forfeit not recorded!'
   assert res['losses'] == 1, 'Loss not recorded!'
   assert res['wins'] == 1, 'Win not recorded!'
   assert res['win_rate_pct'] == 50.0, f'Expected 50.0 WR, got {res[\"win_rate_pct\"]}'
   print('PASS: Forfeits and Win Rate correctly recorded!')
   "
   ```
   *Expected result*: `PASS: Forfeits and Win Rate correctly recorded!`

2. **Run Full Test Suite**:
   ```bash
   python3 -m unittest test_engine.py
   python3 benchmark_suite.py --tier 1
   ```
   *Expected result*: All unit tests pass; Tier 1 passes 5/5 checks.
