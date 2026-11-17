# Root Cause Analysis & Exact Fix Strategy: Forfeit Detection & Suite Integrity (M1 Iteration 2)

**Author**: M1 Iteration 2 Explorer 1  
**Date**: 2026-09-09T14:26:44Z  
**Target Files**:
- `/home/ibrahim-tomota/mon-bot/benchmark_suite.py`
- `/home/ibrahim-tomota/mon-bot/test_engine.py`  
**Reference Evidence**:
- Forensic Auditor Report (`.agents/m1_auditor_1/handoff.md`, `.agents/m1_auditor_1/audit_report.md`)
- Quality Review Reports (`.agents/m1_reviewer_1/handoff.md`, `.agents/m1_reviewer_2/handoff.md`)
- Tournament Ground Truth (`/home/ibrahim-tomota/.platformio/penv/lib/python3.14/site-packages/i151_engine/runner/match_runner.py`)

---

## 1. Executive Summary

During the initial M1 Milestone verification, the Forensic Auditor issued a verdict of **INTEGRITY VIOLATION** due to a critical assertion flaw in `benchmark_suite.py`. Specifically, lines 776–777 and 896–897 checked for `reason in ("timeout", "illegal_action", "error")`. However, the underlying game engine (`i151_engine.runner.match_runner`) never emits `"illegal_action"` or `"error"`; all unhandled exceptions, illegal actions, and rule breaches produce `reason = "forfeit"`.

Because `"forfeit"` and `"max_steps"` were omitted:
1. Any forfeit committed by a bot fell into `else: draws += 1`.
2. The `forfeits` counter was not incremented (`forfeits = 0`).
3. `win_rate` was calculated as `wins / (wins + losses)` (excluding draws), enabling a crashing or rule-violating bot to achieve 100.0% reported win rate and 0 forfeits, completely bypassing the acceptance criterion `t3_medium["forfeits"] == 0`.
4. Reviewers also identified secondary vulnerabilities: opponent timeouts penalizing the challenger in `total_timeouts`, `t4_forfeits` counting opponent forfeits, latency gating querying `timeouts_gt_1000ms` instead of the 400ms server limit, and a self-certifying loop test and tautological assertion in `test_engine.py`.

This document formulates the definitive, mathematically verified remediation strategy for M1 Worker to implement in Iteration 2.

---

## 2. Root Cause Analysis & Engine Mechanics

### 2.1 Engine Ground-Truth Contract
Inspection of `i151_engine/runner/match_runner.py` reveals the exact data contract for match outcomes:
```python
@dataclass(frozen=True)
class MatchResult:
    winner_id: str | None
    opponent_id: str
    reason: Literal["normal", "forfeit", "timeout", "max_steps"]
    forfeited_player_id: str | None
    final_scores: dict[str, int]
    rounds_played: int
    steps_played: int
    replay: ReplayLog | None = None
```
In `_run_match`:
- When a decision times out: `_forfeit_result(..., reason="timeout")`
- When an uncaught exception is thrown: `_forfeit_result(..., reason="forfeit")`
- When an action is not in `legal_actions`: `_forfeit_result(..., reason="forfeit")`
- When step limit is reached: `_forfeit_result(..., reason="max_steps")`
- In all forfeit situations, `winner_id` is set to the non-forfeited player, and `forfeited_player_id` is set to the offending player (`"p0"` or `"p1"`).
- Normal match completion produces `reason = "normal"` and `forfeited_player_id = None`.

Global ripgrep across `i151_engine` confirms:
- `"illegal_action"`: 0 matches.
- `"error"`: 0 matches.

### 2.2 Flawed Logic in `benchmark_suite.py`
In `BenchmarkRunner.run_series` (lines 774–788):
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
When `res.reason == "forfeit"`:
- `is_win = False`, `is_loss = False`
- `is_forfeit_loss = False` (since `"forfeit"` not in tuple)
- `is_forfeit_win = False`
- Falls to `else: draws += 1`
- `forfeits` remains `0`, `losses` remains `0`.

### 2.3 Flawed Win Rate Denominator
In lines 826–829:
```python
total_decided = wins + losses
win_rate = (
    (wins / total_decided) if total_decided > 0 else (1.0 if wins > 0 else 0.0)
)
```
Even ignoring the forfeit bug, excluding draws from the denominator distorts the true tournament performance. A series with 35 wins, 10 losses, and 5 draws would report $35 / 45 = 77.8\%$ instead of $35 / 50 = 70.0\%$. In i151 tournament play, win rate is the percentage of total played matches won: `wins / total_matches`.

