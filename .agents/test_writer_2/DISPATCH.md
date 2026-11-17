## 2026-08-30T23:22:40Z

You are Test Writer 2 (Replacement for test_writer_1) for the i151 Grand Master Bot Project (Milestone 1 / R4: Automated Tournament Benchmark & Verification Suite).
Your working directory is /home/ibrahim-tomota/mon-bot/.agents/test_writer_2.
Read ORIGINAL_REQUEST.md at /home/ibrahim-tomota/mon-bot/.agents/ORIGINAL_REQUEST.md.
Read PROJECT.md at /home/ibrahim-tomota/mon-bot/.agents/PROJECT.md and TEST_INFRA.md at /home/ibrahim-tomota/mon-bot/.agents/TEST_INFRA.md.
Read domain skill at /home/ibrahim-tomota/mon-bot/.agents/skills/i151-master-bot/SKILL.md.
Read Survey Explorer 3 report at /home/ibrahim-tomota/mon-bot/.agents/survey_explorer_3/survey_report.md.
Read previous test writer's progress at /home/ibrahim-tomota/mon-bot/.agents/test_writer_1/progress.md.

Your tasks:
1. Implement the comprehensive, standalone automated benchmark and verification harness `/home/ibrahim-tomota/mon-bot/benchmark_suite.py`.
   The script must provide:
   - CLI options: `--tier {all,1,2,3,4,smoke,seeds,baselines}`, `--games <N>` (default 50), `--profile-latency`, `--json-out <path>`, `--bot <path>` (default bot.py).
   - Direct execution via arena CLI (`arena match`, `arena test`, `arena pack`) or programmatic Python SDK imports (`arena_sdk`, `i151_engine`).
   - Tier 1: Smoke test (`arena test bot.py` or programmatic equivalent), syntax & packaging validation (`arena pack`), anti-Queen 2P invariant test.
   - Tier 2: Baselines vs `builtin:random` and `builtin:basic` (N matches each, win rate >= 95%, 0 forfeits).
   - Tier 3: Tactical match vs `builtin:medium` (N matches, win rate >= 65-75%, 0 forfeits, latency profiling).
   - Tier 4: Leaderboard reference seeds (`848914317`, `1477911113`, `2063595735`, `329389206`) vs `builtin:medium` (100% win rate expected).
   - Latency statistical profiling: min, mean, p50, p90, p95, p99, max latency tracking per move.
   - Beautiful ASCII summary table output and structured JSON export.
2. Execute `python3 benchmark_suite.py --tier 1` to verify it works cleanly.
3. Write a completion report and handoff.md in your working directory.
4. Send a message to your parent upon completion with the path to your report.
