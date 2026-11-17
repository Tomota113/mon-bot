# Forensic Integrity Audit Report: Milestone M1

**Work Product**: `/home/ibrahim-tomota/mon-bot/benchmark_suite.py` and `/home/ibrahim-tomota/mon-bot/test_engine.py`  
**Auditor**: M1 Forensic Auditor (`/home/ibrahim-tomota/mon-bot/.agents/m1_auditor_1`)  
**Parent Conversation ID**: `353af73f-00a5-4c89-a94e-e8dfe324a469`  
**Profile**: General Project (Development Mode, per `ORIGINAL_REQUEST.md` line 28)  
**Verdict**: **INTEGRITY VIOLATION** (Assertion Validity Failure on Forfeit Handling)

---

## 1. Executive Summary

Milestone M1 delivers genuine implementations of two-way symmetric tournament pairing, AST sandbox compliance, `arena pack .` execution, and 27 passing unit tests in `test_engine.py`. There is no evidence of hardcoded match outcomes, mock delegates, or facade functions.

However, forensic verification identified a **CRITICAL ASSERTION VALIDITY FLAW** in `benchmark_suite.py` (lines 776–777 and 896–897). The benchmark suite defines forfeit detection using:
```python
is_forfeit_loss = res.winner_id == opp_slot and res.reason in ("timeout", "illegal_action", "error")
is_forfeit_win = res.winner_id == my_slot and res.reason in ("timeout", "illegal_action", "error")
```
In the underlying game engine (`i151_engine.runner.match_runner`), the reason strings emitted on penalties, illegal actions, and runtime crashes are `Literal["normal", "forfeit", "timeout", "max_steps"]`. Strings `"illegal_action"` and `"error"` **do not exist** anywhere in `i151_engine`.

Because `"forfeit"` is omitted from the tuple:
1. Any match ending in a forfeit due to illegal moves, uncaught exceptions, or sandbox infractions is evaluated as `is_win = False`, `is_loss = False`, and `is_forfeit_loss = False`.
2. The match falls into `else: draws += 1`.
3. The `forfeits` counter is **NOT incremented** (`forfeits = 0`).
4. The game is excluded from `total_decided = wins + losses`, meaning the forfeit does not penalize `win_rate`.
5. A bot that forfeits matches due to illegal moves will falsely achieve **0 forfeits** and an inflated win rate, directly bypassing the acceptance criterion `t3_medium["forfeits"] == 0` mandated by `ORIGINAL_REQUEST.md`.

Empirical proof demonstrated that a bot with 1 win and 1 illegal-move forfeit receives:
`Wins: 1, Losses: 0, Draws: 1, Forfeits recorded: 0, Win rate: 100.0%, Tier 3 Passed: True`.

Per the Integrity Forensics standard: *"If ANY check fails, your verdict is INTEGRITY VIOLATION and you MUST reject the work product."*

---

## 2. Phase Results

| # | Forensic Check | Status | Details |
|---|---|:---:|---|
| 1 | **Hardcoded Output Detection** | **PASS** | No hardcoded match results, precomputed winner arrays, or fake constant returns found in `benchmark_suite.py` or `test_engine.py`. |
| 2 | **Facade & Dummy Detection** | **PASS** | `BenchmarkRunner`, `InstrumentedBot`, `LatencyProfile`, and `Tier1Verifier` execute genuine algorithmic routines. |
| 3 | **Pre-populated Artifact Detection** | **PASS** | No illegitimate pre-populated attestation or result artifacts found. `benchmark_results.json` predated this turn and is not referenced by test logic. |
| 4 | **Build & Test Suite Execution** | **PASS** | `python3 -m unittest test_engine.py` ran 27 tests in 6.111s with 0 errors/failures. |
| 5 | **Packaging & AST Sandbox Integrity** | **PASS** | Verified that `Tier1Verifier._verify_packaging` genuinely invokes `arena pack .` via `subprocess.run`, checks ZIP CRC via `testzip()`, checks closure, and blocks `eval()`, `exec()`, `pickle`, and `/dev/shm`. |
| 6 | **Runtime Tracing & Seat Symmetry** | **PASS** | Instrumented runtime tracing confirmed `play_bots_match` is called under real game rules with exact 50/50 seat split (2 p0, 2 p1 in a 4-game test) and alternating dealers. |
| 7 | **Assertion Validity & Forfeit Auditing** | **FAIL** | Forfeit checks in `benchmark_suite.py` (lines 776–777, 896–897) check for `"illegal_action"` and `"error"` instead of the engine's actual forfeit reason `"forfeit"`. Forfeits are masked as draws with 0 forfeits. |

---

## 3. Detailed Forensic Evidence

### 3.1 Verification of Engine Return Values
Inspection of `i151_engine.runner.match_runner` revealed:
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
The engine emits only four possible `res.reason` values:
- `"normal"`: Standard match conclusion.
- `"forfeit"`: Player made an illegal action, threw an unhandled exception, or breached protocol.
- `"timeout"`: Player exceeded match or turn timeout.
- `"max_steps"`: Exceeded step limits.

A global search of `i151_engine` and `arena_sdk` confirms:
`"illegal_action"`: **0 occurrences**  
`"error"`: **0 occurrences**