### 2.4 Opponent Timeout Penalizing Challenger
In lines 1288–1300:
`match_timeouts` counts all matches where `reason == "timeout"`. If the opponent bot times out, `mon-bot` legitimately won, yet `match_timeouts` increments to 1, causing `total_timeouts == 0` to evaluate to `False` and failing the benchmark.
Similarly, in line 1256–1257:
`t4_forfeits = sum(1 for sr in seed_results if sr.get("forfeit", False) or sr.get("reason") != "normal")`
If an opponent forfeits in a seed match, `sr.get("reason") != "normal"` triggers, counting against the challenger.

---

## 3. Comprehensive Fix Strategy & Code Specifications

### 3.1 Fix 1: Symmetric Forfeit & Termination Detection in `BenchmarkRunner.run_series`
**File**: `/home/ibrahim-tomota/mon-bot/benchmark_suite.py`  
**Target Lines**: 774–788

**Logic**:
- A match is normal win if `res.winner_id == my_slot and res.reason == "normal"`.
- A match is normal loss if `res.winner_id == opp_slot and res.reason == "normal"`.
- Any non-normal termination (`res.reason != "normal"`, including `"forfeit"`, `"timeout"`, `"max_steps"`):
  - If `res.winner_id == opp_slot or res.forfeited_player_id == my_slot`: forfeit loss for `my_slot`. Increments `losses` and `forfeits`.
  - If `res.winner_id == my_slot or res.forfeited_player_id == opp_slot`: forfeit win for `my_slot`. Increments `wins`.
- If neither player won normally or by forfeit (true draw or double fault): increments `draws`.

**Proposed Replacement**:
```python
<<<<
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
====
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
>>>>
```

Also record `forfeited_player_id` and `is_forfeit_loss` in the `detail` dictionary (lines 792–808):
```python
            detail = {
                "game_index": i + 1,
                "seed": seed,
                "my_slot": my_slot,
                "opp_slot": opp_slot,
                "starter": starter_slot,
                "starter_bot": starter_bot,
                "winner_id": res.winner_id,
                "winner_bot": "mon-bot" if res.winner_id == my_slot else opp_name,
                "won": won,
                "reason": res.reason,
                "forfeited_player_id": res.forfeited_player_id,
                "is_forfeit_loss": is_forfeit_loss,
                "scores": res.final_scores,
                "my_score": my_score,
                "opp_score": opp_score,
                "rounds": res.rounds_played,
                "steps": res.steps_played,
            }
```

### 3.2 Fix 2: Win Rate Calculation Accounting for All Matches
**File**: `/home/ibrahim-tomota/mon-bot/benchmark_suite.py`  
**Target Lines**: 826–830

**Logic**:
The win rate must account for all played matches (`len(match_details)`, which equals `games` = `wins + losses + draws`).
```python
<<<<
        total_decided = wins + losses
        win_rate = (
            (wins / total_decided) if total_decided > 0 else (1.0 if wins > 0 else 0.0)
        )
====
        total_matches = len(match_details)
        win_rate = (wins / total_matches) if total_matches > 0 else 0.0
>>>>
```

### 3.3 Fix 3: Forfeit Detection in Deterministic Seed Matches (`run_seed`)
**File**: `/home/ibrahim-tomota/mon-bot/benchmark_suite.py`  
**Target Lines**: 895–907

**Proposed Replacement**:
```python
<<<<
        is_win = res.winner_id == "p0" and res.reason == "normal"
        is_forfeit_win = res.winner_id == "p0" and res.reason in ("timeout", "illegal_action", "error")
        is_forfeit_loss = res.winner_id == "p1" and res.reason in ("timeout", "illegal_action", "error")
        won = is_win or is_forfeit_win

        return {
            "seed": seed,
            "opponent": opp.name,
            "winner_id": res.winner_id,
            "winner": "mon-bot" if res.winner_id == "p0" else opp.name,
            "reason": res.reason,
            "won": won,
            "forfeit": is_forfeit_loss,
            "scores": res.final_scores,
            "rounds": res.rounds_played,
            "steps": res.steps_played,
        }
====
        is_win = res.winner_id == "p0" and res.reason == "normal"
        is_forfeit_win = (
            res.winner_id == "p0" or res.forfeited_player_id == "p1"
        ) and (res.reason != "normal")
        is_forfeit_loss = (
            res.winner_id == "p1" or res.forfeited_player_id == "p0"
        ) and (res.reason != "normal")
        won = is_win or is_forfeit_win

        return {
            "seed": seed,
            "opponent": opp.name,
            "winner_id": res.winner_id,
            "winner": "mon-bot" if res.winner_id == "p0" else opp.name,
            "reason": res.reason,
            "forfeited_player_id": res.forfeited_player_id,
            "won": won,
            "forfeit": is_forfeit_loss,
            "scores": res.final_scores,
            "rounds": res.rounds_played,
            "steps": res.steps_played,
        }
>>>>
```

