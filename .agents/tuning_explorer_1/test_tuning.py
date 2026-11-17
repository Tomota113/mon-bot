import random
import time
import sys
from pathlib import Path

sys.path.insert(0, '/home/ibrahim-tomota/mon-bot')
from arena_sdk.opponents import resolve_opponent_arg
from arena_sdk import Action, ActionType, PlayerView
from i151_engine.models.card import Card, Rank, Suit
from i151_engine.models.player import PlayerState
from i151_engine.models.enums import RoundPhase
from i151_engine.game.round_state import RoundState
from i151_engine.core.legal_actions import legal_actions
from i151_engine.core.reducer import apply_action
from i151_engine.core.rules import hand_score
from i151_engine.runner.match_runner import MatchConfig, play_bots_match
from i151_engine.bots.protocol import Bot

import evaluator
from evaluator import (
    CARD_BY_ID, ID_BY_CARD, CARD_RANK_ID, CARD_SUIT_ID, CARD_POINTS,
    RANK_MASK, SUIT_MASK, EIGHTS_MASK, QUEENS_MASK, ACES_MASK, ALL_CARDS_MASK,
    MOVE_SINGLE, MOVE_MULTIPLE, MOVE_DRAW, MOVE_PASS, MOVE_CHOOSE_SUIT,
    cards_to_mask, mask_to_cards, mask_points, playable_cards_mask,
    compute_zobrist, compute_suit_pressure, best_suit_action,
    finishes_on_queen_two_player, solve_exact_endgame
)
from card_tracker import CardTracker, global_tracker
import bot

