# Handoff Report — Spec Miner (survey_explorer_r2_2)

## 1. Observation
1. **Engine & SDK Location**:
   - `arena` CLI binary: `/home/ibrahim-tomota/.platformio/penv/bin/arena`
   - `arena_sdk` package: `/home/ibrahim-tomota/.platformio/penv/lib/python3.14/site-packages/arena_sdk/`
   - `i151_engine` package: `/home/ibrahim-tomota/.platformio/penv/lib/python3.14/site-packages/i151_engine/`
2. **Card Definitions & Penalties** (`i151_engine/models/card.py:49-58`):
   - `_POINTS = {Rank.EIGHT: 32, Rank.ACE: 11, Rank.QUEEN: 3, Rank.KING: 4, Rank.JACK: 2, Rank.SEVEN: 7, Rank.NINE: 9, Rank.TEN: 10}`
   - Standard 32-card deck: 4 suits (Spades, Hearts, Diamonds, Clubs) $\times$ 8 ranks. Total penalty points = 312.
3. **Legal Actions & Move Equality Trap** (`i151_engine/core/legal_actions.py:9-39`, `runner/match_runner.py:212-214`):
   - In `legal_actions(state)`: Only generates `Action.play_card(card)` (with `chosen_suit=None`), `Action.choose_suit(suit)`, `Action.draw_card()`, `Action.pass_turn()`.
   - In `match_runner.py:212-214`: `if action not in legal: return _forfeit_result(match, opponent_id, pid, steps, "forfeit", recorder)`.
   - Direct probe result: `Action.play_card(8, chosen_suit=HEARTS) in [Action.play_card(8)]` evaluates to `False`. Returning an action with `chosen_suit` embedded in `play_card` causes an immediate match forfeit. Suit choice must occur on the subsequent step via `Action.choose_suit`.
4. **2-Player Queen Trap** (`i151_engine/core/reducer.py:85-94`):
   - When a player empties their hand (`not updated.hand`) and `len(active) == 2` and `cards[-1].rank == Rank.QUEEN`:
     ```python
     bank, drawn = _draw_from_bank(new_state.bank, new_state.played_pile, 1)
     updated = updated.add_cards(drawn)
     updated = replace(updated, has_drawn_this_turn=True, is_chaining=False)
     ...
     return _next_player(new_state, drawn=True)
     ```
   - Direct execution probe confirmed: `Queen finish phase: RoundPhase.PLAYING`, `p0 hand size after Queen play: 1`, `round winner: None`.
5. **Ace Attack, Blocking, & Draw Rules** (`i151_engine/core/reducer.py:111-125, 162-163`, `models/card.py:88-89`):
   - `count = 2 if state.ace_effect_active else 1`.
   - `if other.rank == Rank.ACE: return self.rank in (Rank.ACE, Rank.EIGHT)`.
   - Countering with an Ace deflects the penalty (does not stack to 4). Countering with an 8 resets `ace_effect_active=False` (cancels attack). Drawing 2 cards on Ace terminates the turn immediately.
6. **Timeouts & Constraints** (`i151_engine/runner/config.py:7-17`, `runner/match_runner.py:166-208`):
   - `decision_timeout_ms = 1000`, enforced via `signal.setitimer(ITIMER_REAL)` and `SIGALRM`.
   - Target decision latency: `< 50 ms average`, `< 300 ms max`.
   - Match timeout: `600_000 ms` (10 minutes). Max steps per round: `500`. Max rounds: `200`.
7. **Packaging & Sandbox** (`arena_sdk/pack.py:14-27, 269-316`, `arena_sdk/ipc/sandbox.py:16-68`):
   - Whitelisted packages: `numpy`, `scikit-learn`, `sklearn`, `joblib`, `onnxruntime`, `torch`, `pandas`.
   - Non-whitelisted dependencies in `requirements.txt` are stripped.
   - Forbidden imports in sandbox: `os`, `sys`, `subprocess`, `socket`, `multiprocessing`, `asyncio`, `signal`, `ctypes`, etc.

## 2. Logic Chain
1. *From Observation 3*: The engine strictly validates `action in legal_actions` using object equality (`dataclass` fields). Since `legal_actions` always generates `Action.play_card` with `chosen_suit=None`, any bot returning `play_card(..., chosen_suit=...)` or `play_multiple_cards(...)` will fail membership and immediately forfeit the match. Therefore, all bot actions must be strictly selected from `legal_actions`.
2. *From Observation 4*: In 2-player mode, emptying one's hand with a Queen triggers an explicit branch that draws 1 card from the bank and sets `has_drawn_this_turn=True`, preventing round termination. Therefore, a bot must never play a Queen when `view.you.hand_size == 1` unless no other play exists and drawing is not an option.
3. *From Observation 2 & 5*: An 8 carries a 32-point penalty, but can cancel an active Ace and change suits to force opponent voids. An Ace carries an 11-point penalty and forces a 2-card draw if not answered. Therefore, late-round card dumping must prioritize shedding 8s and Aces before opponent goes out, while preserving them early for tactical disruption.
4. *From Observation 6*: Decisions exceeding 1000 ms trigger `SIGALRM` and an immediate timeout forfeit. The target average is < 50 ms. Therefore, the search engine must employ an adaptive wall-clock cutoff (hard clamp at ~150 ms) to guarantee 0 timeouts.

## 3. Caveats
- The engine supports up to 4 players, but arena matches are primarily 2-player head-to-head (`p0` vs `p1`). All 2-player specific rules (Queen combo extra turn, Queen solitary finish trap) apply specifically to `len(active) == 2`.
- When the bank runs out, the engine replenishes the bank from the played pile in sequential FIFO order without shuffling. This makes the deck deterministically predictable if card order in the played pile is tracked.

## 4. Conclusion
All authoritative specifications, card mechanics, scoring rules, 2P Queen dynamics, Ace counters, bank refill behaviors, and CLI constraints have been exhaustively probed, verified against code and dynamic execution, and documented in `spec_report.md`. The findings directly dictate the architecture and safeguards needed for the ELO 1900+ bot.

## 5. Verification Method
1. **Smoke test**:
   ```bash
   arena test bot.py
   ```
   Must print: `OK — match terminé sans forfait` and exit with code 0.
2. **Match test vs basic**:
   ```bash
   arena match bot.py --vs basic --games 5 --format summary
   ```
   Must execute without timeouts or forfeits.
3. **Packaging test**:
   ```bash
   arena pack .
   arena test mon-bot-submission.zip
   ```
   Must successfully generate `mon-bot-submission.zip` and pass the test.
4. **Inspect report**:
   Verify complete rules tables in `/home/ibrahim-tomota/mon-bot/.agents/survey_explorer_r2_2/spec_report.md`.