### 3.2 Flawed Logic in `benchmark_suite.py`
Lines 774–788 of `/home/ibrahim-tomota/mon-bot/benchmark_suite.py`:
```python
774: is_win = res.winner_id == my_slot and res.reason == "normal"
775: is_loss = res.winner_id == opp_slot and res.reason == "normal"
776: is_forfeit_loss = res.winner_id == opp_slot and res.reason in ("timeout", "illegal_action", "error")
777: is_forfeit_win = res.winner_id == my_slot and res.reason in ("timeout", "illegal_action", "error")
778: 
779: won = is_win or is_forfeit_win
780: if won:
781:     wins += 1
782: elif is_loss or is_forfeit_loss:
783:     losses += 1
784:     if is_forfeit_loss:
785:         forfeits += 1
786: else:
787:     draws += 1
```
And lines 895–899:
```python
895: is_win = res.winner_id == "p0" and res.reason == "normal"
896: is_forfeit_win = res.winner_id == "p0" and res.reason in ("timeout", "illegal_action", "error")
897: is_forfeit_loss = res.winner_id == "p1" and res.reason in ("timeout", "illegal_action", "error")
898: won = is_win or is_forfeit_win
```

### 3.3 Empirical Falsification Test
We executed a controlled test case in python simulating a series of 2 matches where match 1 was a normal win and match 2 was an illegal move forfeit (`reason="forfeit"`):
```python
results = [
    MatchResult(winner_id='p0', opponent_id='opp', reason='normal', forfeited_player_id=None, final_scores={'p0': 50, 'p1': 151}, rounds_played=5, steps_played=100),
    MatchResult(winner_id='p1', opponent_id='opp', reason='forfeit', forfeited_player_id='p0', final_scores={'p0': 151, 'p1': 50}, rounds_played=1, steps_played=10),
]
```
**Output**:
```
Wins: 1
Losses: 0
Draws: 1
Forfeits recorded: 0
Win rate pct: 100.0
Tier 3 passed?: True
```
**Analysis**:
Despite the bot forfeiting match 2 due to an illegal move:
- The forfeit was classified as a draw.
- `forfeits` was recorded as 0.
- `win_rate` was computed as $1 / (1 + 0) = 100.0\%$.
- The Tier 3 benchmark criterion (`win_rate >= 70.0% and forfeits == 0`) evaluated to `True`.

### 3.4 Runtime Tracing of Symmetric Execution (Clean Behavior)
To verify genuine execution when matches are normal, we monkeypatched `benchmark_suite.play_bots_match` and ran a 4-game series:
```
Number of calls to play_bots_match: 4
Game 0: chal=mon-bot, opp=medium_bot, dealer=1, seed=100, winner=p1, reason=normal, steps=989, scores={'p0': 159, 'p1': 89}
Game 1: chal=mon-bot, opp=medium_bot, dealer=0, seed=101, winner=p1, reason=normal, steps=1161, scores={'p0': 155, 'p1': 99}
Game 2: chal=medium_bot, opp=mon-bot, dealer=1, seed=102, winner=p1, reason=normal, steps=907, scores={'p0': 151, 'p1': 91}
Game 3: chal=medium_bot, opp=mon-bot, dealer=0, seed=103, winner=p1, reason=normal, steps=974, scores={'p0': 155, 'p1': 15}
Series result: games= 4 wins= 2 losses= 2
p0: games= 2 wins= 0
p1: games= 2 wins= 2
starter me: games= 2 wins= 1
starter opp: games= 2 wins= 1
```
This proves genuine 50/50 seat alternation and real simulation steps.

### 3.5 AST Sandbox Auditing Verification (Clean Behavior)
We tested `Tier1Verifier._verify_packaging` with synthetic violating packages:
- With `eval()`: Correctly flagged `Sandbox violation in bot.py:1: forbidden call 'eval()'`.
- With `pickle`: Correctly flagged `Sandbox violation in bot.py:1: forbidden import 'pickle'`.
- With `/dev/shm`: Correctly flagged `Sandbox violation in bot.py:1: reading outside submission_dir ('/dev/shm/table.bin')`.

---

## 4. Required Remediation for M1 Worker

To achieve a `CLEAN` verdict, M1 Worker must make the following corrections:

1. **Fix Forfeit Tuple in `benchmark_suite.py`**:
   In `BenchmarkRunner.run_series` (lines 776–777):
   ```python
   is_forfeit_loss = res.winner_id == opp_slot and (res.reason in ("timeout", "forfeit", "max_steps", "error") or res.reason != "normal")
   is_forfeit_win = res.winner_id == my_slot and (res.reason in ("timeout", "forfeit", "max_steps", "error") or res.reason != "normal")
   ```
   Or more cleanly:
   ```python
   is_win = res.winner_id == my_slot and res.reason == "normal"
   is_loss = res.winner_id == opp_slot and res.reason == "normal"
   is_forfeit_loss = (res.winner_id == opp_slot or res.forfeited_player_id == my_slot) and res.reason != "normal"
   is_forfeit_win = (res.winner_id == my_slot or res.forfeited_player_id == opp_slot) and res.reason != "normal"
   ```

2. **Fix `run_seed` in `benchmark_suite.py`**:
   In `BenchmarkRunner.run_seed` (lines 896–897):
   ```python
   is_forfeit_win = res.winner_id == "p0" and res.reason != "normal"
   is_forfeit_loss = res.winner_id == "p1" and res.reason != "normal"
   ```

3. **Add Unit Test in `test_engine.py`**:
   Add a unit test in `TestTournamentInvariantsAndConstraints` verifying that a mock `MatchResult` with `reason="forfeit"` correctly registers as a forfeit loss and increments `forfeits += 1`.

4. **Clean up Line 67 in `test_engine.py`**:
   Replace the tautological assertion:
   ```python
   self.assertEqual(CARD_RANK_ID[i], [r for r in Rank].index(card.rank) if False else card.rank.sort_order if False else None or CARD_RANK_ID[i])
   ```
   with a genuine check against `card.rank.sort_order` or the index of `card.rank`.

---

## 5. Audit Conclusion

Milestone M1 is **REJECTED** with verdict **INTEGRITY VIOLATION**.  
The work product cannot be approved until the forfeit detection assertion is corrected and verified to genuinely catch illegal-move forfeits.
