# i151 Arena Authoritative Specification Report

**Date**: 2026-09-09  
**Auditor**: Spec Miner (`survey_explorer_r2_2`)  
**Specification Sources**:
- `arena` CLI binary (`/home/ibrahim-tomota/.platformio/penv/bin/arena`)
- `arena_sdk` v0.2.10 (`/home/ibrahim-tomota/.platformio/penv/lib/python3.14/site-packages/arena_sdk`)
- `i151_engine` v0.2.4 (`/home/ibrahim-tomota/.platformio/penv/lib/python3.14/site-packages/i151_engine`)
- `ORIGINAL_REQUEST.md` & `i151-master-bot` Skill

---

## Executive Summary
This document provides the definitive, ground-truth specification for the i151 Arena competition, verified by direct static code analysis of `i151_engine` and `arena_sdk`, combined with dynamic execution probes. All mechanics, state transitions, scoring penalties, timing constraints, and packaging rules are authoritatively documented below.

---

## Features Discovered

| # | Category | Feature | Description | Inputs | Outputs | Error Behavior | Discovered Via |
|---|----------|---------|-------------|--------|---------|----------------|----------------|
| 1 | CLI | `arena match` | Run matches between a bot and an opponent | `bot`, `--vs`, `--games`, `--seed`, `--random`, `--starter`, `--p0-first-rate`, `--format`, `--decision-timeout-ms`, `--isolated` | Match results, table/summary/json output, optional replay JSON | Code 1 on error, forfeit on illegal move/timeout | `arena match --help`, `arena_sdk/cli.py:429` |
| 2 | CLI | `arena test` | Smoke test bot against `builtin:random` (seed 42, target 151, max 40 rounds) | `bot`, optional `--seed`, `--model` | "OK — match terminé sans forfait" or failure reason | Code 1 if result != "normal" | `arena test --help`, `arena_sdk/cli.py:835` |
| 3 | CLI | `arena pack` | Pack bot and local dependencies into a valid submission ZIP | `directory`, `-o`, `--entry`, `--lang`, `--model`, `--simulations`, `--determinizations`, `--budget-ms` | `<name>-submission.zip` with AST module closure | `PackError` on missing imports, non-root entry, invalid syntax | `arena pack --help`, `arena_sdk/pack.py:530` |
| 4 | CLI | `arena init` | Initialize new bot template project | `directory`, `-l {python,c,java,node}`, `--force` | Scaffolding files (`bot.py`, `README.md`, etc.) | Error if dir exists without `--force` | `arena init --help`, `arena_sdk/init_project.py` |
| 5 | Engine / Deck | 32-Card Standard Deck | 4 suits (Spades, Hearts, Diamonds, Clubs), 8 ranks (7, 8, 9, 10, Jack, Queen, King, Ace). Dealt 8 cards per player (2-3 players) or 7 (4 players). | `player_count`, `seed` | Deal tuples per player, remaining cards to bank (16 in 2P) | `ValueError` if `cards_per_player` invalid | `i151_engine/models/card.py`, `i151_engine/core/deck.py` |
| 6 | Engine / Moves | Single Card Play | Play card matching top card rank or suit, or play 8, or follow `required_suit` | `Action.play_card(card)` | Card moved to played pile, becomes `top_card` | `IllegalActionError` / Immediate match forfeit if invalid | `i151_engine/core/rules.py:23`, `reducer.py:20` |
| 7 | Engine / Moves | Rank Chaining | If top card has same rank as played card, or if card played is 8, and player has another card of that rank, player continues turn | Consecutive `Action.play_card(c)` or `Action.pass_turn()` | `is_chaining=True`, player retains turn | Forfeit if non-matching rank played while chaining | `i151_engine/core/reducer.py:56-70`, `legal_actions.py:17` |
| 8 | Engine / Special | Rank 8 Wildcard & Suit Choice | 8 can be played on ANY card (even Ace or another 8). Resets Ace effect. Triggers suit selection step. | `Action.play_card(8)` followed by `Action.choose_suit(s)` | `required_suit = s`, `choose_suit = False`, turn passes | Forfeit if bot returns `chosen_suit` inside `play_card` | `i151_engine/core/reducer.py:141-161`, `models/card.py:86` |
| 9 | Engine / Special | Ace Attack & Counter | Playing an Ace forces next player to answer with Ace, 8, or draw 2 cards | `Action.play_card(Ace)` | `ace_effect_active = True`, next player restricted | Opponent draws 2 & loses turn if cannot counter | `i151_engine/core/reducer.py:111,162`, `models/card.py:88` |
| 10| Engine / Special | 2P Queen Skip & Combos | Queen skips next player. In 2P mode, player skips opponent and immediately plays again | `Action.play_card(Queen)` | `skip_next_player = True`, next player is self | Normal play rules for subsequent card | `i151_engine/core/reducer.py:164,181` |
| 11| Engine / Invariant | 2P Solitary Queen Trap | Playing Queen as the single last card in 2P mode does NOT win; forces 1 card draw and passes turn | `Action.play_card(Queen)` with `hand_size == 1` | Draw 1 card from bank, `has_drawn_this_turn = True`, pass turn | Cannot win on solitary Queen in 2P | `i151_engine/core/reducer.py:85-94` |
| 12| Engine / Draw | Bank Draw & Play/Pass | If unplayed, player can draw 1 card (2 if Ace active). If drawn card playable, may play or pass. | `Action.draw_card()`, then optional `Action.play_card()` or `Action.pass_turn()` | Hand size +1 (+2 if Ace), `has_drawn_this_turn = True` | Forfeit if draw attempted twice in one turn | `i151_engine/core/reducer.py:106-134`, `legal_actions.py:27` |
| 13| Engine / Bank | Bank Refill from Played Pile | When bank size < draw count, `played_pile` is appended in FIFO order without shuffling | Internal engine draw trigger | Bank replenished, `played_pile = ()` | If both bank & pile empty, `top_card = None` | `i151_engine/core/reducer.py:190-206` |
| 14| Scoring | Hand Penalty Points | At round end, losers add point sum of remaining hand cards to total score | Hand cards: 8=32, A=11, 10=10, 9=9, 7=7, K=4, Q=3, J=2 | `total_score += sum(points)` | Elimination if score >= 151 (`target_score`) | `i151_engine/models/card.py:49`, `core/scoring.py:102` |
| 15| Scoring | Consecutive Win Bonus | Player winning 3 rounds in a row receives -10 points on total score | 3 consecutive round wins | `total_score -= 10`, streak resets to 0 | Streak resets to 0 immediately if opponent wins | `i151_engine/core/scoring.py:152-179` |
| 16| Scoring | Match Elimination & Winner | Match ends when all but 1 player reach >= 151 points, or round ends with winner | Player scores | Match status FINISHED, lowest score wins | Forfeit penalty applies current hand points to violator | `i151_engine/core/scoring.py:36-70,121-135` |
| 17| Protocol / Bot | Bot Lifecycle API | Four standardized methods: `setup`, `decide`, `observe`, `teardown` | `PlayerView`, `list[Action]`, `time_left_ms` | `Action` | `decide` is mandatory; others optional | `arena_sdk/loader.py:35-99`, `i151_engine/bots/protocol.py` |
| 18| Protocol / Observation | Passive Observer Hook | Inactive bots receive `observe(view)` after each atomic opponent move | `PlayerView` (with `table.last_play_cards`) | None (internal state update) | Errors in `observe` are silently caught | `i151_engine/runner/match_runner.py:285-299` |
| 19| Security / Sandbox | Sandbox Import Enforcement | Worker execution isolates bot; network, IPC, OS, and system hooks blocked | AST walk + runtime `sys.modules` purge | Verified safe environment | Immediate crash / forfeit if forbidden module loaded | `arena_sdk/ipc/sandbox.py:16-68` |
| 20| Packaging | AST Local Closure & Whitelist | AST imports tracked from `bot.py`; pip packages strictly whitelisted | `project_dir` | Clean zip with only root modules + whitelisted deps | Non-whitelisted requirements stripped | `arena_sdk/pack.py:14-24,269-316` |

