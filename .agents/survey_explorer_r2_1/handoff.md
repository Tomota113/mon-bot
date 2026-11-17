# Handoff Report: Investigation of PIMC Minimax, R1, R2, and R3

**Agent**: Survey Explorer 1 (`survey_explorer_r2_1`)  
**Date**: 2026-09-09  
**Type**: Hard (Task Complete)  
**Report Artifact**: `/home/ibrahim-tomota/mon-bot/.agents/survey_explorer_r2_1/survey_report.md`

---

## 1. Observation

1. **Minimax Search Depth and Decision Formula**:
   - In `/home/ibrahim-tomota/mon-bot/bot.py:212`:
     ```python
     max_search_depth = 4
     ```
   - In `/home/ibrahim-tomota/mon-bot/bot.py:262-270`:
     ```python
     val = _alphabeta_search(
         s1,
         max_search_depth - 1,
         float("-inf"),
         float("inf"),
         0,
         tt,
         streak_mode,
     )
     ```
     Root action counts as 1 ply; `_alphabeta_search` searches `max_search_depth - 1 = 3` plies deeper. Total lookahead is 4 plies.
   - In `/home/ibrahim-tomota/mon-bot/bot.py:277-284`:
     ```python
     def evaluate_candidate(a: Action) -> tuple[float, float, str]:
         h_score, h_dump, h_key = score_action(view, a, streak_mode=streak_mode)
         c = max(1, action_counts[a])
         norm_minimax = action_values[a] / c
         total_eval = h_score + norm_minimax * 0.20
         return (total_eval, h_dump, h_key)

     return max(plays, key=evaluate_candidate)
     ```
     Minimax normalized score is down-weighted to `0.20`, while static heuristic `h_score` (values 50 to 2,500+) dominates candidate ranking.

2. **Transposition Table Alpha-Beta Bounding**:
   - In `/home/ibrahim-tomota/mon-bot/bot.py:415` and `433`:
     ```python
     tt[z_key] = (depth, max_v, best_act)
     ...
     tt[z_key] = (depth, min_v, best_act)
     ```
   - In `/home/ibrahim-tomota/mon-bot/bot.py:368-371`:
     ```python
     if z_key in tt:
         cached_depth, cached_val, _ = tt[z_key]
         if cached_depth >= depth:
             return cached_val
     ```
     Cached values do not store bound types (`EXACT`, `LOWER_BOUND`, `UPPER_BOUND`). Cutoff values (`beta <= alpha`) are cached and retrieved as exact scores.
   - Move ordering in `bot.py:380-398` does not inspect `tt` to prioritize the principal variation (PV) move.

3. **Wildcard & Penalty Dumping Scoring (Rank 8s & Aces)**:
   - In `/home/ibrahim-tomota/mon-bot/evaluator.py:636`:
     ```python
     score += dump * 1.1
     ```
     An 8 dumps 32 points, contributing $+35.2$ points.
   - In `/home/ibrahim-tomota/mon-bot/evaluator.py:550-560`:
     ```python
     if card.rank == Rank.EIGHT:
         if is_agony or remaining_after <= 2 or streak_mode == 2 or opp_size <= 4:
             bonus += 60.0
         elif my_size <= 4:
             bonus += 40.0
         elif my_size >= 7:
             bonus -= 10.0
         elif my_size >= 5:
             bonus -= 2.0
         else:
             bonus += 20.0
     ```
     For hand size 5–6 (`my_size >= 5`), the penalty is only $-2.0$. Net heuristic for playing an 8 over a 7 (0 dump points, 0 bonus) is $+33.2$ in favor of burning the 8. For hand size $\ge 7$, penalty is only $-10.0$, still $+25.2$ in favor of burning the 8.
   - In `/home/ibrahim-tomota/mon-bot/evaluator.py:562-571`:
     An Ace (11 dump points, $+12.1$) receives base `bonus += 15.0` even when not tactical and not in agony, giving $+27.1$ preference over regular 0-point cards.
   - In `/home/ibrahim-tomota/mon-bot/evaluator.py:644-650`:
     `is_agony` activates when `opp_size <= 4` or `view.you.hand_size <= 4`.

4. **Queen 2P Filter & Tempo Dynamics**:
   - `finishes_on_queen_two_player` in `/home/ibrahim-tomota/mon-bot/evaluator.py:263-271` correctly detects single Queen or Queen-ending multi-card finishes in 2P.
   - Filtered in `bot.py:110-112`, `bot.py:88-90`, `evaluator.py:601`, and `evaluator.py:397-400`.
   - In `i151_engine.core.legal_actions.legal_actions`, multi-card plays are not generated. Queen tempo operates sequentially through extra turns granted by `skip_next_player = True` in 2-player games (`reducer.py:90-128`).
   - In `evaluator.py:658-666`, playing a Queen awards static bonuses ($+15$ to $+75$) based on opponent hand size without evaluating whether the player has a valid follow-up card to play on the Queen.

5. **Opponent Void Tracking & Starvation Suit Forcing**:
   - In `/home/ibrahim-tomota/mon-bot/card_tracker.py:67-68`:
     ```python
     if view.turn.is_your_turn and self.last_table_top is not None:
         if curr_opp_size > self.last_opp_hand_size:
     ```
     Void inference triggers only on strictly increasing opponent hand size. Draws followed by immediate plays (`curr_opp_size == last_opp_hand_size`) are not detected.
   - In `/home/ibrahim-tomota/mon-bot/evaluator.py:210-216`:
     ```python
     if h_count == 0:
         if not has_another_eight:
             pressure[suit] = -10_000.0
     ```
     Assigns $-10,000.0$ if player has 0 cards of that suit, completely barring the bot from choosing that suit.
   - In `/home/ibrahim-tomota/mon-bot/evaluator.py:220-223`:
     ```python
     if opp_void_masks:
         for v in opp_void_masks:
             if (v & s_mask) == s_mask:
                 p += 60.0
     ```
     For Ace-induced voids (`ACES_MASK | EIGHTS_MASK`), `(v & s_mask) == s_mask` never matches because `v` only contains 2 cards of suit `s`.

