## 2026-08-30T22:48:22Z
You are Survey Explorer 2 (Search Architecture & Game-Theoretic Engine Specialist).
Your working directory is /home/ibrahim-tomota/mon-bot/.agents/survey_explorer_2.
Read ORIGINAL_REQUEST.md at /home/ibrahim-tomota/mon-bot/.agents/ORIGINAL_REQUEST.md.
Read the domain skill at /home/ibrahim-tomota/mon-bot/.agents/skills/i151-master-bot/SKILL.md and examine all algorithmic advice, formulas, and heuristics.

Your tasks:
1. Investigate the algorithmic requirements for the Grand Master bot:
   - R1: Perfect Information Monte Carlo (PIMC) + Minimax Alpha-Beta search, iterative deepening, transposition table/memoization, deterministic rollout determinization, node evaluation function, time allocation per move (within [50ms, 300ms]).
   - R2: Game-theoretic suit starvation, multi-card chaining / lead control, Queen combo dynamics, win-streak hunting / score differential optimization.
   - R3: Exact terminal endgame solver when remaining unseen/hand cards <= 6 (perfect information retrograde / exhaustive alpha-beta solver).
2. Formulate state representations (bitboards or fast integer arrays), fast copy/simulation mechanics, determinization sampling count vs depth trade-offs.
3. Identify all critical design constraints, heuristics, and potential pitfalls.
4. Write a comprehensive architectural survey report to /home/ibrahim-tomota/mon-bot/.agents/survey_explorer_2/survey_report.md and a handoff.md.
5. Send a message to your parent upon completion with the path to your report.