### 3.4 Fix 4: Seed Forfeits and Timeout Accounting in Global Gating
**File**: `/home/ibrahim-tomota/mon-bot/benchmark_suite.py`  
**Target Lines**: 1256–1258, 1288–1300

**Changes**:
1. In Tier 4 seed evaluation (lines 1256–1258):
```python
<<<<
        t4_forfeits = sum(
            1 for sr in seed_results if sr.get("forfeit", False) or sr.get("reason") != "normal"
        )
====
        t4_forfeits = sum(1 for sr in seed_results if sr.get("forfeit", False))
>>>>
```
2. In match timeout auditing (lines 1288–1300):
Ensure opponent timeouts do NOT increment challenger `match_timeouts`:
```python
<<<<
    match_timeouts = 0
    if run_t2:
        match_timeouts += sum(1 for m in t2_random.get("matches", []) if m.get("reason") == "timeout")
        match_timeouts += sum(1 for m in t2_basic.get("matches", []) if m.get("reason") == "timeout")
    if run_t3:
        match_timeouts += sum(1 for m in t3_medium.get("matches", []) if m.get("reason") == "timeout")
    if run_t4:
        match_timeouts += sum(1 for s in seed_results if s.get("reason") == "timeout")

    decision_timeouts = final_lat_stats.get("timeouts_gt_1000ms", 0)
====
    match_timeouts = 0
    if run_t2:
        match_timeouts += sum(
            1 for m in t2_random.get("matches", [])
            if m.get("reason") == "timeout" and m.get("is_forfeit_loss", False)
        )
        match_timeouts += sum(
            1 for m in t2_basic.get("matches", [])
            if m.get("reason") == "timeout" and m.get("is_forfeit_loss", False)
        )
    if run_t3:
        match_timeouts += sum(
            1 for m in t3_medium.get("matches", [])
            if m.get("reason") == "timeout" and m.get("is_forfeit_loss", False)
        )
    if run_t4:
        match_timeouts += sum(
            1 for s in seed_results
            if s.get("reason") == "timeout" and s.get("forfeit", False)
        )

    decision_timeouts = final_lat_stats.get("timeouts_gt_400ms", 0)
>>>>
```

### 3.5 Fix 5: Refactor Pairing Helper & Clean `test_engine.py`
**File**: `/home/ibrahim-tomota/mon-bot/benchmark_suite.py`  
Extract reusable symmetric pairing math function:
```python
def compute_symmetric_slot(i: int, total_games: int) -> tuple[str, str, int, str]:
    """Computes (my_slot, opp_slot, dealer, starter_slot) for game i in a symmetric series."""
    half = total_games // 2
    is_p0 = (i < half)
    sub_i = i if is_p0 else (i - half)
    dealer = 1 if (sub_i % 2 == 0) else 0
    my_slot = "p0" if is_p0 else "p1"
    opp_slot = "p1" if is_p0 else "p0"
    starter_slot = "p0" if dealer == 1 else "p1"
    return my_slot, opp_slot, dealer, starter_slot
```
In `BenchmarkRunner.run_series` (lines 717–725), call this helper directly:
```python
        for i in range(games):
            seed = base_seed + i
            if symmetric:
                my_slot, opp_slot, dealer, starter_slot = compute_symmetric_slot(i, games)
                is_p0 = (my_slot == "p0")
            else:
                is_p0 = True
                my_slot = "p0"
                opp_slot = "p1"
                dealer = 1 if (i % 2 == 0) else 0
                starter_slot = "p0" if dealer == 1 else "p1"
```

**File**: `/home/ibrahim-tomota/mon-bot/test_engine.py`  
1. **Fix Line 67**:
Replace tautology:
```python
<<<<
            self.assertEqual(CARD_RANK_ID[i], [r for r in Rank].index(card.rank) if False else card.rank.sort_order if False else None or CARD_RANK_ID[i])
====
            self.assertEqual(CARD_RANK_ID[i], RANK_TO_ID[card.rank])
>>>>
```
*(Import `RANK_TO_ID` from `evaluator`)*

