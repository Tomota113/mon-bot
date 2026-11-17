# Comprehensive Survey Report: i151 Grand Master Bot Architecture Analysis

**Date**: 2026-09-09  
**Investigator**: Survey Explorer 1 (`survey_explorer_r2_1`)  
**Target Repository**: `/home/ibrahim-tomota/mon-bot`  
**Reference Standards**: `ORIGINAL_REQUEST.md`, `i151-master-bot/SKILL.md`, `i151_engine` codebase.

---

## Executive Summary

A comprehensive architectural and algorithmic investigation of `bot.py`, `evaluator.py`, `card_tracker.py`, and the underlying `i151_engine` runtime was conducted. The bot possesses solid bitboard foundations (32-bit bitmasks, 64-bit Zobrist hashing, deterministic terminal endgame solver for $|U| \le 6$, and zero-forfeit rule compliance). However, critical algorithmic deficiencies prevent it from achieving the Grand Master benchmark targets specified in R1, R2, and R3:

1. **PIMC Minimax Lookahead & Driver Status**:
   - The tree search depth in `bot.py:212` is hardcoded to `max_search_depth = 4` (only 3 plies evaluated beyond root), failing the **5–8 plies** specification.
   - The Minimax value **does NOT drive decision-making** (`bot.py:281`): decision scoring is dominated by a static heuristic (`total_eval = h_score + norm_minimax * 0.20`), where Minimax contributes a meager 20% dampening factor.
   - The Transposition Table lacks bound flags (`EXACT`, `LOWER_BOUND`, `UPPER_BOUND`), causing unsound cutoffs in Alpha-Beta pruning, and TT best moves are not used in move ordering.

2. **R1: Resource Preservation & Wildcard Timing (8 & As)**:
   - Rank 8 wildcards are **burned prematurely early and mid round** when hand size $\ge 5$. While `card_context` applies a token penalty of `-2.0` at hand size 5–6, `score_action` awards `dump * 1.1` ($32 \times 1.1 = +35.2$), creating a net **$+33.2$ preference to burn an 8 over a normal card (e.g. 7 or 9)**.
   - Penalty dumping activates prematurely at `opp_size <= 4` or `my_size <= 4`, instead of genuine round termination (`opp_size <= 3` or `my_size <= 2`).
   - Aces are similarly expended early without tactical justification because of positive default bonuses ($+15.0$ bonus $+ 12.1$ dump points).

3. **R2: Queen Combo & 2-Player Tempo Mastery**:
   - The anti-Queen-alone 2P trap filter is rigorously enforced across Tier 1, fallback handlers, heuristic evaluation, and Minimax ordering.
   - Queen tempo combos are NOT chained into multi-card actions because `legal_actions()` in `i151_engine` only generates single-card plays; instead, Queen tempo works via sequential turns (extra turns granted via `skip_next_player = True`).
   - The decision engine is blind to follow-up capability: playing a Queen without having a matching suit/rank follow-up card results in immediate bank draw forfeiture on the next turn.

4. **R3: Bayesian Opponent Void Tracking & Starvation**:
   - `card_tracker.py` infers opponent voids solely when `curr_opp_size > self.last_opp_hand_size`, completely missing turns where the opponent drew a card and immediately played it.
   - Opponent void masks are matched with an exact mask equality bug (`(v & s_mask) == s_mask`), which fails for Ace-induced voids and fails to discount voids as the round progresses and bank cards are drawn.
   - When playing an 8, `choose_suit` bypasses Minimax search entirely (Tier 1 intercept). If the bot holds 0 cards in a suit, it assigns $-10,000.0$ penalty, refusing to impose that suit even when the opponent is 100% void and forced into bank draw penalties.

---

## 1. Current State of PIMC Minimax Engine (`bot.py` & `evaluator.py`)

