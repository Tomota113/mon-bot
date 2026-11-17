# Handoff Report: M1 Forensic Integrity Audit

**Agent**: M1 Forensic Auditor  
**Working Directory**: `/home/ibrahim-tomota/mon-bot/.agents/m1_auditor_1`  
**Date**: 2026-09-09T14:26:00Z  
**Handoff Type**: Hard (Audit Complete)  
**Target Work Product**: `/home/ibrahim-tomota/mon-bot/benchmark_suite.py` and `/home/ibrahim-tomota/mon-bot/test_engine.py`  
**Verdict**: **INTEGRITY VIOLATION**  

---

## 1. Observation

1. **Forfeit Accounting Assertion in `benchmark_suite.py`**:
   - At `/home/ibrahim-tomota/mon-bot/benchmark_suite.py` lines 776–777:
     ```python
     is_forfeit_loss = res.winner_id == opp_slot and res.reason in ("timeout", "illegal_action", "error")
     is_forfeit_win = res.winner_id == my_slot and res.reason in ("timeout", "illegal_action", "error")
     ```
   - At `/home/ibrahim-tomota/mon-bot/benchmark_suite.py` lines 896–897:
     ```python
     is_forfeit_win = res.winner_id == "p0" and res.reason in ("timeout", "illegal_action", "error")
     is_forfeit_loss = res.winner_id == "p1" and res.reason in ("timeout", "illegal_action", "error")
     ```
   - Inspection of `/home/ibrahim-tomota/.platformio/penv/lib/python3.11/site-packages/i151_engine/runner/match_runner.py` reveals that the engine specifies:
     `reason: Literal["normal", "forfeit", "timeout", "max_steps"]`.
   - String search of the entire `i151_engine` and `arena_sdk` libraries confirms:
     `"illegal_action"`: 0 occurrences.
     `"error"`: 0 occurrences.
   - When a bot throws an exception or makes an illegal action, `i151_engine` sets `reason = "forfeit"`.

2. **Empirical Falsification Demonstration**:
   - Executing a simulated test where match 1 was normal (`winner_id="p0", reason="normal"`) and match 2 was an illegal-move forfeit (`winner_id="p1", reason="forfeit", forfeited_player_id="p0"`):
     ```
     Wins: 1
     Losses: 0
     Draws: 1
     Forfeits recorded: 0
     Win rate pct: 100.0
     Tier 3 passed?: True
     ```
   - Verbatim result: Despite forfeiting 50% of matches due to illegal action, the benchmark recorded 0 forfeits, 100% win rate, and passed Tier 3.

3. **Runtime Tracing of Symmetric Tournament Execution**:
   - Tracing `play_bots_match` in `BenchmarkRunner.run_series('medium', games=4, symmetric=True)` confirmed:
     - `play_bots_match` is called 4 times.
     - Game 0: mon-bot as p0, medium as p1, dealer=1 (mon-bot starts Round 1).
     - Game 1: mon-bot as p0, medium as p1, dealer=0 (medium starts Round 1).
     - Game 2: medium as p0, mon-bot as p1, dealer=1 (medium starts Round 1).
     - Game 3: medium as p0, mon-bot as p1, dealer=0 (mon-bot starts Round 1).
     - Steps played: 989, 1161, 907, 974 steps (genuine engine simulation).
     - Win detection correctly mapped `p1` wins to mon-bot when mon-bot was seated in `p1`.

4. **Packaging and AST Verification**:
   - Tracing `Tier1Verifier._verify_packaging` confirmed subprocess invocation:
     `{'cmd': ['/home/ibrahim-tomota/.platformio/penv/bin/arena', 'pack', '.'], 'cwd': PosixPath('/home/ibrahim-tomota/mon-bot')}`.
   - Synthetic testing verified AST checks correctly blocked `eval()` (`forbidden call 'eval()'`), `pickle` (`forbidden import 'pickle'`), and `/dev/shm` (`reading outside submission_dir`).

5. **Unit Test Execution**:
   - Running `python3 -m unittest test_engine.py` ran 27 tests in 6.111s with 0 failures (`OK`).
   - Line 67 in `test_engine.py` contains tautological logic:
     `self.assertEqual(CARD_RANK_ID[i], [r for r in Rank].index(card.rank) if False else card.rank.sort_order if False else None or CARD_RANK_ID[i])`.

---

## 2. Logic Chain

1. **Premise**: Per `ORIGINAL_REQUEST.md` and the Integrity Forensics standard, all verification assertions must be valid, and the suite must strictly enforce `forfeits == 0` and prevent bypasses.
2. **From Observation 1**: In `i151_engine`, forfeit outcomes on illegal moves or unhandled exceptions are designated by `reason = "forfeit"`. The strings `"illegal_action"` and `"error"` are non-existent in the engine.
3. **From Observation 1 & 2**: Because `benchmark_suite.py` checks `res.reason in ("timeout", "illegal_action", "error")`, an illegal-move forfeit evaluates to `is_forfeit_loss = False` and `is_loss = False`.
4. **From Observation 2**: The forfeit falls into `else: draws += 1`. Consequently, `forfeits` remains 0, and `total_decided = wins + losses` does not count the game. A bot that forfeits due to illegal moves achieves 100% win rate and 0 forfeits, falsely passing Tier 3.
5. **From Observation 3 & 4**: While the two-way symmetric pairing, latency profiling, and packaging verification are genuinely implemented, the flaw in forfeit assertion represents an integrity bypass.
6. **Conclusion**: Because the assertion is invalid and masks forfeits as draws, the work product fails check 7 ("Assertion Validity & Forfeit Auditing") and MUST be rejected with verdict **INTEGRITY VIOLATION**.

---

## 3. Caveats

- The worker did not intentionally engineer this bypass; rather, the worker followed an erroneous instruction provided in `m1_worker_1/DISPATCH.md` line 25. However, `ORIGINAL_REQUEST.md` takes precedence over agent dispatch instructions, and an auditor must independently verify assertions against the ground-truth engine mechanics.
- In `bot.py`'s current clean state, no illegal moves or forfeits are being committed during normal play (as shown by `arena test bot.py` and Tier 1). However, the benchmark harness itself is defective because it would fail to catch regressions in subsequent milestones.

---

## 4. Conclusion

**Verdict**: **INTEGRITY VIOLATION** (Rejected).

Milestone M1 cannot be approved in its current state. The work product must be returned to `m1_worker_1` with instructions to:
1. Fix lines 776–777 in `benchmark_suite.py` to recognize `res.reason == "forfeit"` (or `res.reason != "normal"`) as a forfeit loss.
2. Fix lines 896–897 in `benchmark_suite.py` to recognize `res.reason == "forfeit"` (or `res.reason != "normal"`).
3. Add a unit test in `test_engine.py` asserting that `reason="forfeit"` increments `forfeits` and is counted as a loss.
4. Clean up tautological assertion on line 67 of `test_engine.py`.

---

## 5. Verification Method

To independently verify the flaw:
1. Run the empirical falsification test:
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
   print('Wins:', res['wins'], 'Losses:', res['losses'], 'Draws:', res['draws'], 'Forfeits:', res['forfeits'])
   assert res['forfeits'] == 1, 'INTEGRITY FLAW: Forfeit was not recorded!'
   "
   ```
   *Expected result*: AssertionError: `INTEGRITY FLAW: Forfeit was not recorded! res['forfeits'] is 0 and res['draws'] is 1`.
