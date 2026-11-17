# E2E Test Infra: i151 Grand Master Bot

## Test Philosophy
- Opaque-box, requirement-driven.
- Automated multi-tier verification covering unit invariants, baseline opponents, competitive medium benchmarks, leaderboard deterministic seeds, latency profiling, and packaging compliance.

## Feature Inventory & Test Mapping
| # | Feature | Requirement Source | Tier 1 (Smoke/Invariants) | Tier 2 (Baselines >=95%) | Tier 3 (Medium >=65-75%) | Tier 4 (Leaderboard Seeds) |
|---|---------|-------------------|:-------------------------:|:------------------------:|:------------------------:|:--------------------------:|
| 1 | PIMC Minimax Engine (R1) | ORIGINAL_REQUEST §1 | ✓ | ✓ | ✓ | ✓ |
| 2 | Bitboard 32-bit State | ORIGINAL_REQUEST §1 | ✓ | ✓ | ✓ | ✓ |
| 3 | Bayesian Card Tracker | ORIGINAL_REQUEST §1 | ✓ | ✓ | ✓ | ✓ |
| 4 | Suit Starvation (R2) | ORIGINAL_REQUEST §1 | ✓ | ✓ | ✓ | ✓ |
| 5 | Chaining & Lead Control | ORIGINAL_REQUEST §1 | ✓ | ✓ | ✓ | ✓ |
| 6 | 2P Queen Anti-Trap Invariant | ORIGINAL_REQUEST §1 | ✓ | ✓ | ✓ | ✓ |
| 7 | Win-Streak Hunting | ORIGINAL_REQUEST §1 | ✓ | ✓ | ✓ | ✓ |
| 8 | Exact Endgame Solver (R3) | ORIGINAL_REQUEST §1 | ✓ | ✓ | ✓ | ✓ |
| 9 | Zero Forfeits / Zero Timeouts | Acceptance Criteria | ✓ | ✓ | ✓ | ✓ |
| 10| Move Latency in [50ms, 300ms] | Acceptance Criteria | ✓ | ✓ | ✓ | ✓ |
| 11| Submission Packaging | Acceptance Criteria | ✓ | ✓ | ✓ | ✓ |

## Test Architecture
- **Harness**: `benchmark_suite.py` (CLI runner with options `--tier`, `--games`, `--profile-latency`, `--json-out`).
- **Pass/Fail Semantics**:
  - Tier 1: `arena test bot.py` passes with 0 forfeits/timeouts.
  - Tier 2: $\ge 95\%$ win rate across 50 games vs `builtin:random` and 50 games vs `builtin:basic`.
  - Tier 3: $\ge 65\text{--}75\%$ win rate across 50 games vs `builtin:medium` with latency within $[50\text{ms}, 300\text{ms}]$.
  - Tier 4: $100\%$ win rate on seeds `848914317`, `1477911113`, `2063595735`, `329389206` vs `builtin:medium`.
  - Packaging: `arena pack .` succeeds and produces valid `mon-bot-submission.zip`.

## Real-World Application Scenarios (Tier 4)
| # | Scenario / Seed | Complexity | Opponent | Success Metric |
|---|-----------------|------------|----------|----------------|
| 1 | Seed `848914317` | High (tactical Ace warfare & suit blocks) | `builtin:medium` | Victory (p0 wins) |
| 2 | Seed `1477911113` | High (tight score survival endgame) | `builtin:medium` | Victory (p0 wins) |
| 3 | Seed `2063595735` | High (Queen combos & 8-dumps under pressure) | `builtin:medium` | Victory (p0 wins) |
| 4 | Seed `329389206` | Extreme (29 rounds endurance, >1000 steps) | `builtin:medium` | Victory (p0 wins) |
| 5 | Mirror Match | Extreme (Bot vs Bot self-play) | `mon-bot` | 0 crashes, balanced win distribution (~50%) |
| 6 | Bank Recycled Endurance | High (multiple bank draw exhausts) | `builtin:medium` | 0 crashes/exceptions |
