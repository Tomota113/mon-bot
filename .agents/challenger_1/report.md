# Empirical Benchmark & Acceptance Verification Report

**Author**: Challenger 1 (E2E Benchmark & Acceptance Verifier)  
**Date**: 2026-08-30T23:58:00Z  
**Target Bot**: `/home/ibrahim-tomota/mon-bot/bot.py`  
**Overall Verdict**: **REQUEST_CHANGES** (Criterion 3 & Tier 4 below threshold)

---

## 1. Executive Summary

A comprehensive empirical evaluation of the i151 Grand Master Bot (`bot.py`, `card_tracker.py`, `evaluator.py`) was conducted across all required benchmark suites and CLI tools.

| # | Benchmark / Acceptance Criterion | Target Threshold | Empirical Result | Status |
|---|----------------------------------|------------------|------------------|:------:|
| 1 | **Smoke & Invariants** (`benchmark_suite.py --tier 1`) | 5/5 Checks Passed (100%) | 5/5 Checks Passed (100%) | **PASSED** |
| 2 | **Baselines vs Random** (`arena match bot.py --vs random --games 50`) | $\ge 95\%$ Win Rate, 0 Forfeits | 50-0 (100.0% WR, 0 forfeits) | **PASSED** |
| 3 | **Baselines vs Basic** (`arena match bot.py --vs basic --games 50`) | $\ge 95\%$ Win Rate, 0 Forfeits | 40-10 (80.0% WR, 0 forfeits) | **FAILED** |
| 4 | **Competitive Medium** (`benchmark_suite.py --tier medium --games 50`) | $\ge 65\text{--}75\%$ WR, Latency $\in [50, 300]\text{ms}$ | 43-7 (86.0% WR, 0 forfeits) | **PASSED** |
| 5 | **Leaderboard Reference Seeds** (`benchmark_suite.py --tier seeds`) | 4/4 Seeds Won (100%) | 2/4 Seeds Won (50.0%) | **FAILED** |
| 6 | **Packaging Compliance** (`arena pack .` & AST) | Valid `mon-bot-submission.zip` | 3 files packaged, 0 extra deps | **PASSED** |
| 7 | **Smoke CLI Test** (`arena test bot.py`) | 0 Forfeits / Timeouts | Clean match completion | **PASSED** |

---

## 2. Detailed Empirical Results

### Criterion 1: Smoke & Invariant Verification
Command: `python3 benchmark_suite.py --tier 1`
- **T1.1 Official Smoke Test**: PASSED (0 forfeits, 0 timeouts vs Random)
- **T1.2 AST & Packaging**: PASSED (Valid submission ZIP with `bot.py`, `card_tracker.py`, `evaluator.py`, whitelist-compliant)
- **T1.3 Anti-Queen 2P Invariant**: PASSED (Correctly filtered solitary Queen finish in 2P match context)
- **T1.4 Suit Selection Invariant**: PASSED (Valid `CHOOSE_SUIT` action returned)
- **T1.5 Legal Action Adherence**: PASSED (100% adherence to supplied `legal_actions`)
- **Summary**: 5/5 checks passed (100.0%).

---

### Criterion 2: Baselines vs Random Bot (50 Games)
Command: `arena match bot.py --vs random --games 50 --format summary`
- **Score**: 50 wins, 0 losses (50-0)
- **Win Rate**: **100.0%** (Requirement: $\ge 95\%$)
- **Forfeits / Timeouts**: 0
- **Assessment**: Overwhelming dominance over random baseline.

---

### Criterion 3: Baselines vs Basic Bot (50 Games)
Command: `arena match bot.py --vs basic --games 50 --format summary`
- **Score**: 40 wins, 10 losses (40-10)
- **Win Rate**: **80.0%** (Requirement: $\ge 95\%$)
- **Shortfall**: -15.0% below the required threshold.
- **Forfeits / Timeouts**: 0
- **Root-Cause Analysis**:
  - `basic_bot` implements a greedy rank-dump heuristic: it aggressively dumps high-penalty cards (8s = 32 pts, Aces = 11 pts, 10s = 10 pts) and multiple-card sets at the earliest opportunity.
  - In contrast, `mon-bot`'s tactical heuristic holds 8s in hand during early and mid-rounds for suit starvation and late-game tactical control.
  - When `basic_bot` rapidly empties its hand through aggressive multi-dumps, `mon-bot` is occasionally left holding an 8 (32 pts penalty) when the round ends, causing rapid accumulation of penalty points towards 151.
  - Mitigating this requires tuning early-game 8-holding penalties when opponent hand size drops quickly or when opponent is playing greedy dump style.