---

## 2. Logic Chain

1. **Minimax Subordination**:
   - Observation 1 demonstrates `total_eval = h_score + norm_minimax * 0.20`.
   - Because `h_score` has standard magnitudes of $50$ to $2,500$ points while `norm_minimax * 0.20` has typical magnitudes of $\pm 10$ to $30$, static heuristics dictate the action ranking.
   - Furthermore, `max_search_depth = 4` limits search to 3 plies beyond the root move, falling short of the required 5–8 plies lookahead.
   - Therefore, the bot currently operates as a heuristic-dominated player rather than a Minimax-driven engine.

2. **Wildcard Squandering (R1 Failure)**:
   - Observation 3 shows that playing an 8 yields $32 \times 1.1 = +35.2$ dump points against a $-2.0$ penalty at hand sizes 5 and 6, and $-10.0$ penalty at hand size 7+.
   - Playing a 7 or 9 yields $0$ dump points and $0$ penalty.
   - Net ranking calculates $35.2 - 2.0 = +33.2$ in favor of playing the 8 at hand sizes 5 and 6.
   - Consequently, the bot burns 8s as high-value dump cards early in the round rather than saving them as universal counters and emergency escapes.
   - Agony dumping triggers at `opp_size <= 4` instead of the genuine round-termination criteria (`opp_size <= 3` or `my_size <= 2`).

3. **Queen Tempo Limitations (R2)**:
   - Observation 4 confirms that while solitary Queen finishes are strictly prevented, Queen play scoring is purely static ($+15$ to $+75$).
   - If a player plays a Queen without a follow-up card of matching suit, rank, or an 8, the player is forced to draw from the bank on the subsequent sequential turn, squandering tempo.
   - Shallow search depth (4 plies) prevents Minimax from evaluating the full tempo cycle across sequential turns.

4. **Void Inference and Starvation Flaws (R3)**:
   - Observation 5 shows that void tracking relies solely on `curr_opp_size > last_opp_hand_size`, missing turns where the opponent drew and played.
   - Suit pressure hard-locks any suit with $h\_count = 0$ to $-10,000.0$, preventing strategic starvation of known opponent voids.
   - The bitmask equality test `(v & s_mask) == s_mask` fails for Ace voids and does not compute Bayesian probabilities.

---

## 3. Caveats

- **Time Budget Trade-off**: Increasing Minimax search depth from 4 to 6–8 plies will increase CPU time per move. While current latency is $\approx 10\text{–}20\text{ ms}$ (well below the $150\text{ ms}$ target and $1000\text{ ms}$ timeout), iterative deepening or move ordering optimization (PV-first) will be necessary to stay strictly within $[50\text{ ms}, 300\text{ ms}]$.
- **Multi-Card Rules in Runtime**: The engine rules define `is_valid_multiple_play`, but `match_runner.py` enforces `legal_actions()`, which only generates single-card plays. Returning multi-card actions directly from `decide()` causes an immediate forfeit.

---

## 4. Conclusion

The current codebase contains solid bitboard primitives and passes baseline sanity and smoke tests. However, it fails all core competitive requirements of R1, R2, and R3:
- **R1**: 8s and Aces are burned prematurely early/mid round due to insufficient preservation penalties ($-2.0$ vs $+35.2$ dump gain); penalty dumping activates at `opp_size <= 4`.
- **R2**: Search depth is hardcoded to 4 plies instead of 5–8; Minimax is down-weighted to $0.20$ and overridden by heuristics; TT Alpha-Beta bounds are unsound; Queen follow-up tempo is not verified.
- **R3**: Opponent void tracking misses draw-and-play actions; suit selection bypasses Minimax and hard-locks suits with $h\_count = 0$; Ace-induced voids are bugged.

The system requires deep algorithmic remediation along the lines detailed in `survey_report.md`.

---

## 5. Verification Method

To independently verify all findings and test suite behavior:

1. **Unit Test Suite**:
   ```bash
   python -m unittest test_engine.py
   ```
   *Expected result*: 12 tests pass in $< 0.01\text{ s}$.

2. **Official Arena Smoke Test**:
   ```bash
   arena test bot.py
   ```
   *Expected result*: `OK — match terminé sans forfait` (exit code 0).

3. **Automated Tier 1 Benchmark & Packaging Verification**:
   ```bash
   python benchmark_suite.py --tier 1
   ```
   *Expected result*: 5/5 checks pass (Smoke test, Packaging, Anti-Queen 2P, Suit Selection, Legal Action Adherence).

4. **Submission Packaging Compliance**:
   ```bash
   arena pack .
   ```
   *Expected result*: Outputs valid `mon-bot-submission.zip` containing `bot.py`, `card_tracker.py`, `evaluator.py`.

5. **Premature 8 Burning Reproduction**:
   Inspect line 558 of `evaluator.py` (`bonus -= 2.0`) vs line 636 (`score += dump * 1.1 = 35.2`). Evaluate `score_action` on hand with an 8 and a 7 at hand size 6 to observe $+33.2$ preference for burning the 8.