---

## Edge Cases

| # | Feature | Input | Observed Behavior |
|---|---------|-------|-------------------|
| 1 | 2P Queen Finish | Hand = `[Queen]`, table = `King` (same suit) | Hand empties, but engine detects 2P Queen finish: forces drawing 1 card from bank, sets `has_drawn_this_turn=True`, passes turn to opponent (unless drawn card is playable on Queen). Round does NOT end. |
| 2 | Multi-Player Queen Finish | Hand = `[Queen]`, 3 active players, table = `King` (same suit) | Hand empties. Since `active_player_count == 3` (not 2), Queen trap does NOT trigger. Round ENDS immediately with player winning 0 penalty. |
| 3 | Queen -> 8 Combo | Hand = `[Queen, 8]`, table = `King` (matching Queen suit) | Step 1: Plays Queen -> skips opponent, player gets immediate turn with hand `[8]`. Step 2: Plays 8 on Queen -> hand becomes empty. Last card was 8 (not Queen). Round ENDS immediately with player winning. |
| 4 | Solitary 8 Finish | Hand = `[8]`, table = any card | Plays 8. Hand becomes 0. Round ENDS immediately. Player wins. No suit selection prompt is generated because round phase changes to ENDED. |
| 5 | Chaining 8s | Hand = `[8S, 8D]`, table = `King of Hearts` | Step 1: Plays 8S. Engine sets `is_chaining=True` and `choose_suit=True`. Legal actions include `Action.play_card(8D)` AND `Action.choose_suit(...)` for all 4 suits. Player can choose to chain the second 8 or choose a suit. |
| 6 | Suit Choice Action Format | Bot returns `Action.play_card(8, chosen_suit=Suit.SPADES)` | `legal_actions` only provides `Action.play_card(8)` with `chosen_suit=None`. Equality fails (`act in legal` evaluates False), causing an IMMEDIATE MATCH FORFEIT. Suit must be chosen in the follow-up step via `Action.choose_suit(Suit.SPADES)`. |
| 7 | Ace Attack vs Counter Ace | Player 0 plays `Ace of Hearts`. Player 1 has `Ace of Spades`, `King of Hearts`. | Player 1 cannot play `King of Hearts` despite matching suit. Only `Ace of Spades` or `drawCard` are legal. Playing `Ace of Spades` counters the attack, passing `ace_effect_active=True` back to Player 0. Draw penalty remains 2 (does not stack to 4). |
| 8 | Ace Attack vs 8 Neutralizer | Player 0 plays `Ace of Hearts`. Player 1 plays `8 of Diamonds`. | 8 is legal on Ace. Engine resets `ace_effect_active=False` and triggers suit choice. The Ace attack is completely neutralized; next player is not forced to draw 2. |
| 9 | Ace Draw Penalty | Player 0 plays `Ace`. Player 1 has no Ace/8 and draws. | Player 1 draws 2 cards from bank. `ace_effect_active` resets to False. Player 1's turn terminates immediately without any opportunity to play a card. |
| 10| Ace Draw with 1 Bank Card | Player 0 plays `Ace`. Bank has 1 card, played pile is empty. Player 1 draws. | Player 1 draws the 1 available card (bank becomes 0). Turn terminates immediately. `ace_effect_active` resets to False. No error occurs. |
| 11| Bank Exhaustion & Refill | Bank = 0, played pile = `[9D, 10D]`. Player draws. | Engine appends `played_pile` into `bank` in original FIFO order without shuffling. Player draws `9D`. Bank has 1 card, `played_pile` becomes empty. |
| 12| Total Card Exhaustion | Bank = 0, played pile = 0. Player draws. | Player draws 0 cards. `has_drawn_this_turn` becomes True. `top_card` becomes `None` (table opened). Player can play any card or pass turn. |
| 13| Drawing when Playable | Player has playable cards in hand, has not drawn yet. | `Action.draw_card()` is explicitly present in `legal_actions`. Drawing is permitted even when valid plays exist. |
| 14| Consecutive Win Resets | Player A wins Round 1 & 2 (`consecutive=2`). Player B wins Round 3. | Player A's streak is broken and reset to 0. Player B's streak becomes 1. Neither receives the -10 bonus. |
| 15| Forfeit Scoring Penalty | Player forfeits during active round (e.g. timeout or illegal action). | Forfeiting player's current hand cards are summed and added as a penalty to their `total_score`. Opponent's score remains unchanged. Opponent is awarded the match win. |

