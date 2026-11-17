# M1 Explorer 3 Dispatch

Milestone: M1 (Symmetric Benchmark Suite R4)
Focus: Automated Packaging Validation & Test Verification Pipeline.
Read:
- /home/ibrahim-tomota/mon-bot/.agents/ORIGINAL_REQUEST.md
- /home/ibrahim-tomota/mon-bot/.agents/orchestrator_2/PROJECT.md
- /home/ibrahim-tomota/mon-bot/benchmark_suite.py
- /home/ibrahim-tomota/mon-bot/.agents/survey_explorer_r2_2/spec_report.md
Output: Write fix recommendation to /home/ibrahim-tomota/mon-bot/.agents/m1_explorer_3/analysis.md and handoff.md.

## 2026-09-09T14:06:29Z
You are M1 Explorer 3. Your working directory is /home/ibrahim-tomota/mon-bot/.agents/m1_explorer_3.
Read:
- /home/ibrahim-tomota/mon-bot/.agents/ORIGINAL_REQUEST.md
- /home/ibrahim-tomota/mon-bot/.agents/orchestrator_2/PROJECT.md
- /home/ibrahim-tomota/mon-bot/benchmark_suite.py
- /home/ibrahim-tomota/mon-bot/.agents/survey_explorer_r2_2/spec_report.md

Investigate and produce a detailed implementation strategy for:
1. Packaging verification in Tier 1:
   - Run `arena pack .` and verify `mon-bot-submission.zip` is created.
   - Verify archive validity with `zipfile.ZipFile`, ensuring it contains `bot.py` and required modules without unauthorized external dependencies.
2. CLI verification commands and regression test verification in `test_engine.py` or new test cases for `benchmark_suite.py`.
Write your analysis to /home/ibrahim-tomota/mon-bot/.agents/m1_explorer_3/analysis.md and handoff to /home/ibrahim-tomota/mon-bot/.agents/m1_explorer_3/handoff.md. Send a message when done.

## 2026-09-09T14:07:55Z
From: 353af73f-00a5-4c89-a94e-e8dfe324a469 (parent)
Priority: MESSAGE_PRIORITY_HIGH
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
