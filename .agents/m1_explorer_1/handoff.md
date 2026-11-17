# Handoff Report: Two-Way Symmetric Tournament Pairing Implementation Strategy

**Agent**: M1 Explorer 1  
**Working Directory**: `/home/ibrahim-tomota/mon-bot/.agents/m1_explorer_1`  
**Target Milestone**: M1 (Symmetric Benchmark Suite R4)  
**Deliverable Document**: `/home/ibrahim-tomota/mon-bot/.agents/m1_explorer_1/analysis.md`  
**Date**: 2026-09-09  

---

## 1. Observation

### Obs 1: Asymmetric Slot Assignment in `BenchmarkRunner.run_series()`
In `/home/ibrahim-tomota/mon-bot/benchmark_suite.py`, lines 583–606:
```python
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
```
In `i151_engine.runner.match_runner.play_bots_match`, the first argument is unconditionally registered with player ID `"p0"` (role `"challenger"`) and the second argument with player ID `"p1"` (role `"opponent"`).
`self.instrumented_bot` is passed as argument 0 in 100% of matches. `mon-bot` is never placed into the `"p1"` slot.

### Obs 2: Hardcoded Win Detection
In `benchmark_suite.py`, lines 608–610:
```python
is_win = res.winner_id == "p0" and res.reason == "normal"
is_loss = res.winner_id == "p1" and res.reason == "normal"
is_forfeit = res.reason != "normal"
```
Win detection checks `res.winner_id == "p0"`. If `mon-bot` plays in slot `"p1"`, a victory results in `res.winner_id == "p1"`, which this code records as a loss.

### Obs 3: Dealer Alternation vs Seat Inversion
In `benchmark_suite.py`, lines 575–581:
```python
p0_starts = (
    (i % 2 == 0)
    if p0_starter_rate == 0.5
    else (i / max(1, games) < p0_starter_rate)
)
starter = "p0" if p0_starts else "p1"
dealer = 1 if p0_starts else 0
```
In `i151_engine.game.round.start_round`:
`starter = (match.dealer_index + 1) % len(players)`
- When `dealer == 1`, `(1 + 1) % 2 = 0` $\rightarrow$ seat `p0` starts.
- When `dealer == 0`, `(0 + 1) % 2 = 1` $\rightarrow$ seat `p1` starts.
This toggles who starts Round 1 between seats `p0` and `p1`, but does not swap the bots assigned to seats `p0` and `p1`.

### Obs 4: Empirical Confirmation of Role Inversion Support and Sensitivity
We executed a two-game match test against `builtin:medium` using inverted slot assignments:
- Game 1 (`mon-bot` in `p0`): `scores={'p0': 176, 'p1': 124}`, `winner_id='p1'` (Medium won).
- Game 2 (`mon-bot` in `p1`): `scores={'p0': 157, 'p1': 129}`, `winner_id='p1'` (`mon-bot` won).
In Game 2, `mon-bot` won from slot `p1`, confirming that `play_bots_match(opp.bot, self.instrumented_bot, ...)` functions cleanly, and verifying that evaluating `res.winner_id == my_slot` correctly scores `won = True`.
Furthermore, in reference seed `848914317`:
- As `p0`: `mon-bot` wins 62 vs 188.
- As `p1`: `medium_bot` wins 126 vs 159.
This demonstrates severe strategic sensitivity to player position.

### Obs 5: Tournament Regulation Updates
Official tournament regulations establish:
1. Hard server timeout: **400 ms per decision** (forfeit if exceeded). Target: 80–180 ms with 250 ms cutoff.
2. Rank 8 dumping bug: `my_score >= 80` was false agony trigger; 8s must be preserved when hand $\ge 5$.
3. Exact endgame solver condition: active only when `unrevealed_mask.bit_count() <= 6 AND bank_size == 0`.
4. R4 Acceptance Criteria: 50 symmetric matches vs `builtin:medium` (25 p0, 25 p1) with alternating dealers, win rate $\ge 70\%$.

---

## 2. Logic Chain

1. **Premise 1 (R4 Mandate)**: R4 in `ORIGINAL_REQUEST.md` and `PROJECT.md` requires: *"Benchmark the bot on symmetric two-way matches against builtin:medium (50 games total: 25 as challenger p0, 25 as opponent p1) with alternating dealers to eliminate first-player bias."*
2. **Premise 2 (Asymmetric Implementation)**: `benchmark_suite.py` unconditionally passes `self.instrumented_bot` as the challenger `p0` to `play_bots_match` and checks `res.winner_id == "p0"` (Obs 1, Obs 2).
3. **Inference 1**: The existing test suite evaluates zero matches in the `p1` slot and misclassifies any `p1` win as a defeat.
4. **Premise 3 (Mathematical Balance)**: By partitioning $N$ games into two halves (`half = games // 2 = 25`), assigning `mon-bot` as `p0` for $i < half$ and as `p1` for $i \ge half$, and setting `dealer = 1 if (sub_i % 2 == 0) else 0` in each half:
   - Half 1: 13 games with dealer=1 (mon-bot starts), 12 games with dealer=0 (opp starts).
   - Half 2: 13 games with dealer=1 (opp starts), 12 games with dealer=0 (mon-bot starts).