---

## Detailed Rules & Constraints Breakdown

### 1. Card Inventory & Penalty Scoring
The i151 deck consists of exactly 32 cards (4 suits $\times$ 8 ranks). Card values and penalties are:

$$\begin{array}{|l|c|c|l|}
\hline
\textbf{Rank} & \textbf{Symbol} & \textbf{Penalty Points} & \textbf{Special Mechanic} \\
\hline
\text{Eight} & 8 & \mathbf{32\text{ pts}} & \text{Universal wildcard; cancels Ace; sets required suit; chains} \\
\text{Ace} & \text{A} & \mathbf{11\text{ pts}} & \text{Forces next player to counter with Ace/8 or draw 2 cards} \\
\text{Ten} & \text{T} & \mathbf{10\text{ pts}} & \text{High-value penalty card; no special effect} \\
\text{Nine} & 9 & \mathbf{9\text{ pts}} & \text{Standard card} \\
\text{Seven} & 7 & \mathbf{7\text{ pts}} & \text{Lowest numerical rank; standard card} \\
\text{King} & \text{K} & \mathbf{4\text{ pts}} & \text{Face card; safe to hold} \\
\text{Queen} & \text{Q} & \mathbf{3\text{ pts}} & \text{Skips next player (extra turn in 2P); solitary finish forbidden} \\
\text{Jack} & \text{J} & \mathbf{2\text{ pts}} & \text{Lowest penalty card (safest card in hand)} \\
\hline
\end{array}$$