2. **Fix `test_two_way_symmetric_pairing_math` (lines 296–321)**:
Replace duplicate loop with direct calls to `benchmark_suite.compute_symmetric_slot`:
```python
    def test_two_way_symmetric_pairing_math(self):
        from benchmark_suite import compute_symmetric_slot
        n = 50
        p0_count, p1_count, mon_starts, opp_starts = 0, 0, 0, 0
        for i in range(n):
            my_slot, opp_slot, dealer, starter_slot = compute_symmetric_slot(i, n)
            if my_slot == "p0":
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

3. **Add `test_benchmark_forfeit_accounting`**:
Add to `TestTournamentInvariantsAndConstraints`:
```python
    def test_benchmark_forfeit_accounting(self):
        from unittest.mock import patch
        from arena_sdk import MatchResult
        from benchmark_suite import BenchmarkRunner

        runner = BenchmarkRunner(Path("bot.py"), profile_latency=False)
        fake_forfeit = MatchResult(
            winner_id="p1",
            opponent_id="opp",
            reason="forfeit",
            forfeited_player_id="p0",
            final_scores={"p0": 151, "p1": 50},
            rounds_played=1,
            steps_played=10,
        )
        fake_win = MatchResult(
            winner_id="p0",
            opponent_id="opp",
            reason="normal",
            forfeited_player_id=None,
            final_scores={"p0": 50, "p1": 151},
            rounds_played=5,
            steps_played=100,
        )
        call_idx = 0
        def mock_match(*args, **kwargs):
            nonlocal call_idx
            r = [fake_win, fake_forfeit][call_idx % 2]
            call_idx += 1
            return r

        with patch("benchmark_suite.play_bots_match", side_effect=mock_match):
            res = runner.run_series("medium", games=2, symmetric=False)
            self.assertEqual(res["wins"], 1)
            self.assertEqual(res["losses"], 1)
            self.assertEqual(res["draws"], 0)
            self.assertEqual(res["forfeits"], 1)
            self.assertEqual(res["win_rate_pct"], 50.0)
```

---

## 4. Edge Case Exhaustive Matrix

| Match Outcome Scenario | `res.reason` | `winner_id` | `forfeited_id` | `my_slot` | `won` | Outcome Category | `wins` Δ | `losses` Δ | `forfeits` Δ | `draws` Δ |
|---|---|---|---|---|---|---|---|---|---|---|
| **Normal Win (as p0)** | `normal` | `p0` | `None` | `p0` | `True` | Normal Win | +1 | 0 | 0 | 0 |
| **Normal Win (as p1)** | `normal` | `p1` | `None` | `p1` | `True` | Normal Win | +1 | 0 | 0 | 0 |
| **Normal Loss (as p0)** | `normal` | `p1` | `None` | `p0` | `False` | Normal Loss | 0 | +1 | 0 | 0 |
| **Normal Loss (as p1)** | `normal` | `p0` | `None` | `p1` | `False` | Normal Loss | 0 | +1 | 0 | 0 |
| **Self Illegal Move (as p0)** | `forfeit` | `p1` | `p0` | `p0` | `False` | Forfeit Loss | 0 | +1 | +1 | 0 |
| **Self Illegal Move (as p1)** | `forfeit` | `p0` | `p1` | `p1` | `False` | Forfeit Loss | 0 | +1 | +1 | 0 |
| **Opponent Illegal Move (as p0)**| `forfeit` | `p0` | `p1` | `p0` | `True` | Forfeit Win | +1 | 0 | 0 | 0 |
| **Opponent Illegal Move (as p1)**| `forfeit` | `p1` | `p0` | `p1` | `True` | Forfeit Win | +1 | 0 | 0 | 0 |
| **Self Timeout (as p0)** | `timeout` | `p1` | `p0` | `p0` | `False` | Forfeit Loss | 0 | +1 | +1 | 0 |
| **Opponent Timeout (as p1)** | `timeout` | `p1` | `p0` | `p1` | `True` | Forfeit Win | +1 | 0 | 0 | 0 |
| **Self Max Steps Exceeded** | `max_steps` | `p1` | `p0` | `p0` | `False` | Forfeit Loss | 0 | +1 | +1 | 0 |
| **Opponent Max Steps Exceeded** | `max_steps` | `p0` | `p1` | `p0` | `True` | Forfeit Win | +1 | 0 | 0 | 0 |
| **Engine Tie / Unresolved Draw** | `normal` | `None` | `None` | `p0` | `False` | Draw | 0 | 0 | 0 | +1 |

All 13 operational paths are deterministically handled without ambiguity.

---

## 5. Verification Plan for Implementer

Following implementation by `m1_worker_1`:
1. **Auditor Falsification Test**:
   Execute the auditor's mock test (1 normal win, 1 illegal move forfeit). It must output:
   `Wins: 1, Losses: 1, Draws: 0, Forfeits: 1, Win rate: 50.0%`.
2. **Reviewer 2 Adversarial Suite**:
   Run `python3 .agents/m1_reviewer_2/adversarial_tests.py` modified for the new contract. Both `test_forfeit_reason_blindspot` and `test_opponent_timeout_penalizes_challenger` must pass.
3. **Unit Tests**:
   Run `python3 -m unittest test_engine.py`. All tests (including new forfeit test) must pass with 0 errors.
4. **Smoke & Packaging**:
   Run `python3 benchmark_suite.py --tier 1`. All 5 checks must pass.
