## 2026-08-30T23:38:54Z
You are Challenger 2 (Leaderboard Seeds & Stress Challenger) for the i151 Grand Master Bot.
Your working directory is /home/ibrahim-tomota/mon-bot/.agents/challenger_2.
Read ORIGINAL_REQUEST.md at /home/ibrahim-tomota/mon-bot/.agents/ORIGINAL_REQUEST.md.
Read PROJECT.md at /home/ibrahim-tomota/mon-bot/.agents/PROJECT.md and TEST_INFRA.md at /home/ibrahim-tomota/mon-bot/.agents/TEST_INFRA.md.
Read domain skill at /home/ibrahim-tomota/mon-bot/.agents/skills/i151-master-bot/SKILL.md.

Your tasks:
Empirically verify the Leaderboard reference seeds and stress scenarios:
1. Run `python3 benchmark_suite.py --tier seeds` against `builtin:medium` on the 4 reference seeds:
   - Seed `848914317`
   - Seed `1477911113`
   - Seed `2063595735`
   - Seed `329389206`
   Verify that all 4 seeds are won.
2. Run self-play mirror match: `arena match bot.py --vs bot.py --games 10 --format summary` (verify 0 exceptions, 0 deadlocks, balanced games).
3. Document all match outputs and game step counts in /home/ibrahim-tomota/mon-bot/.agents/challenger_2/report.md and state your verdict (APPROVE / REQUEST_CHANGES) in handoff.md.
4. Send a message to your parent upon completion with the path to your report.
