import sys
sys.path.insert(0, "/home/ibrahim-tomota/mon-bot")
#!/usr/bin/env python3
"""Diagnostic script for Tuning Explorer 2: experiments on weights and heuristics."""

import sys
import time
import random
from pathlib import Path
from arena_sdk import Action, ActionType, PlayerView, MatchConfig
from arena_sdk.opponents import resolve_opponent_arg
from i151_engine.runner.match_runner import play_bots_match
from i151_engine.models.card import Card, Rank, Suit
from i151_engine.models.player import PlayerState
from i151_engine.models.enums import RoundPhase
from i151_engine.game.round_state import RoundState
from i151_engine.core.legal_actions import legal_actions
from i151_engine.core.reducer import apply_action
from i151_engine.core.rules import hand_score

import bot
import evaluator
from evaluator import (
    CARD_BY_ID, ID_BY_CARD, CARD_RANK_ID, CARD_SUIT_ID,
    cards_to_mask, mask_to_cards, finishes_on_queen_two_player,
    best_suit_action, solve_exact_endgame, score_action
)
from card_tracker import global_tracker

SEEDS = [848914317, 1477911113, 2063595735, 329389206]

def make_decider(minimax_weight=0.5, early_eight_penalty=0.0, ace_retention_penalty=0.0, dump_weight=1.5, score_threshold=100):
    def decide_custom(view: PlayerView, legal_actions_list: list[Action], time_left_ms: int | None = None) -> Action:
        if not legal_actions_list:
            raise RuntimeError("No legal actions")
        if len(legal_actions_list) == 1:
            return legal_actions_list[0]

        global_tracker.update_from_view(view)

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
            return best_suit_action(view, choose_suit_actions, global_tracker.opp_void_masks)

        plays = [a for a in safe_actions if a.type in (ActionType.PLAY_CARD, ActionType.PLAY_MULTIPLE_CARDS)]
        if not plays:
            passes = [a for a in safe_actions if a.type == ActionType.PASS_TURN]
            return passes[0] if passes else safe_actions[0]

        if len(plays) == 1:
            return plays[0]

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
        elif my_score >= score_threshold:
            streak_mode = 3
        elif opp_score >= 120:
            streak_mode = 4

        # Tier 2 Endgame solver (|U| <= 6)
        unrevealed_mask = global_tracker.get_unrevealed_mask(my_mask)
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
                if m_type == evaluator.MOVE_SINGLE:
                    c = CARD_BY_ID[cid]
                    for a in plays:
                        if a.type == ActionType.PLAY_CARD and a.card == c:
                            return a
                elif m_type == evaluator.MOVE_MULTIPLE:
                    expected_cards = set(mask_to_cards(cid))
                    for a in plays:
                        if a.type == ActionType.PLAY_MULTIPLE_CARDS and a.cards and set(a.cards) == expected_cards:
                            return a

        # Tier 3 PIMC
        t0 = time.monotonic()
        rem_ms = time_left_ms if time_left_ms is not None else 1000
        budget_s = min(bot.DECISION_BUDGET_MS * 0.001, rem_ms * 0.001 * 0.70)
        deadline = t0 + max(budget_s, 0.035)

        num_worlds = 10 if total_unrevealed <= 12 else 8
        rng = random.Random(view.match.round_number * 10000 + view.turn.step_index * 13 + 42)
        worlds = global_tracker.sample_worlds_masks(my_mask, opp_size, num_worlds, rng)

        action_values = {a: 0.0 for a in plays}
        tt = {}
        max_search_depth = 8 if total_unrevealed <= 10 else 6

        for opp_mask_sample, bank_mask_sample in worlds:
            if time.monotonic() >= deadline:
                break
            opp_cards_sample = mask_to_cards(opp_mask_sample)
            bank_cards_sample = mask_to_cards(bank_mask_sample)

            me_p = PlayerState(view.you.player_id, "p0", view.you.hand, view.you.total_score, view.you.is_excluded, view.you.has_drawn_this_turn, view.you.is_chaining, view.you.consecutive_round_wins)
            opp_p = PlayerState(opp.player_id if opp else "p1", "p1", tuple(opp_cards_sample), opp.total_score if opp else 0, False, False, False, opp.consecutive_round_wins if opp else 0)

            sim_state = RoundState(
                phase=RoundPhase.PLAYING,
                players=(me_p, opp_p),
                current_player_index=0,
                top_card=view.table.top_card,
                required_suit=view.table.required_suit,
                choose_suit=view.table.must_choose_suit,
                ace_effect_active=view.table.ace_effect_active,
                skip_next_player=False,
                bank=tuple(bank_cards_sample),
                played_pile=view.table.recent_cards,
                round_number=view.match.round_number,
                dealer_index=0,
                last_play_count=view.table.last_play_count,
                round_winner_id=None,
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
                if last_c.rank == Rank.EIGHT and (opp_size <= 3 or streak_mode == 3):
                    p += 400.0
                if last_c.rank == Rank.ACE:
                    p += 250.0
                p += sum(c.points for c in cards)
                return p

            ordered_plays = sorted(plays, key=order_priority, reverse=True)

            for a in ordered_plays:
                if time.monotonic() >= deadline:
                    break
                try:
                    s1 = apply_action(sim_state, a)
                except Exception:
                    continue
                val = bot._alphabeta_search(s1, max_search_depth - 1, float("-inf"), float("inf"), my_idx=0, deadline=deadline, tt=tt, streak_mode=streak_mode)
                action_values[a] += val

        def evaluate_candidate(a: Action) -> tuple[float, float, str]:
            h_score, h_dump, h_key = custom_score_action(view, a, streak_mode=streak_mode, early_eight_penalty=early_eight_penalty, ace_retention_penalty=ace_retention_penalty, dump_weight=dump_weight)
            norm_minimax = action_values[a] / max(1, len(worlds))
            total_eval = h_score + norm_minimax * minimax_weight
            return (total_eval, h_dump, h_key)

        return max(plays, key=evaluate_candidate)

    return decide_custom

def custom_score_action(view: PlayerView, action: Action, streak_mode: int, early_eight_penalty: float, ace_retention_penalty: float, dump_weight: float):
    if finishes_on_queen_two_player(view, action):
        return (-10_000.0, 0.0, "queen-finish-trap")

    cards = ()
    if action.type == ActionType.PLAY_CARD and action.card is not None:
        cards = (action.card,)
    elif action.type == ActionType.PLAY_MULTIPLE_CARDS and action.cards:
        cards = tuple(action.cards)

    if not cards:
        if action.type == ActionType.PASS_TURN:
            return (-5.0, 0.0, "pass")
        if action.type == ActionType.DRAW_CARD:
            return (-10.0, 0.0, "draw")
        return (0.0, 0.0, "action")

    dump = float(sum(c.points for c in cards))
    emptied = len(cards)
    remaining = view.you.hand_size - emptied
    opp = view.sole_opponent()
    opp_size = opp.hand_size if opp else 8
    opp_score = opp.total_score if opp else 0
    my_score = view.you.total_score
    score = 0.0

    if remaining == 0:
        score += 2_000.0
        if streak_mode == 1 or view.you.consecutive_round_wins == 2:
            score += 1_000.0
        if streak_mode == 4 or opp_score >= 120:
            score += 500.0

    score += emptied * 32.0  # Encourage emptying hand slightly more
    score += dump * dump_weight
    score -= remaining * 6.0

    if opp_size <= 4:
        score += emptied * 20.0
        score -= remaining * 12.0
        if streak_mode == 3 or my_score >= 100:
            score += dump * 2.0

    if view.you.hand_size <= 4:
        score += emptied * 15.0

    last = cards[-1]
    if last.rank == Rank.QUEEN and view.match.player_count == 2 and remaining > 0:
        if opp_size <= 2:
            score += 55.0
        elif opp_size <= 4:
            score += 35.0
        else:
            score += 8.0

    for card in cards:
        bonus = 0.0
        if card.rank == Rank.EIGHT:
            if opp_size <= 4 or remaining <= 2 or streak_mode == 3 or my_score >= 100:
                bonus += 45.0
            elif view.you.hand_size >= 7:
                bonus -= early_eight_penalty
            elif view.you.hand_size >= 5:
                bonus -= early_eight_penalty * 0.5
            else:
                bonus += 10.0
        elif card.rank == Rank.ACE:
            if view.table.ace_effect_active:
                bonus -= 12.0
            elif evaluator.ace_is_tactical(view):
                bonus += 20.0
            elif opp_size <= 4 or my_score >= 100:
                bonus += 15.0
            else:
                bonus -= ace_retention_penalty
        elif card.rank == Rank.QUEEN and view.match.player_count == 2 and remaining == 0:
            bonus -= 200.0
        score += bonus

    if view.you.is_chaining:
        top = view.table.top_card
        if top is not None and any(c.rank == top.rank for c in cards):
            score += 20.0

    if remaining == 1 and view.match.player_count == 2:
        left = list(view.you.hand)
        for c in cards:
            if c in left: left.remove(c)
        if len(left) == 1 and left[0].rank == Rank.QUEEN:
            score -= 40.0

    key = cards[0].code if len(cards) == 1 else f"M{len(cards)}-{cards[0].code}"
    return (score, dump, key)

class CustomBot:
    def __init__(self, decider):
        self.decider = decider
    def setup(self, s_dir):
        bot.setup(s_dir)
    def decide(self, view, legal_actions_list, time_left_ms=None):
        return self.decider(view, legal_actions_list, time_left_ms)
    def observe(self, view):
        bot.observe(view)
    def teardown(self):
        bot.teardown()

def run_tests():
    configs = [
        ("Base (w=0.05, early_8_pen=45, dump=1.0)", make_decider(0.05, early_eight_penalty=45.0, dump_weight=1.0, score_threshold=115)),
        ("Config A (w=0.25, early_8_pen=15, dump=1.2)", make_decider(0.25, early_eight_penalty=15.0, dump_weight=1.2, score_threshold=100)),
        ("Config B (w=0.50, early_8_pen=0, dump=1.5)", make_decider(0.50, early_eight_penalty=0.0, dump_weight=1.5, score_threshold=100)),
        ("Config C (w=0.75, early_8_pen=0, dump=1.5)", make_decider(0.75, early_eight_penalty=0.0, dump_weight=1.5, score_threshold=100)),
        ("Config D (w=1.00, early_8_pen=0, dump=1.5)", make_decider(1.00, early_eight_penalty=0.0, dump_weight=1.5, score_threshold=100)),
    ]

    opp_med = resolve_opponent_arg('medium')
    opp_basic = resolve_opponent_arg('basic')

    for name, decider in configs:
        b = CustomBot(decider)
        print(f"\n=================== Testing {name} ===================")
        
        # Test 4 Seeds
        seed_wins = 0
        for s in SEEDS:
            b.setup(Path('.'))
            opp_med.bot.setup(opp_med.submission_dir or Path('.'))
            cfg = MatchConfig(seed=s, target_score=151, initial_dealer_index=1, decision_timeout_ms=1000)
            res = play_bots_match(b, opp_med.bot, cfg, challenger_name='mon-bot', opponent_name=opp_med.name, opponent_id=opp_med.opponent_id, challenger_dir=Path('.'), opponent_dir=opp_med.submission_dir, manage_lifecycle=False)
            b.teardown()
            opp_med.bot.teardown()
            won = res.winner_id == 'p0'
            if won: seed_wins += 1
            print(f"  Seed {s}: {'WON' if won else 'LOST'} ({res.final_scores}) in {res.rounds_played} rounds")
        print(f"  --> Seeds Won: {seed_wins}/4")

        # Test 20 games vs basic
        basic_wins = 0
        for s in range(42, 42 + 20):
            dealer = 1 if (s % 2 == 0) else 0
            b.setup(Path('.'))
            opp_basic.bot.setup(opp_basic.submission_dir or Path('.'))
            cfg = MatchConfig(seed=s, target_score=151, initial_dealer_index=dealer, decision_timeout_ms=1000)
            res = play_bots_match(b, opp_basic.bot, cfg, challenger_name='mon-bot', opponent_name=opp_basic.name, opponent_id=opp_basic.opponent_id, challenger_dir=Path('.'), opponent_dir=opp_basic.submission_dir, manage_lifecycle=False)
            b.teardown()
            opp_basic.bot.teardown()
            if res.winner_id == 'p0': basic_wins += 1
        print(f"  --> vs Basic (20G): {basic_wins}/20 ({basic_wins/20*100:.1f}%)")

if __name__ == '__main__':
    run_tests()
