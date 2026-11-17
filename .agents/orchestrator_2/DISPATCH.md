## 2026-09-09T13:57:39Z

You are the Project Orchestrator for developing, hyper-optimizing, and benchmarking the Grand Master AI Bot for the i151 Arena competition.

Working Directory: /home/ibrahim-tomota/mon-bot/.agents/orchestrator_2
Project Directory: /home/ibrahim-tomota/mon-bot
Authoritative Request: /home/ibrahim-tomota/mon-bot/.agents/ORIGINAL_REQUEST.md
Skill Available: /home/ibrahim-tomota/mon-bot/.agents/skills/i151-master-bot/SKILL.md

User Objective & Requirements:
R1. Strategic Resource Preservation & Wildcard Timing (8 & As):
Eliminate premature burning of rank 8 wildcards and Aces in the early/mid round. Retain 8s as universal counters and emergency escapes when hand size >= 5, transitioning into aggressive penalty dumping only when the round is genuinely terminating (opponent hand <= 3 or self hand <= 2).

R2. Deep Minimax Lookahead & 2-Player Tempo Mastery (Dames & Combos):
Amplify tree search depth (5–8 plies) with Alpha-Beta pruning, transposition caching, and move ordering. Ensure Minimax value is the primary driver of decision-making. Maximize tempo-skipping Queen combos in 2-player mode while enforcing zero Queen-alone finishes.

R3. Bayesian Opponent Void Tracking & Game-Theoretic Starvation:
Track full-round card history and infer opponent void suits whenever an opponent draws and passes. When playing an 8, calculate and force the exact suit the opponent cannot answer, forcing bank draw penalties.

R4. Symmetric Unbiased Tournament Verification Suite:
Benchmark the bot on symmetric two-way matches against builtin:medium (50 games total: 25 as challenger p0, 25 as opponent p1) with alternating dealers to eliminate first-player bias. Ensure packaging via arena pack . produces a compliant submission archive.

Acceptance Criteria:
- arena test bot.py passes with 0 forfeits, 0 timeouts, and 0 illegal moves.
- Average decision latency remains strictly < 50 ms (max < 300 ms, budget 1000 ms).
- arena pack . outputs a valid mon-bot-submission.zip with clean dependencies.
- Win rate >= 98% vs builtin:random and builtin:basic.
- Win rate >= 70% vs builtin:medium across 50 symmetric matches (alternating p0/p1).
- Win rate >= 75% across the top leaderboard reference seeds (848914317, 1477911113, 2063595735, 329389206).

## 2026-09-09T14:07:16Z

CRITICAL TOURNAMENT RULES & USER DIRECTIVES UPDATE (recorded in ORIGINAL_REQUEST.md):

1. HARD SERVER TIMEOUT: 400 ms per decision (NOT 1000ms!). The decision engine MUST target 80ms - 180ms with hard cutoff at 250ms to guarantee zero timeouts/forfeits.
2. SUBMISSION LIMIT: Up to 50 MB ZIP is officially allowed! Local precomputed tables/lookup structures or compact tablebases are permissible to maximize win rate.
3. STRICT SANDBOX CONSTRAINTS: Forbidden: eval(), exec(), pickle.load, network sockets, reading outside submission_dir (/dev/shm, /etc, /proc). Any violation triggers immediate forfeit.
4. RANKING SYSTEM: The official podium is ranked by TOTAL NUMBER OF VICTORIES (Elo K=32 is the power rating). Win-rate maximization is the #1 imperative.
5. ROOT CAUSES TO FIX IMMEDIATELY:
   - Rank 8 wildcard dumping: Previous code dumped 8s early due to false 'my_score >= 80' agony trigger. 8s must be preserved as emergency trumps when hand >= 5.
   - Exact endgame solver: Only active when unrevealed_mask.bit_count() <= 6 AND bank_size == 0.
   - Symmetric 50-game verification: Must test 25 games as p0 and 25 games as p1 vs medium_bot with alternating dealer indices. Win rate must be >= 70%.

Integrate these hard constraints into all milestone designs, engine development, and verification suites. The user wants #1 place on the leaderboard and nothing else. Maximize every legal competitive advantage.