### 1.1 Search Depth Analysis
- **Current Configuration**:
  - `bot.py:212`: `max_search_depth = 4`
  - In `_decide_internal`:
    ```python
    s1 = apply_action(sim_state, a)
    val = _alphabeta_search(s1, max_search_depth - 1, float("-inf"), float("inf"), 0, tt, streak_mode)
    ```
  - Root action `a` counts as ply 1; `_alphabeta_search` evaluates `depth - 1 = 3` plies deeper.
  - Total lookahead: **strictly 4 plies**.
  - Contrast with requirements: `ORIGINAL_REQUEST.md` (R2) and `SKILL.md` specify **5–8 plies**.
  - Note: `evaluator.py:503` runs an exact analytical solver `solve_exact_endgame` at `depth=12`, but this is only triggered when `total_unrevealed <= 6` (endgame with $\le 6$ cards remaining outside player's hand).

### 1.2 Does Minimax Value Drive Decisions?
- **Finding: Minimax is heavily overridden and suppressed by static heuristics.**
- In `bot.py:277-284`:
  ```python
  def evaluate_candidate(a: Action) -> tuple[float, float, str]:
      h_score, h_dump, h_key = score_action(view, a, streak_mode=streak_mode)
      c = max(1, action_counts[a])
      norm_minimax = action_values[a] / c
      total_eval = h_score + norm_minimax * 0.20
      return (total_eval, h_dump, h_key)

  return max(plays, key=evaluate_candidate)
  ```
- **Quantitative Impact**:
  - `h_score` ranges between $50.0$ and $2,500.0+$ points.
  - `norm_minimax` (expected payoff across 6 PIMC worlds) is scaled down by factor **`0.20`**.
  - For typical non-terminal moves, `norm_minimax` ranges between $-150.0$ and $+150.0$, contributing merely $\pm 10$ to $30$ points to `total_eval`.
  - Static heuristics (e.g. $+28$ for emptied, $+35.2$ for dumping an 8, $+50$ for Queen play) completely overwhelm the Minimax strategic evaluation.
  - Minimax cannot override a statically preferred bad move unless the Minimax difference exceeds $5 \times$ the heuristic difference.
  - Tier 1 intercepts immediate 1-ply finishes and `ActionType.CHOOSE_SUIT` before Minimax is even evaluated.

### 1.3 Alpha-Beta Pruning Implementation & Soundness
- Located in `bot.py:336-435` (`_alphabeta_search`).
- Standard Alpha-Beta bounding logic is implemented:
  - For MAX player: updates `alpha = max(alpha, v)`; cutoffs via `if beta <= alpha: break`.
  - For MIN player: updates `beta = min(beta, v)`; cutoffs via `if beta <= alpha: break`.
- **Transposition Table Bound Bug**:
  - In `bot.py:415` & `433`:
    ```python
    tt[z_key] = (depth, max_v, best_act)  # and (depth, min_v, best_act)
    ```
  - In `bot.py:368-371`:
    ```python
    if z_key in tt:
        cached_depth, cached_val, _ = tt[z_key]
        if cached_depth >= depth:
            return cached_val
    ```
  - **Critical Flaw**: When a beta-cutoff occurs (`v >= beta`), `max_v` is a **lower bound** (fail-high), not an exact score. Conversely, when all moves fail low (`max_v <= alpha`), it is an **upper bound**.
  - The current implementation stores all values as exact without bound flags (`FLAG_EXACT`, `FLAG_LOWER`, `FLAG_UPPER`). In subsequent node visits (especially across the 6 PIMC worlds sharing the same `tt`), this leads to **unsound pruning and incorrect evaluation**.

### 1.4 Move Ordering & Transposition Table Caching
- **Transposition Table**:
  - Uses 64-bit Zobrist hashing (`evaluator.py:82-121`), hashing hands (`p0_hand`, `p1_hand`), top card, required suit, turn player, ace effect, chaining state, and drawn state.
  - Table is re-instantiated on every `decide()` call (`tt = {}`), shared across the 6 sampled worlds.
- **Move Ordering**:
  - Implemented in `bot.py:380-398` (`move_order`):
    - Hand emptied: $+10,000.0$ (or $-10,000.0$ if ending on solitary Queen).
    - Multi-card combinations: $+200.0 \times \text{count}$.
    - Queen play: $+350.0$.
    - Eight play: $+300.0$.
    - Ace play: $+250.0$.
    - Card points: $+50.0 + 2.0 \times \sum \text{points}$.
  - **Deficiencies**:
    1. **No PV-Move / TT-Move Prioritization**: The cached `best_act` from the transposition table is never checked or prioritized during move ordering.
    2. **Blind Eight Priority**: Assigning $+300.0$ to rank 8 cards causes Minimax to search 8s before regular plays in all branches, causing unnecessary cutoffs and biasing search toward burning wildcards.

---

## 2. R1: Strategic Resource Preservation & Wildcard Timing (8 & As)

### 2.1 Premature Burning of Rank 8s (Early/Mid Round)
- **Mathematical Cause of Premature Burning**:
  - In i151 scoring, Rank 8 cards carry **32 penalty points** if left in hand.
  - In `evaluator.py:score_action` (lines 636 & 667-668):
    - Base dump score: `score += dump * 1.1` $\implies 32 \times 1.1 = \mathbf{+35.2}$.
    - `card_context` evaluation (`evaluator.py:550-560`):
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
  - **Concrete Comparison (Hand Size = 6)**:
    - Playing an 8:
      - Emptied bonus: $+28.0$
      - Dump points: $32 \times 1.1 = +35.2$
      - Card context penalty: $-2.0$
      - Remaining cards penalty: $-6.0 \times 5 = -30.0$
      - **Total Score = $+31.2$**
    - Playing a 7 (dump = 0 points):
      - Emptied bonus: $+28.0$
      - Dump points: $0.0$
      - Card context: $0.0$
      - Remaining cards penalty: $-6.0 \times 5 = -30.0$
      - **Total Score = $-2.0$**
    - **Delta**: The bot scores playing an 8 **33.2 points HIGHER** than playing a 7 when hand size is 6!
    - At hand size 7+, the penalty is only $-10.0$, so playing an 8 STILL beats playing a 7 by **$+25.2$ points**.
  - **Verdict**: The bot burns 8s as standard early/mid-round plays instead of preserving them.

### 2.2 Handling of Aces
- Aces inflict an immediate 2-card draw penalty on the opponent and carry **11 penalty points**.
- In `evaluator.py:562-571`:
  ```python
  elif card.rank == Rank.ACE:
      if view.table.ace_effect_active:
          bonus -= 10.0
      elif is_agony or opp_size <= 4:
          bonus += 30.0
      elif ace_is_tactical(view):
          bonus += 25.0
      else:
          bonus += 15.0
  ```
- Even when an Ace is NOT tactical (we have natural plays on the required suit/rank) and NOT in agony:
  - Base bonus: $+15.0$
  - Dump bonus: $11 \times 1.1 = +12.1$
  - Net boost: **$+27.1$ over regular zero-point cards**.
- Aces are consequently squandered in early rounds rather than held as tactical counters against opponent chains or stored for endgame execution.

### 2.3 Penalty Dumping Trigger Conditions
- Current activation threshold in `evaluator.py:644-650`:
  ```python
  is_agony = (
      opp_size <= 4
      or view.you.hand_size <= 4
      or streak_mode == 3
      or my_score >= 80
  )
  ```
- When `is_agony` is True:
  - `score += emptied * 22.0`
  - `score -= remaining * 14.0`
  - `score += dump * 2.2` (dumps: 8 $\implies +70.4$; Ace $\implies +24.2$; 10 $\implies +22.0$)
  - `bonus += 60.0` for 8s, `+30.0` for Aces, `+22.0` for 10s.
- **Comparison with R1 Specification**:
  - R1 specifies: "transitioning into aggressive penalty dumping only when the round is genuinely terminating (opponent hand <= 3 or self hand <= 2)."
  - In practice, when `opp_size == 4`, the round is far from over. Dumping rank 8s and Aces at `opp_size == 4` leaves the bot defenseless against subsequent opponent plays.

---

## 3. R2: Deep Minimax & 2-Player Tempo Mastery (Dames & Combos)

### 3.1 Hard Filter for Zero Queen-Alone Finishes
- In i151 2-player rules (`i151_engine.core.reducer._handle_play`), playing a Queen as the final card does not win the game; instead, the player draws 1 card from the bank and play passes to the opponent.
- **Verification of Enforcement**:
  - `evaluator.py:finishes_on_queen_two_player`:
    ```python
    def finishes_on_queen_two_player(view: PlayerView, action: Action) -> bool:
        if view.match.player_count != 2:
            return False
        if action.type == ActionType.PLAY_CARD and action.card is not None:
            return view.you.hand_size == 1 and action.card.rank == Rank.QUEEN
        if action.type == ActionType.PLAY_MULTIPLE_CARDS and action.cards:
            return view.you.hand_size == len(action.cards) and action.cards[-1].rank == Rank.QUEEN
        return False
    ```
  - `bot.py:110-112`: Safe actions filter strips out any action matching `finishes_on_queen_two_player`.
  - `bot.py:88-90`: Safe fallback in top-level exception handler.
  - `evaluator.py:601`: `score_action` returns $-10,000.0$ for Queen finishes.
  - `evaluator.py:397-400`: `solve_exact_endgame` penalizes Queen finishes with $-10,000.0$.
  - Unit test `test_solve_queen_anti_trap` passes; Tier 1 benchmark check T1.3 passes.
- **Conclusion**: The anti-Queen trap filter is 100% sound and verified.

### 3.2 2-Player Queen Tempo Dynamics & Combo Chaining
- In 2-player mode, playing a Queen activates `skip_next_player = True`. In a 2-player game, skipping the opponent cycles turn control directly back to the active player:
  $$\text{next\_idx} = (0 + 1) \pmod 2 = 1 \implies (1 + 1) \pmod 2 = 0$$
- Thus, every Queen played in 2-player grants an immediate sequential turn.
- **How Queens Are Handled**:
  - In `evaluator.py:658-666`:
    ```python
    last = cards[-1]
    if last.rank == Rank.QUEEN and view.match.player_count == 2 and remaining > 0:
        if opp_size <= 2:
            score += 75.0
        elif opp_size <= 4:
            score += 50.0
        else:
            score += 15.0
    ```
  - Anti-solitary Queen remainder penalty (`evaluator.py:677-684`): $-60.0$ if a play leaves exactly 1 Queen as the sole remaining card in hand.
- **Current Limitations in Queen Combo Chaining**:
  1. **Blindness to Follow-Up Play**:
     The bonus ($+15.0$ to $+75.0$) is awarded purely based on opponent hand size, without checking if our hand actually contains a playable follow-up card (same suit, another Queen, or an 8). If the bot plays a Queen but has no follow-up, it is forced to draw from the bank on the subsequent turn, handing initiative back to the opponent.
  2. **No Multi-Queen Tempo Horizon**:
     Holding multiple Queens (e.g. Queen of Spades + Queen of Hearts) allows chaining 2 consecutive skips before delivering a heavy card dump. The static heuristic does not value this tempo multiplier, and Minimax depth (4 plies) cannot see past the individual turns.

---

## 4. R3: Bayesian Opponent Void Tracking & Game-Theoretic Starvation

### 4.1 Card History & Opponent Void Inference
- Implemented in `card_tracker.py:48-93`.
- Tracks `seen_mask` across turns; handles deck recycling (`view.table.bank_size > self.last_bank_size`).
- **Void Detection Logic**:
  ```python
  if view.turn.is_your_turn and self.last_table_top is not None:
      if curr_opp_size > self.last_opp_hand_size:
          void_mask = 0
          if self.last_req_suit is not None:
              s_id = SUIT_TO_ID.get(self.last_req_suit, -1)
              if s_id >= 0:
                  void_mask = SUIT_MASK[s_id] | EIGHTS_MASK
          elif self.last_table_top is not None:
              top_cid = ID_BY_CARD.get(self.last_table_top, -1)
              if top_cid >= 0:
                  t_rank = CARD_RANK_ID[top_cid]
                  t_suit = CARD_SUIT_ID[top_cid]
                  if t_rank == 7:  # Ace
                      void_mask = ACES_MASK | EIGHTS_MASK
                  else:
                      void_mask = RANK_MASK[t_rank] | SUIT_MASK[t_suit] | EIGHTS_MASK

          if void_mask and void_mask not in self.opp_void_masks:
              self.opp_void_masks.append(void_mask)
  ```
- **Identified Flaws**:
  1. **Draw-and-Play Invisibility**:
     If the opponent draws a card and immediately plays a card, `curr_opp_size == self.last_opp_hand_size`. The condition `curr_opp_size > self.last_opp_hand_size` evaluates to `False`. The tracker completely misses that the opponent was void of the required suit/rank before drawing!
  2. **Static Void Persistence Without Decay**:
     When the opponent draws cards on subsequent turns, their void state may be resolved. The tracker maintains `self.opp_void_masks` indefinitely until deck recycling, erroneously treating past voids as permanent.

### 4.2 Calculation and Forcing of Starvation Suits on Rank 8 Plays
- When the bot plays an 8, `ActionType.CHOOSE_SUIT` is triggered.
- In `bot.py:122-124`:
  ```python
  choose_suit_actions = [a for a in safe_actions if a.type == ActionType.CHOOSE_SUIT]
  if choose_suit_actions:
      return best_suit_action(view, choose_suit_actions, global_tracker.opp_void_masks)
  ```
- This calls `compute_suit_pressure` in `evaluator.py:194-237`.
- **Flaws in Suit Selection**:
  1. **Minimax is Bypassed**: Suit selection is performed via a static greedy formula without Minimax lookahead.
  2. **Self-Lockout Penalty**:
     ```python
     if h_count == 0:
         if not has_another_eight:
             pressure[suit] = -10_000.0
         else:
             pressure[suit] = -50.0
         continue
     ```
     If the bot has 0 cards in that suit in hand and no other 8, it assigns $-10,000.0$, strictly forbidding that suit. It cannot recognize situations where forcing that suit guarantees opponent bank draw penalties or round victory.
  3. **Void Bitmask Matching Bug**:
     In `evaluator.py:220-223`:
     ```python
     if opp_void_masks:
         for v in opp_void_masks:
             if (v & s_mask) == s_mask:
                 p += 60.0
     ```
     - For Ace-induced voids (`void_mask = ACES_MASK | EIGHTS_MASK`), `(v & s_mask) == s_mask` is NEVER TRUE because `v & s_mask` has at most 2 bits, whereas `s_mask` has 8 bits.
     - Even for normal top-card voids, `+60.0` is an arbitrary heuristic constant that does not compute the mathematical probability $P(\text{opp void in } S \mid \text{history})$.

---

## 5. Comparative Architectural Matrix

| Component | Current Implementation | Requirement (R1/R2/R3) | Gap Assessment |
|---|---|---|---|
| **Minimax Depth** | 4 plies (`max_search_depth = 4`) | 5–8 plies | **Deficient**: Search truncated too shallowly |
| **Decision Driver** | Static heuristic ($80\%$) + Minimax ($20\%$) | Minimax is primary driver | **Severe**: Minimax output is marginalized |
| **TT Alpha-Beta Soundness** | Values cached without bound flags | `FLAG_EXACT`, `FLAG_LOWER`, `FLAG_UPPER` | **Deficient**: Leads to unsound pruning |
| **Move Ordering** | Static heuristic only; ignores TT PV move | PV-first + history heuristic | **Missing**: Misses TT best move optimization |
| **Rank 8 Wildcard Timing** | Burned when hand size $\ge 5$ (dump $+35.2$ vs penalty $-2.0$) | Retain as counter when $\ge 5$; dump when $\le 2$ or opp $\le 3$ | **Critical**: High penalty cards squandered |
| **Ace Preservation** | Played aggressively ($+27.1$ over 7) | Tactical counter / draw forcing | **Deficient**: Tactical defensive cards burned |
| **Agony Dumping Threshold** | `opp_size <= 4` or `my_size <= 4` | `opp_size <= 3` or `my_size <= 2` | **Inaccurate**: Triggers too early |
| **Queen Finish Invariant** | Hard filter active across all tiers | Hard filter active, 0 Queen finishes in 2P | **Compliant**: 100% verified |
| **Queen Tempo Chaining** | Fixed $+15$ to $+75$ bonus; no follow-up check | Evaluate follow-up chain & sequential skips | **Deficient**: Can lead to self-inflicted draw |
| **Opponent Void Detection** | Hand size delta (`curr > last`) only | Full tracking including draw-then-play & bank deltas | **Deficient**: Misses draws; static voids |
| **Starvation Suit Forcing** | Hard $-10,000$ if $h\_count=0$; static $+60$ bonus | Bayesian probability + Minimax lookahead | **Deficient**: Crude heuristic, bypasses Minimax |

---

## 6. Actionable Implementation Recommendations

1. **Amplify Search Depth to 6 Plies & Fix Alpha-Beta TT Soundness**:
   - Set `max_search_depth = 6` (or dynamic 5–8 based on time left).
   - Add TT bound flags (`FLAG_EXACT = 0`, `FLAG_LOWER = 1`, `FLAG_UPPER = 2`).
   - Store and prioritize TT PV move at index 0 in move ordering.
2. **Elevate Minimax as Primary Decision Driver**:
   - Revise decision formula in `_decide_internal`:
     $$\text{total\_eval} = \text{norm\_minimax} + 0.10 \times h\_\text{score}$$
   - Minimax expected score must be the primary sort key, with heuristics acting solely as tie-breakers.
3. **Enforce Strict R1 Resource Preservation for 8s & Aces**:
   - In `card_context`: increase penalty for playing an 8 when `my_size >= 5` to at least $-50.0$ (matching and exceeding the $+35.2$ dump gain).
   - Require `opp_size <= 3` or `my_size <= 2` for aggressive penalty dumping.
   - Restrict Ace plays to tactical counter situations (`ace_is_tactical` or agony mode).
4. **Fix R3 Void Detection & Starvation Pressure**:
   - Detect opponent draws via `table.bank_size` reduction, capturing draw-and-play turns.
   - Update `compute_suit_pressure` to evaluate true void probability and eliminate the mask matching bug.
   - Evaluate `CHOOSE_SUIT` inside Minimax lookahead rather than intercepting it with a shallow heuristic.
