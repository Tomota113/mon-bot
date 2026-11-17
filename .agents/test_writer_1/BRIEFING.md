# BRIEFING — 2026-08-30T22:56:00Z

## Mission
Implement the comprehensive, automated benchmark and verification harness `benchmark_suite.py` for i151 Grand Master Bot (Milestone 1 / R4), supporting Tiers 1-4, seed tests, latency profiling, and JSON/ASCII reporting.

## 🔒 My Identity
- Archetype: test_writer
- Roles: specialist, qa
- Working directory: /home/ibrahim-tomota/mon-bot/.agents/test_writer_1
- Original parent: 50c75927-3386-4933-bf5e-0daba9d67cfb
- Milestone: M1 (R4: Automated Tournament Benchmark & Verification Suite)

## 🔒 Key Constraints
- Write test and harness code only — never modify implementation code.
- Implement `/home/ibrahim-tomota/mon-bot/benchmark_suite.py` with CLI options `--tier`, `--games`, `--profile-latency`, `--json-out`, `--bot`.
- Tier 1: Smoke test (`arena test` or programmatic equivalent), packaging validation (`arena pack`), anti-Queen 2P invariant test.
- Tier 2: Baselines vs `builtin:random` and `builtin:basic` (50 matches each, win rate >= 95%, 0 forfeits).
- Tier 3: Tactical match vs `builtin:medium` (50 matches, win rate >= 65-75%, 0 forfeits, latency profiling).
- Tier 4: Leaderboard reference seeds (`848914317`, `1477911113`, `2063595735`, `329389206`) vs `builtin:medium` (100% win rate expected).
- Latency statistical profiling: min, mean, p50, p90, p95, p99, max latency tracking per move.
- ASCII summary table output and structured JSON export.

## Current Parent
- Conversation ID: 50c75927-3386-4933-bf5e-0daba9d67cfb
- Updated: not yet

## Task Summary
- **What to build**: `benchmark_suite.py`
- **Success criteria**: All CLI modes functional, comprehensive multi-tier tests, 0 crashes, accurate stats and ASCII/JSON output.
- **Interface contracts**: `/home/ibrahim-tomota/mon-bot/.agents/PROJECT.md`
- **Code layout**: `/home/ibrahim-tomota/mon-bot/`

## Loaded Skills
- **Source**: `/home/ibrahim-tomota/mon-bot/.agents/skills/i151-master-bot/SKILL.md`
- **Local copy**: `/home/ibrahim-tomota/mon-bot/.agents/test_writer_1/SKILL_copy.md`
- **Core methodology**: Multi-tier game-theoretic verification, PIMC minimax validation, invariant filtering, latency profiling.

## Quality Status
- **Build/test result**: Initializing
- **Lint status**: 0 violations
- **Tests added/modified**: `benchmark_suite.py`

## Key Decisions Made
- Use `arena_sdk` and `i151_engine` APIs directly with high performance instrumentation wrapper for move latency profiling.
- Include unit-level invariant checks for Queen 2P trap, illegal move rejection, and packaging verification.
- Provide clear colorized/ASCII formatting for CLI execution and structured machine-readable JSON reports.

## Artifact Index
- `/home/ibrahim-tomota/mon-bot/benchmark_suite.py` — Main benchmark and verification suite runner.
