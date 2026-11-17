## 2026-08-30T22:54:09Z
You are Core Engine Worker 1 for the i151 Grand Master Bot Project (Milestones 2, 3, 4: PIMC Minimax, Game-Theoretic Dynamics, Exact Endgame Solver).
Your working directory is /home/ibrahim-tomota/mon-bot/.agents/engine_worker_1.
Read ORIGINAL_REQUEST.md at /home/ibrahim-tomota/mon-bot/.agents/ORIGINAL_REQUEST.md.
Read PROJECT.md at /home/ibrahim-tomota/mon-bot/.agents/PROJECT.md.
Read domain skill at /home/ibrahim-tomota/mon-bot/.agents/skills/i151-master-bot/SKILL.md.
Read Survey Explorer 1 report at /home/ibrahim-tomota/mon-bot/.agents/survey_explorer_1/survey_report.md and Survey Explorer 2 report at /home/ibrahim-tomota/mon-bot/.agents/survey_explorer_2/survey_report.md.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Your file ownership:
You own `/home/ibrahim-tomota/mon-bot/bot.py`, `/home/ibrahim-tomota/mon-bot/card_tracker.py`, and `/home/ibrahim-tomota/mon-bot/evaluator.py`.

Your implementation tasks:
1. **R1: Core Engine & Representation (`evaluator.py`, `card_tracker.py`, `bot.py`)**:
   - 32-bit bitboard state representation (POPCNT, bitwise legal action generation, fast transitions achieving millions of ops/sec).
   - 64-bit Zobrist Transposition Table with PV move ordering.
   - PIMC Minimax Alpha-Beta search with iterative deepening across $W=8..12$ determinized worlds.
   - Bayesian Negative Inference Card Tracker (track played/seen cards, infer opponent voids from draws/passes, sample consistent worlds).
   - Time budget management ([50ms, 300ms] nominal target, hard deadline cutoff at 150ms).
   - Zero forfeit/timeout exception handling & safe legal fallback.
2. **R2: Game-Theoretic Dynamics & Heuristics (`evaluator.py`, `bot.py`)**:
   - Suit starvation formula on 8s to lock opponent in draw loops.
   - Multi-card chaining & lead retention.
   - Queen combo dynamics in 2P & strict Anti-Queen solitary finish filter (hard-filter solitary Queen final card to prevent 1-card draw penalty).
   - Win-streak hunting mode (+1000 equity bonus when consecutive round wins == 2 to capture -10 pt bonus), Streak Buster mode, Agony survival mode (>=115 pts), Executioner mode (opp >=120 pts).
3. **R3: Exact Terminal Endgame Solver (`evaluator.py`, `bot.py`)**:
   - Exhaustive retrograde / Alpha-Beta solver when unrevealed cards $|U| \le 6$ (< 1ms).
4. Run `arena test bot.py` and verify zero forfeits, 0 timeouts, clean execution.
5. Run benchmark matches against `builtin:random`, `builtin:basic`, `builtin:medium` and check latency.
6. Write a comprehensive implementation and test report in your working directory and handoff.md.
7. Send a message to your parent upon completion with the path to your report.