5. **Inference 2**: Across 50 games, `mon-bot` is challenger `p0` in exactly 25 games (50%), opponent `p1` in exactly 25 games (50%), starts round 1 in exactly 25 games (50%), and opponent starts round 1 in exactly 25 games (50%). Both seat and starting player biases are perfectly neutralized.
6. **Premise 4 (Execution Verification)**: Passing `(opp.bot, self.instrumented_bot, config, challenger_name=opp_name, opponent_name='mon-bot', opponent_id='student:mon-bot', challenger_dir=opp.submission_dir, opponent_dir=self.challenger_dir, manage_lifecycle=False)` executes cleanly and returns `winner_id="p1"` on `mon-bot` victory (Obs 4).
7. **Inference 3**: Implementing this symmetric dispatch and dynamic `res.winner_id == my_slot` evaluation fully resolves the architectural gap and prepares the benchmark for R4 verification.

---

## 3. Caveats

- **Scope Boundary**: As an Explorer agent, our actions are read-only. We did not modify `benchmark_suite.py` directly; instead, we delivered the complete line-by-line strategy in `analysis.md` for the test writer / implementer agent.
- **Server Timeout Simulation**: Local execution uses `MatchConfig(decision_timeout_ms=1000)` by default. To strictly simulate tournament server constraints, `LatencyProfile` should check for moves exceeding 400 ms (server limit) and 250 ms (engine cutoff).
- **Even vs Odd Series**: For even $N$, the starter and slot balance is 50/50. For odd $N$ (e.g. $N=5$ in `--quick`), the distribution is $2 \text{ vs } 3$, differing by at most 1 game.

---

## 4. Conclusion

1. The current `benchmark_suite.py` is structurally asymmetric and fails Acceptance Criteria R4.
2. Inverting `play_bots_match` arguments for the second half of matches with `dealer = 1 if (sub_i % 2 == 0) else 0` mathematically guarantees a 25/25 slot split and a 25/25 starter split.
3. Win detection must dynamically check `res.winner_id == my_slot` and distinguish opponent forfeits from self-forfeits.
4. A complete, drop-in replacement implementation for `BenchmarkRunner.run_series()` has been designed, verified, and documented in `/home/ibrahim-tomota/mon-bot/.agents/m1_explorer_1/analysis.md`.

---

## 5. Verification Method

To independently verify the observations and implementation strategy:

1. **Verify Role Hardcoding**:
   ```bash
   sed -n '583,612p' /home/ibrahim-tomota/mon-bot/benchmark_suite.py
   ```
   Confirms `self.instrumented_bot` is passed as first argument and `res.winner_id == "p0"`.

2. **Verify Mathematical Balance of Proposed Pairing**:
   ```bash
   python3 -c "
   n = 50
   half = n // 2
   p0, p1, m_start, o_start = 0, 0, 0, 0
   for i in range(n):
       is_p0 = i < half
       sub_i = i if is_p0 else i - half
       dealer = 1 if (sub_i % 2 == 0) else 0
       my_slot = 'p0' if is_p0 else 'p1'
       starter = 'p0' if dealer == 1 else 'p1'
       if is_p0: p0 += 1
       else: p1 += 1
       if starter == my_slot: m_start += 1
       else: o_start += 1
   assert (p0, p1, m_start, o_start) == (25, 25, 25, 25), 'Imbalance detected!'
   print('Symmetry assertion passed: 25/25 slots, 25/25 starters.')
   "
   ```

3. **Verify Inverted `play_bots_match` Support with `bot.py`**:
   ```bash
   python3 -c "
   from arena_sdk.opponents import resolve_opponent_arg
   from i151_engine.runner.match_runner import play_bots_match
   from arena_sdk import MatchConfig
   from pathlib import Path
   import bot
   opp = resolve_opponent_arg('medium')
   opp.bot.setup(opp.submission_dir or Path('.'))
   bot.setup(Path('.'))
   cfg = MatchConfig(seed=42, target_score=151)
   res = play_bots_match(opp.bot, bot, cfg, challenger_name=opp.name, opponent_name='mon-bot', opponent_id='student:mon-bot', challenger_dir=opp.submission_dir, opponent_dir=Path('.'), manage_lifecycle=False)
   opp.bot.teardown()
   bot.teardown()
   print('Execution Success. Winner ID:', res.winner_id, 'Scores:', res.final_scores)
   "
   ```
