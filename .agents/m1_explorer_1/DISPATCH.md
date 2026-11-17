# M1 Explorer 1 Dispatch

Milestone: M1 (Symmetric Benchmark Suite R4)
Focus: Slot Inversion Architecture & Tournament Pairing in benchmark_suite.py.
Read:
- /home/ibrahim-tomota/mon-bot/.agents/ORIGINAL_REQUEST.md
- /home/ibrahim-tomota/mon-bot/.agents/orchestrator_2/PROJECT.md
- /home/ibrahim-tomota/mon-bot/benchmark_suite.py
- /home/ibrahim-tomota/mon-bot/.agents/survey_explorer_r2_3/benchmark_report.md
- /home/ibrahim-tomota/mon-bot/.agents/survey_explorer_r2_3/handoff.md
Output: Write fix recommendation to /home/ibrahim-tomota/mon-bot/.agents/m1_explorer_1/analysis.md and handoff.md.

## 2026-09-09T14:06:29Z
You are M1 Explorer 1. Your working directory is /home/ibrahim-tomota/mon-bot/.agents/m1_explorer_1.
Read:
- /home/ibrahim-tomota/mon-bot/.agents/ORIGINAL_REQUEST.md
- /home/ibrahim-tomota/mon-bot/.agents/orchestrator_2/PROJECT.md
- /home/ibrahim-tomota/mon-bot/benchmark_suite.py
- /home/ibrahim-tomota/mon-bot/.agents/survey_explorer_r2_3/benchmark_report.md
- /home/ibrahim-tomota/mon-bot/.agents/survey_explorer_r2_3/handoff.md

Investigate and produce a detailed, line-by-line implementation strategy for:
1. Two-way symmetric tournament pairing in `BenchmarkRunner.run_series()`:
   - For a series of N games (default 50 vs medium), allocate exactly half (games // 2 = 25) with mon-bot as challenger p0 and opponent as p1, and the other half (25) with opponent as challenger p0 and mon-bot as opponent p1.
   - For each half, alternate `dealer = 1` and `dealer = 0` so starting player is evenly split 50/50.
   - In `play_bots_match`, ensure correct parameters are passed when mon-bot is p1: `play_bots_match(opp.bot, self.instrumented_bot, config, challenger_name=opp_name, opponent_name='mon-bot', opponent_id='student:mon-bot', challenger_dir=opp.submission_dir, opponent_dir=self.challenger_dir, manage_lifecycle=False)`.
   - Update win/loss detection to dynamically check `res.winner_id == my_slot`.
Write your analysis to /home/ibrahim-tomota/mon-bot/.agents/m1_explorer_1/analysis.md and handoff to /home/ibrahim-tomota/mon-bot/.agents/m1_explorer_1/handoff.md. Send a message when done.

## 2026-09-09T14:07:45Z
**Context**: Critical Tournament Rules Update from Official Regulations
**Content**: 
1. HARD SERVER TIMEOUT: 400 ms per decision (NOT 1000ms!). Engine must target 80ms - 180ms with hard cutoff at 250ms to guarantee zero timeouts/forfeits.
2. SUBMISSION LIMIT: Up to 50 MB ZIP allowed.
3. STRICT SANDBOX CONSTRAINTS: Forbidden: eval(), exec(), pickle.load, network sockets, reading outside submission_dir.
4. RANKING SYSTEM: Ranked by total number of victories.
5. ROOT CAUSES:
   - Rank 8 dumping: previous code had false 'my_score >= 80' agony trigger. 8s must be preserved as emergency trumps when hand >= 5.
   - Exact endgame solver: Only active when unrevealed_mask.bit_count() <= 6 AND bank_size == 0.
   - Symmetric 50-game verification: 25 games p0, 25 games p1 vs medium_bot with alternating dealers, win rate >= 70%.
**Action**: Incorporate these constraints into your analysis and recommendations.
