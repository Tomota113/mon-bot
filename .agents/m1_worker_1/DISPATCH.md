## 2026-09-09T14:11:52Z
You are M1 Worker. Your working directory is /home/ibrahim-tomota/mon-bot/.agents/m1_worker_1.

Exclusively Owned Files:
- /home/ibrahim-tomota/mon-bot/benchmark_suite.py
- /home/ibrahim-tomota/mon-bot/test_engine.py

Read:
- /home/ibrahim-tomota/mon-bot/.agents/ORIGINAL_REQUEST.md
- /home/ibrahim-tomota/mon-bot/.agents/orchestrator_2/PROJECT.md
- /home/ibrahim-tomota/mon-bot/.agents/m1_explorer_1/analysis.md
- /home/ibrahim-tomota/mon-bot/.agents/m1_explorer_1/handoff.md
- /home/ibrahim-tomota/mon-bot/.agents/m1_explorer_2/analysis.md
- /home/ibrahim-tomota/mon-bot/.agents/m1_explorer_2/handoff.md
- /home/ibrahim-tomota/mon-bot/.agents/m1_explorer_3/analysis.md
- /home/ibrahim-tomota/mon-bot/.agents/m1_explorer_3/handoff.md
- /home/ibrahim-tomota/mon-bot/.agents/m1_explorer_3/proposed_tier1_and_tests.py

Task:
Implement the complete M1 specification in benchmark_suite.py and test_engine.py:
1. Two-way symmetric pairing in `BenchmarkRunner.run_series()`:
   - For series of games (e.g. 50 vs medium), allocate 25 games with mon-bot as challenger p0 and 25 games with mon-bot as opponent p1. In both sets, alternate dealer = 1 if (sub_i % 2 == 0) else 0.
   - Correctly pass challenger / opponent arguments to play_bots_match when mon-bot is p1:
     `play_bots_match(opp.bot, self.instrumented_bot, config, challenger_name=opp_name, opponent_name='mon-bot', opponent_id='student:mon-bot', challenger_dir=opp.submission_dir, opponent_dir=self.challenger_dir, manage_lifecycle=False)`.
   - Update win/loss and forfeit detection based on `my_slot`: `is_win = res.winner_id == my_slot and res.reason == "normal"`, `is_loss = res.winner_id == opp_slot and res.reason == "normal"`, `is_forfeit_loss = res.winner_id == opp_slot and res.reason in ("timeout", "illegal_action", "error")`, `is_forfeit_win = res.winner_id == my_slot and res.reason in ("timeout", "illegal_action", "error")`.
2. Align thresholds:
   - Tier 2 (Baselines): random >= 98.0%, basic >= 98.0%, 0 forfeits.
   - Tier 3 (Medium Series): medium >= 70.0% across 50 symmetric games, 0 forfeits.
   - Tier 4 (Reference Seeds): seeds >= 75.0%, 0 forfeits.
3. Hard latency gating in `overall_passed`: mean < 50.0 ms, max < 300.0 ms, 0 timeouts, 0 forfeits.
4. Comprehensive packaging verification in `Tier1Verifier._verify_packaging`: run `arena pack .`, verify `mon-bot-submission.zip` CRC, size <= 50 MB, AST sandbox auditing (no eval, exec, pickle.load, forbidden imports, network, outside reads).
5. Add unit tests in `test_engine.py` verifying packaging, CLI, and tournament constraints.
6. Verify implementation by running:
   - `python3 -m unittest test_engine.py`
   - `python3 benchmark_suite.py --tier 1`

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Write your handoff report to /home/ibrahim-tomota/mon-bot/.agents/m1_worker_1/handoff.md with passing test results and send a message when done.
