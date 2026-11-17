# Original User Request

## Initial Request — 2026-08-30T22:47:48Z

You are the Project Orchestrator for developing, hyper-optimizing, and benchmarking the Grand Master AI Bot for the i151 Arena competition.

Working Directory: /home/ibrahim-tomota/mon-bot/.agents/orchestrator
Original Request: /home/ibrahim-tomota/mon-bot/.agents/ORIGINAL_REQUEST.md
Skills available: Check /home/ibrahim-tomota/mon-bot/.agents/skills/i151-master-bot/SKILL.md for domain expertise, rule mechanics, scoring, game dynamics, and tournament benchmark tools.

Your objective:
1. Decompose and orchestrate the full implementation of R1 (PIMC Minimax Alpha-Beta search engine in bot.py), R2 (Game-theoretic suit starvation, multi-card chaining, Queen combo dynamics, win-streak hunting), R3 (Exact terminal endgame solver for remaining cards <= 6), and R4 (Automated tournament benchmark & verification suite).
2. Ensure all acceptance criteria are met:
   - arena test bot.py passes with 0 forfeits/timeouts.
   - Decision execution time within [50ms, 300ms].
   - arena pack . succeeds creating valid mon-bot-submission.zip.
   - Win rate >= 95% vs builtin:random and builtin:basic.
   - Win rate >= 65-75% vs builtin:medium across 50 matches.
   - Wins benchmark seeds against top leaderboard bots (848914317, 1477911113, 2063595735, 329389206).
3. Maintain progress.md and BRIEFING.md in your working directory.
4. When finished and thoroughly verified, report completion.

## Follow-up — 2026-09-09T13:56:44Z

Develop and hyper-optimize a Grand Master AI Bot for the i151 Arena competition (https://challenge.jeu-151.com) capable of dominating the current leaderboard leaders: Oureiba Oumar (ELO 1976), Anw Djigui (ELO 1927), and Master of 151 (ELO 1888).

Working directory: /home/ibrahim-tomota/mon-bot
Integrity mode: development

## Requirements

### R1. Strategic Resource Preservation & Wildcard Timing (8 & As)
Eliminate premature burning of rank 8 wildcards and Aces in the early/mid round. Retain 8s as universal counters and emergency escapes when hand size >= 5, transitioning into aggressive penalty dumping only when the round is genuinely terminating (opponent hand <= 3 or self hand <= 2).

### R2. Deep Minimax Lookahead & 2-Player Tempo Mastery (Dames & Combos)
Amplify tree search depth (5–8 plies) with Alpha-Beta pruning, transposition caching, and move ordering. Ensure Minimax value is the primary driver of decision-making. Maximize tempo-skipping Queen combos in 2-player mode while enforcing zero Queen-alone finishes.

### R3. Bayesian Opponent Void Tracking & Game-Theoretic Starvation
Track full-round card history and infer opponent void suits whenever an opponent draws and passes. When playing an 8, calculate and force the exact suit the opponent cannot answer, forcing bank draw penalties.

### R4. Symmetric Unbiased Tournament Verification Suite
Benchmark the bot on symmetric two-way matches against builtin:medium (50 games total: 25 as challenger p0, 25 as opponent p1) with alternating dealers to eliminate first-player bias. Ensure packaging via arena pack . produces a compliant submission archive.

## Acceptance Criteria

### Performance & Rules Compliance
- arena test bot.py passes with 0 forfeits, 0 timeouts, and 0 illegal moves.
- Average decision latency remains strictly < 50 ms (max < 300 ms, budget 1000 ms).
- arena pack . outputs a valid mon-bot-submission.zip with clean dependencies.

### Real Competitive Win Rate (Symmetric & Unbiased)
- Win rate >= 98% vs builtin:random and builtin:basic.
- Win rate >= 70% vs builtin:medium across 50 symmetric matches (alternating p0/p1).
- Win rate >= 75% across the top leaderboard reference seeds (848914317, 1477911113, 2063595735, 329389206).

## Follow-up — 2026-09-09T14:07:04Z

CRITICAL TOURNAMENT RULES & USER DIRECTIVES FROM OFFICIAL REGULATION SCREENSHOTS:

1. HARD SERVER TIMEOUT: 400 ms per decision (NOT 1000ms!). The decision engine MUST target 80ms - 180ms with hard cutoff at 250ms to guarantee zero timeouts/forfeits.
2. SUBMISSION LIMIT: Up to 50 MB ZIP is officially allowed! Use local precomputed tables/lookup structures or compact tablebases if needed to maximize win rate.
3. STRICT SANDBOX CONSTRAINTS: Forbidden: eval(), exec(), pickle.load, network sockets, reading outside submission_dir (/dev/shm, /etc, /proc). Any violation triggers immediate forfeit.
4. RANKING SYSTEM: The official podium is ranked by TOTAL NUMBER OF VICTORIES (Elo K=32 is the power rating). Win-rate maximization is the #1 imperative.
5. ROOT CAUSES TO FIX IMMEDIATELY:
   - Rank 8 wildcard dumping: Previous code dumped 8s early due to false 'my_score >= 80' agony trigger. 8s must be preserved as emergency trumps when hand >= 5.
   - Exact endgame solver: Only active when unrevealed_mask.bit_count() <= 6 AND bank_size == 0.
   - Symmetric 50-game verification: Must test 25 games as p0 and 25 games as p1 vs medium_bot with alternating dealer indices. Win rate must be >= 70%.

The user wants #1 place on the leaderboard and nothing else. Maximize every legal competitive advantage.