---

### Criterion 4: Competitive Medium Benchmark & Latency Profiling (50 Games)
Command: `python3 benchmark_suite.py --tier medium --games 50 --profile-latency --json-out /home/ibrahim-tomota/mon-bot/.agents/challenger_1/benchmark_medium_report.json`
- **Score**: 43 wins, 7 losses (43-7)
- **Win Rate**: **86.0%** (Requirement: $\ge 65\text{--}75\%$)
- **Forfeits / Timeouts**: 0
- **Total Decisions Instrumented**: 15,152 decisions

#### Latency Statistics Profile:
| Metric | Observed Latency | Constraint | Status |
|--------|------------------|------------|:------:|
| Minimum | 0.001 ms | $\ge 0$ ms | PASS |
| Mean | 20.035 ms | $< 300$ ms | PASS |
| Median ($p_{50}$) | 0.010 ms | $< 300$ ms | PASS |
| $p_{90}$ | 83.109 ms | $< 300$ ms | PASS |
| $p_{95}$ | 148.257 ms | $< 300$ ms | PASS |
| $p_{99}$ | 150.558 ms | $< 300$ ms | PASS |
| Maximum | 151.245 ms | $< 300$ ms (timeout at 1000ms) | PASS |
| Budget Compliance | 100.0% decisions $< 300$ ms | 100.0% | PASS |
| Timeouts ($> 1000$ ms) | 0 | 0 | PASS |

- **Assessment**: The PIMC Minimax engine demonstrates outstanding tactical performance against `medium_bot` (86.0% WR) while strictly respecting the wall-clock execution budget (mean 20.0ms, max 151.2ms, 0 timeouts).

---

### Criterion 5: Leaderboard Reference Seeds (Tier 4)
Command: `python3 benchmark_suite.py --tier seeds`
| Seed | Complexity / Theme | Winner | Match Score (mon-bot / opp) | Rounds | Steps | Status |
|:----:|-------------------|:------:|:---------------------------:|:------:|:-----:|:------:|
| `848914317` | Ace tactical warfare | **mon-bot** | 116 / 151 | 21 | 774 | **PASSED** |
| `1477911113` | Tight score survival | **medium_bot** | 174 / 71 | 17 | 658 | **FAILED** |
| `2063595735` | Queen combos & 8-dumps | **mon-bot** | 102 / 163 | 23 | 883 | **PASSED** |
| `329389206` | Endurance marathon | **medium_bot** | 158 / 85 | 20 | 710 | **FAILED** |

- **Seed Win Rate**: 2/4 (50.0%) vs Target 100%.

---

## 3. Packaging and Compliance
- `arena pack .`:
  - Output ZIP: `/home/ibrahim-tomota/mon-bot/mon-bot-submission.zip`
  - Packaged files: `bot.py`, `card_tracker.py`, `evaluator.py`
  - Requirements sanitized (`i151-arena-sdk` properly stripped)
  - AST Verification: Valid and loadable via `arena_sdk.loader.load_submission_zip`

---

## 4. Recommendations for Engineering Team

1. **Tune Penalty Dump Threshold vs Fast Hands**:
   - In `evaluator.py`, adjust the 8 and Ace retention penalties. Currently, holding an 8 is penalized only when opponent hand size $\le 3$. Increasing the penalty or lowering the threshold when opponent hand size is $\le 4$ or when my hand size is $\ge 5$ will prevent accumulating 32 penalty points against fast dumpers (like `basic_bot`).
2. **Leaderboard Seed Defensive Calibration**:
   - Inspect seeds `1477911113` and `329389206`. Both matches involved mon-bot exceeding 151 penalty points due to late-round high-card holding. Emphasize score-preservation heuristic when `total_score` exceeds 100 points.

---

## 5. Challenger Verdict

**Verdict**: **REQUEST_CHANGES**  
**Reason**: While Tier 1 (100%), Tier 2 Random (100%), Tier 3 Medium (86.0%), latency budget (100%), and packaging compliance all fully pass, the bot achieved 80.0% vs `basic_bot` (threshold: $\ge 95\%$) and won 2/4 reference seeds (threshold: 4/4).
