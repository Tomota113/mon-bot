# Challenger 2 Handoff Report: Leaderboard Seeds & Stress Verification

**Date**: 2026-08-30T23:47:30Z  
**Role**: EMPIRICAL CHALLENGER (Critic & Specialist)  
**Task**: Empirically verify Leaderboard reference seeds and stress scenarios  
**Verdict**: **REQUEST_CHANGES** ⚠️

---

## 1. Observation

Direct empirical observations from executing the required verification harnesses:

1. **Benchmark Seeds Execution (`python3 benchmark_suite.py --tier seeds`)**:
   - Seed `848914317`: `mon-bot` Won vs `medium_bot` (Scores: 67/152, Rounds: 13, Steps: 490) — PASSED.
   - Seed `1477911113`: `medium_bot` Won vs `mon-bot` (Scores: 190/89, Rounds: 19, Steps: 699) — FAILED.
   - Seed `2063595735`: `medium_bot` Won vs `mon-bot` (Scores: 152/143, Rounds: 28, Steps: 1122) — FAILED.
   - Seed `329389206`: `medium_bot` Won vs `mon-bot` (Scores: 155/81, Rounds: 19, Steps: 669) — FAILED.
   - Overall Seed Win Rate: **1 / 4 (25.0%)**. Target requirement was 4 / 4 (100.0%).

2. **Self-Play Mirror Match (`arena match bot.py --vs bot.py --games 10 --format summary`)**:
   - Exit code: `0`.
   - Result: `Bilan mon-bot vs mon-bot : 8-2 (8/10 = 80%)` across 10 games in 3m55s (~23.6s/game).
   - Crashes: `0`. Unhandled exceptions: `0`. Deadlocks: `0`.

3. **Latency Profile**:
   - Min: 0.001 ms, Median: 0.010 ms, Mean: 20.415 ms, p95: 150.314 ms, Max: 152.597 ms.
   - 0 moves > 300ms, 0 timeouts > 1000ms (100% budget compliance).

4. **Unit Engine Invariants (`python3 test_engine.py`)**:
   - Ran 12 tests in 0.001s, 0 failures, 0 errors (OK).

---

## 2. Logic Chain

1. The project specification in `ORIGINAL_REQUEST.md` (§2) and `TEST_INFRA.md` (§Tier 4) explicitly establishes that the bot must win 100% of the 4 benchmark seeds against `builtin:medium` (`848914317`, `1477911113`, `2063595735`, `329389206`).
2. When executing `python3 benchmark_suite.py --tier seeds`, only seed `848914317` resulted in a victory (67 vs 152). Seeds `1477911113` (190 vs 89), `2063595735` (152 vs 143), and `329389206` (155 vs 81) were lost to `medium_bot`.
3. Code inspection of `bot.py` indicates that `evaluate_candidate` (line 301) scales the Minimax search value by only `0.05`, allowing the static heuristic `score_action` to override deeper tactical search variations.
4. Because the core requirement of 4/4 leaderboard reference seed wins is unsatisfied (1/4 = 25.0%), the release acceptance criteria are not met.

---

## 3. Caveats

- The engine demonstrated complete stability, 0 crashes, 0 memory leaks, and 100% compliance with time budget ([50ms, 300ms]).
- The mirror match completed 10/10 matches cleanly with 0 forfeits.
- Seed `2063595735` was very close (152 vs 143 over 28 rounds), indicating minor tuning to evaluation weights or Minimax blending could flip the result.

---

## 4. Conclusion

- **Verdict**: **REQUEST_CHANGES**
- **Actionable Next Steps**:
  1. Increase Minimax search influence in `bot.py:evaluate_candidate` (adjust multiplier from `0.05` to `0.25-0.50` or prioritize Minimax evaluation over static heuristic).
  2. Re-tune penalty dumping vs suit starvation trade-offs in `evaluator.py:card_context`.
  3. Re-run `python3 benchmark_suite.py --tier seeds` until all 4 seeds pass.

---

## 5. Verification Method

To independently reproduce all observations:
```bash
# 1. Run deterministic seed benchmark (Tier 4)
python3 benchmark_suite.py --tier seeds

# 2. Run self-play mirror match
arena match bot.py --vs bot.py --games 10 --format summary

# 3. Inspect generated structured benchmark report
cat .agents/challenger_2/seeds_benchmark.json
```