Total points in deck: $4 \times (32 + 11 + 10 + 9 + 7 + 4 + 3 + 2) = 4 \times 78 = \mathbf{312\text{ points}}$.

### 2. Elimination & Match Target Score
- Default match target score: **151 points**.
- When a player's accumulated penalty points reach or exceed 151 (`total_score >= 151`), they are excluded.
- The match terminates when all opponents are eliminated, or after the round where target score is reached. The winner is the player with the lowest score.

### 3. Timing, Latency, and Step Budgets
- **Per-decision timeout**: **1000 ms** (enforced via `signal.setitimer(ITIMER_REAL)` with `SIGALRM`).
- **Target decision latency**: Strictly **< 50 ms average**, **< 300 ms peak**.
- **Match timeout**: **600,000 ms** (10 minutes).
- **Max steps per round**: **500 steps** (exceeding triggers `max_steps` forfeit).
- **Max rounds per match**: **200 rounds** (or 40 in test mode).

### 4. Arena Packaging & Submission Constraints
- Command: `arena pack .` generates `<directory>-submission.zip`.
- Single Python entry point: `bot.py` at root.
- All imported local modules are statically resolved via AST traversal and bundled at the root of the ZIP.
- Third-party packages in `requirements.txt` are filtered against an authoritative whitelist:
  - `numpy`, `scikit-learn`, `sklearn`, `joblib`, `onnxruntime`, `torch`, `pandas`.
  - Any non-whitelisted packages (e.g. `i151-arena-sdk`) are automatically stripped.
- Forbidden runtime imports:
  - `os`, `sys`, `subprocess`, `socket`, `multiprocessing`, `asyncio`, `signal`, `ctypes`, `builtins`, `importlib`.
  - Violations result in container/sandbox initialization failures.

---

## Authoritative Signatures & Interfaces

### Bot Protocol (`bot.py`)
```python
from pathlib import Path
from typing import Sequence
from arena_sdk import Action, PlayerView

def setup(submission_dir: Path) -> None:
    """Optional: Precompute tables, load models, initialize trackers."""
    ...

def decide(view: PlayerView, legal_actions: list[Action], time_left_ms: int) -> Action:
    """Mandatory: Return exactly one Action present in legal_actions within time_left_ms."""
    ...

def observe(view: PlayerView) -> None:
    """Optional: Passive callback invoked after each opponent move to update tracking."""
    ...

def teardown() -> None:
    """Optional: Clean up state, close resources."""
    ...
```