class TunedBot(Bot):
    def __init__(self, minimax_weight=0.25, dump_weight=1.5, eight_bonus_mode='balanced', agony_thresh=95):
        self.minimax_weight = minimax_weight
        self.dump_weight = dump_weight
        self.eight_bonus_mode = eight_bonus_mode
        self.agony_thresh = agony_thresh
        self.tracker = CardTracker()

    def setup(self, submission_dir: Path | None = None) -> None:
        self.tracker.reset_for_round(0)

    def observe(self, view: PlayerView) -> None:
        try:
            self.tracker.update_from_view(view)
        except Exception:
            pass

    def teardown(self) -> None:
        self.tracker.reset_for_round(0)

    def decide(self, view: PlayerView, legal_actions_list: list[Action], time_left_ms: int | None = None) -> Action:
        if not legal_actions_list:
            raise RuntimeError("Aucune action légale.")
        if len(legal_actions_list) == 1:
            return legal_actions_list[0]

        self.tracker.update_from_view(view)

        # Tier 1
        safe_actions = [a for a in legal_actions_list if not finishes_on_queen_two_player(view, a)]
        if not safe_actions:
            safe_actions = legal_actions_list

        for a in safe_actions:
            if a.type == ActionType.PLAY_CARD and view.you.hand_size == 1 and a.card:
                if a.card.rank != Rank.QUEEN or view.match.player_count > 2:
                    return a
            elif a.type == ActionType.PLAY_MULTIPLE_CARDS and a.cards:
                if len(a.cards) == view.you.hand_size and (a.cards[-1].rank != Rank.QUEEN or view.match.player_count > 2):
                    return a

        choose_suit_actions = [a for a in safe_actions if a.type == ActionType.CHOOSE_SUIT]
        if choose_suit_actions:
            return best_suit_action(view, choose_suit_actions, self.tracker.opp_void_masks)

        plays = [a for a in safe_actions if a.type in (ActionType.PLAY_CARD, ActionType.PLAY_MULTIPLE_CARDS)]
        if not plays:
            passes = [a for a in safe_actions if a.type == ActionType.PASS_TURN]
            if passes: return passes[0]
            return safe_actions[0]

        if len(plays) == 1:
            return plays[0]

        # Dynamic Game Modes
        opp = view.sole_opponent() if view.opponents else None
        opp_size = opp.hand_size if opp else 8
        opp_score = opp.total_score if opp else 0
        my_score = view.you.total_score
        my_hand = view.you.hand
        my_mask = cards_to_mask(my_hand)

        streak_mode = 0
        if view.you.consecutive_round_wins == 2:
            streak_mode = 1
        elif opp and opp.consecutive_round_wins == 2:
            streak_mode = 2
        elif my_score >= self.agony_thresh:
            streak_mode = 3
        elif opp_score >= 120:
            streak_mode = 4

        # Tier 2: Exact solver
        unrevealed_mask = self.tracker.get_unrevealed_mask(my_mask)
        total_unrevealed = unrevealed_mask.bit_count()

        if total_unrevealed <= 6 and opp_size > 0:
            top_cid = ID_BY_CARD.get(view.table.top_card, -1) if view.table.top_card else -1
            req_s = -1
            if view.table.required_suit is not None:
                from evaluator import SUIT_TO_ID
                req_s = SUIT_TO_ID.get(view.table.required_suit, -1)

            score, best_mv = solve_exact_endgame(
                my_hand_mask=my_mask,
                opp_hand_mask=unrevealed_mask,
                top_card_id=top_cid,
                req_suit=req_s,
                is_my_turn=True,
                ace_active=view.table.ace_effect_active,
                is_chaining=view.you.is_chaining,
                has_drawn=view.you.has_drawn_this_turn,
            )
            if best_mv is not None:
                m_type, cid, s_idx = best_mv
                if m_type == MOVE_SINGLE:
                    c = CARD_BY_ID[cid]
                    for a in plays:
                        if a.type == ActionType.PLAY_CARD and a.card == c:
                            return a
                elif m_type == MOVE_MULTIPLE:
                    expected_cards = set(mask_to_cards(cid))
                    for a in plays:
                        if a.type == ActionType.PLAY_MULTIPLE_CARDS and a.cards and set(a.cards) == expected_cards:
                            return a

        # Tier 3: PIMC Minimax
        t0 = time.monotonic()
        rem_ms = time_left_ms if time_left_ms is not None else 1000
        budget_s = min(0.150, rem_ms * 0.001 * 0.70)
        deadline = t0 + max(budget_s, 0.035)

        num_worlds = 10 if total_unrevealed <= 12 else 8
        rng = random.Random(view.match.round_number * 10000 + view.turn.step_index * 13 + 42)
        worlds = self.tracker.sample_worlds_masks(my_mask, opp_size, num_worlds, rng)

        action_values = {a: 0.0 for a in plays}
        tt = {}
        max_search_depth = 8 if total_unrevealed <= 10 else 6

        for opp_mask_sample, bank_mask_sample in worlds:
            if time.monotonic() >= deadline:
                break
            opp_cards_sample = mask_to_cards(opp_mask_sample)
            bank_cards_sample = mask_to_cards(bank_mask_sample)

            me_p = PlayerState(
                view.you.player_id, "p0", view.you.hand, view.you.total_score,
                view.you.is_excluded, view.you.has_drawn_this_turn, view.you.is_chaining,
                view.you.consecutive_round_wins,
            )
            opp_p = PlayerState(
                opp.player_id if opp else "p1", "p1", tuple(opp_cards_sample),
                opp.total_score if opp else 0, False, False, False,
                opp.consecutive_round_wins if opp else 0,
            )

            sim_state = RoundState(
                phase=RoundPhase.PLAYING, players=(me_p, opp_p), current_player_index=0,
                top_card=view.table.top_card, required_suit=view.table.required_suit,
                choose_suit=view.table.must_choose_suit, ace_effect_active=view.table.ace_effect_active,
                skip_next_player=False, bank=tuple(bank_cards_sample),
                played_pile=view.table.recent_cards, round_number=view.match.round_number,
                dealer_index=0, last_play_count=view.table.last_play_count, round_winner_id=None,
            )

            def order_priority(action: Action) -> float:
                cards = action.cards if action.type == ActionType.PLAY_MULTIPLE_CARDS and action.cards else ((action.card,) if action.card else ())
                if not cards: return 0.0
                p = 0.0
                last_c = cards[-1]
                if len(cards) == len(my_hand) and (last_c.rank != Rank.QUEEN or view.match.player_count > 2):
                    return 100_000.0
                if last_c.rank == Rank.QUEEN and view.match.player_count == 2:
                    p += 500.0
                if last_c.rank == Rank.EIGHT and (opp_size <= 4 or streak_mode == 3):
                    p += 400.0
                if last_c.rank == Rank.ACE:
                    p += 250.0
                p += sum(c.points for c in cards)
                return p

            ordered_plays = sorted(plays, key=order_priority, reverse=True)

            for a in ordered_plays:
                if time.monotonic() >= deadline: break
                try:
                    s1 = apply_action(sim_state, a)
                except Exception:
                    continue
                val = bot._alphabeta_search(
                    s1, max_search_depth - 1, float("-inf"), float("inf"),
                    my_idx=0, deadline=deadline, tt=tt, streak_mode=streak_mode,
                )
                action_values[a] += val

        def custom_score_action(a: Action) -> tuple[float, float, str]:
            if finishes_on_queen_two_player(view, a):
                return (-10_000.0, 0.0, "queen-finish-trap")

            cards = ()
            if a.type == ActionType.PLAY_CARD and a.card is not None:
                cards = (a.card,)
            elif a.type == ActionType.PLAY_MULTIPLE_CARDS and a.cards:
                cards = tuple(a.cards)

            if not cards:
                if a.type == ActionType.PASS_TURN: return (-5.0, 0.0, "pass")
                if a.type == ActionType.DRAW_CARD: return (-10.0, 0.0, "draw")
                return (0.0, 0.0, "action")

            dump = float(sum(c.points for c in cards))
            emptied = len(cards)
            remaining = view.you.hand_size - emptied
            score = 0.0

            if remaining == 0:
                score += 2_000.0
                if streak_mode == 1 or view.you.consecutive_round_wins == 2:
                    score += 1_000.0
                if streak_mode == 4 or opp_score >= 120:
                    score += 500.0

            score += emptied * 28.0
            score += dump * self.dump_weight
            score -= remaining * 6.0

            if opp_size <= 4:
                score += emptied * 18.0
                score -= remaining * 10.0
                score += dump * 0.8
                if streak_mode == 3 or my_score >= self.agony_thresh:
                    score += dump * 1.5

            if view.you.hand_size <= 4:
                score += emptied * 12.0

            last = cards[-1]
            if last.rank == Rank.QUEEN and view.match.player_count == 2 and remaining > 0:
                if opp_size <= 2: score += 55.0
                elif opp_size <= 4: score += 35.0
                else: score += 8.0

            for card in cards:
                bonus = 0.0
                if card.rank == Rank.EIGHT:
                    if opp_size <= 4 or remaining <= 2 or streak_mode == 3 or my_score >= self.agony_thresh:
                        bonus += 42.0
                    elif self.eight_bonus_mode == 'balanced':
                        # Do not overly penalize 8s
                        if view.you.hand_size >= 7:
                            bonus -= 10.0
                        elif view.you.hand_size >= 5:
                            bonus -= 5.0
                        else:
                            bonus += 10.0
                    elif self.eight_bonus_mode == 'aggressive':
                        bonus += 20.0
                elif card.rank == Rank.ACE:
                    if view.table.ace_effect_active:
                        bonus -= 12.0
                    elif evaluator.ace_is_tactical(view):
                        bonus += 22.0
                    elif opp_size <= 4:
                        bonus += 15.0
                elif card.rank == Rank.QUEEN and view.match.player_count == 2 and remaining == 0:
                    bonus -= 200.0
                score += bonus

            if view.you.is_chaining:
                top = view.table.top_card
                if top is not None and any(card.rank == top.rank for card in cards):
                    score += 20.0

            if remaining == 1 and view.match.player_count == 2:
                left = list(view.you.hand)
                for c in cards:
                    if c in left: left.remove(c)
                if len(left) == 1 and left[0].rank == Rank.QUEEN:
                    score -= 40.0

            key = cards[0].code if len(cards) == 1 else f"M{len(cards)}-{cards[0].code}"
            return (score, dump, key)

        def evaluate_candidate(a: Action) -> tuple[float, float, str]:
            h_score, h_dump, h_key = custom_score_action(a)
            norm_minimax = action_values[a] / max(1, len(worlds))
            total_eval = h_score + norm_minimax * self.minimax_weight
            return (total_eval, h_dump, h_key)

        return max(plays, key=evaluate_candidate)

if __name__ == '__main__':
    seeds = [848914317, 1477911113, 2063595735, 329389206]
    for mm_w in [0.05, 0.15, 0.25, 0.35, 0.50]:
        for d_w in [1.0, 1.3, 1.6]:
            for e_mode in ['balanced', 'aggressive']:
                bot_inst = TunedBot(minimax_weight=mm_w, dump_weight=d_w, eight_bonus_mode=e_mode, agony_thresh=95)
                opp = resolve_opponent_arg('medium')
                wins = 0
                results = []
                for s in seeds:
                    config = MatchConfig(seed=s, target_score=151, initial_dealer_index=1)
                    res = play_bots_match(bot_inst, opp.bot, config, challenger_dir=Path('.'), opponent_dir=opp.submission_dir)
                    if res.winner_id == 'p0': wins += 1
                    results.append((s, res.winner_id, res.final_scores))
                print(f"MM_W={mm_w:4.2f}, D_W={d_w:3.1f}, E_MODE={e_mode:<10} -> WINS: {wins}/4 | {results}")
