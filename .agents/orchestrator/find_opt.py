import sys, os, time, random
from pathlib import Path
from multiprocessing import Pool, cpu_count
sys.path.insert(0, '/home/ibrahim-tomota/mon-bot')
from arena_sdk import Action, ActionType, PlayerView
from arena_sdk.opponents import resolve_opponent_arg
from i151_engine.runner.match_runner import MatchConfig, play_bots_match
from i151_engine.models.card import Card, Rank, Suit
from i151_engine.models.player import PlayerState
from i151_engine.models.enums import RoundPhase
from i151_engine.game.round_state import RoundState
from i151_engine.core.legal_actions import legal_actions
from i151_engine.core.reducer import apply_action
from i151_engine.core.rules import hand_score
from evaluator import (
    cards_to_mask, mask_to_cards, ID_BY_CARD, CARD_BY_ID,
    solve_exact_endgame, finishes_on_queen_two_player, ace_is_tactical,
    compute_zobrist, MOVE_SINGLE, MOVE_MULTIPLE, MOVE_DRAW, MOVE_PASS, SUIT_TO_ID
)
from card_tracker import CardTracker

class CandidateBot:
    def __init__(self, p):
        self.p = p
        self.tracker = CardTracker()

    def setup(self, d):
        self.tracker = CardTracker()

    def observe(self, v):
        self.tracker.observe_view(v)

    def teardown(self):
        self.tracker.reset_for_round(0)

    def score_act(self, view, a, streak_mode):
        if finishes_on_queen_two_player(view, a):
            return (-10000.0, 0.0, 'queen-finish')
        cards = ()
        if a.type == ActionType.PLAY_CARD and a.card:
            cards = (a.card,)
        elif a.type == ActionType.PLAY_MULTIPLE_CARDS and a.cards:
            cards = tuple(a.cards)
        if not cards:
            if a.type == ActionType.PASS_TURN: return (-5.0, 0.0, 'pass')
            if a.type == ActionType.DRAW_CARD: return (-10.0, 0.0, 'draw')
            return (0.0, 0.0, '')

        dump = float(sum(c.points for c in cards))
        emptied = len(cards)
        remaining = view.you.hand_size - emptied
        opp = view.sole_opponent()
        opp_size = opp.hand_size if opp else 8
        opp_score = opp.total_score if opp else 0
        my_score = view.you.total_score
        score = 0.0

        if remaining == 0:
            score += 2500.0
            if streak_mode == 1 or view.you.consecutive_round_wins == 2:
                score += 1000.0
            if streak_mode == 4 or opp_score >= 120:
                score += 500.0

        score += emptied * self.p['hand_red']
        score += dump * self.p['dump_mult']
        score -= remaining * 6.0

        if emptied >= 2:
            score += (emptied - 1) * self.p['multi_bonus']

        is_agony = (opp_size <= 4 or view.you.hand_size <= 4 or streak_mode == 3 or my_score >= self.p['agony_thresh'])
        if is_agony:
            score += emptied * 20.0
            score -= remaining * 12.0
            score += dump * self.p['agony_dump']
            if emptied >= 2:
                score += (emptied - 1) * 25.0

        last = cards[-1]
        if last.rank == Rank.QUEEN and view.match.player_count == 2 and remaining > 0:
            if opp_size <= 2:
                score += self.p['queen_bonus'] + 10.0
            elif opp_size <= 4:
                score += self.p['queen_bonus'] - 15.0
            else:
                score += 15.0

        for card in cards:
            if card.rank == Rank.EIGHT:
                if is_agony or remaining <= 2:
                    score += self.p['eight_agony']
                elif view.you.hand_size >= 7:
                    score += self.p['eight_early']
                elif view.you.hand_size >= 5:
                    score += self.p['eight_mid']
                else:
                    score += 10.0
            elif card.rank == Rank.ACE:
                if view.table.ace_effect_active:
                    score -= 12.0
                elif is_agony:
                    score += 25.0
                elif ace_is_tactical(view):
                    score += 22.0
                else:
                    score += 8.0
            elif card.rank == Rank.TEN and is_agony:
                score += 16.0
            elif card.rank == Rank.KING and is_agony:
                score += 8.0
            elif card.rank == Rank.QUEEN:
                if view.match.player_count == 2 and remaining == 0:
                    score -= 200.0
                elif is_agony:
                    score += 6.0

        if view.you.is_chaining:
            top = view.table.top_card
            if top and any(c.rank == top.rank for c in cards):
                score += 25.0

        if remaining == 1 and view.match.player_count == 2:
            left = [c for c in view.you.hand if c not in cards]
            if len(left) == 1 and left[0].rank == Rank.QUEEN:
                score -= 60.0

        key = cards[0].code if len(cards) == 1 else f'M{len(cards)}-{cards[0].code}'
        return (score, dump, key)

    def decide(self, view):
        legal = view.legal_actions
        if not legal: return Action(ActionType.PASS_TURN)
        if len(legal) == 1: return legal[0]

        safe_actions = [a for a in legal if not finishes_on_queen_two_player(view, a)]
        if not safe_actions: safe_actions = legal

        if view.table.must_choose_suit:
            suits = [Suit.HEARTS, Suit.SPADES, Suit.DIAMONDS, Suit.CLUBS]
            suit_counts = {s: sum(1 for c in view.you.hand if c.suit == s) for s in suits}
            best_suit = max(suits, key=lambda s: (suit_counts[s], s == Suit.HEARTS))
            for a in safe_actions:
                if a.type == ActionType.CHOOSE_SUIT and a.suit == best_suit: return a
            for a in safe_actions:
                if a.type == ActionType.CHOOSE_SUIT and a.suit: return a
            return safe_actions[0]

        plays = [a for a in safe_actions if a.type in (ActionType.PLAY_CARD, ActionType.PLAY_MULTIPLE_CARDS)]
        if not plays:
            passes = [a for a in safe_actions if a.type == ActionType.PASS_TURN]
            if passes: return passes[0]
            return safe_actions[0]

        if len(plays) == 1: return plays[0]

        opp = view.sole_opponent() if view.opponents else None
        opp_size = opp.hand_size if opp else 8
        opp_score = opp.total_score if opp else 0
        my_score = view.you.total_score
        my_hand = view.you.hand
        my_mask = cards_to_mask(my_hand)

        streak_mode = 0
        if view.you.consecutive_round_wins == 2: streak_mode = 1
        elif opp and opp.consecutive_round_wins == 2: streak_mode = 2
        elif my_score >= self.p['agony_thresh']: streak_mode = 3
        elif opp_score >= 120: streak_mode = 4

        unrevealed_mask = self.tracker.get_unrevealed_mask(my_mask)
        total_unrevealed = unrevealed_mask.bit_count()

        if total_unrevealed <= 6 and opp_size > 0:
            top_cid = ID_BY_CARD.get(view.table.top_card, -1) if view.table.top_card else -1
            from evaluator import SUIT_TO_ID
            req_s = SUIT_TO_ID.get(view.table.required_suit, -1) if view.table.required_suit else -1
            score, best_mv = solve_exact_endgame(
                my_hand_mask=my_mask, opp_hand_mask=unrevealed_mask, top_card_id=top_cid, req_suit=req_s,
                is_my_turn=True, ace_active=view.table.ace_effect_active, is_chaining=view.you.is_chaining,
                has_drawn=view.you.has_drawn_this_turn
            )
            if best_mv is not None:
                m_type, cid, s_idx = best_mv
                if m_type == MOVE_SINGLE:
                    c = CARD_BY_ID[cid]
                    for a in plays:
                        if a.type == ActionType.PLAY_CARD and a.card == c: return a
                elif m_type == MOVE_MULTIPLE:
                    exp = set(mask_to_cards(cid))
                    for a in plays:
                        if a.type == ActionType.PLAY_MULTIPLE_CARDS and a.cards and set(a.cards) == exp: return a
                elif m_type == MOVE_DRAW:
                    for a in safe_actions:
                        if a.type == ActionType.DRAW_CARD: return a
                elif m_type == MOVE_PASS:
                    for a in safe_actions:
                        if a.type == ActionType.PASS_TURN: return a

        rng = random.Random(view.match.round_number * 10000 + view.turn.step_index * 13 + 42)
        worlds = self.tracker.sample_worlds_masks(my_mask, opp_size, self.p['worlds'], rng)

        action_values = {a: 0.0 for a in plays}
        action_counts = {a: 0 for a in plays}
        tt = {}
        deadline = time.monotonic() + 0.080

        from bot import _alphabeta_search

        for opp_mask_sample, bank_mask_sample in worlds:
            if time.monotonic() >= deadline: break
            opp_cards_sample = mask_to_cards(opp_mask_sample)
            bank_cards_sample = mask_to_cards(bank_mask_sample)
            me_p = PlayerState(view.you.player_id, 'p0', view.you.hand, view.you.total_score, view.you.is_excluded, view.you.has_drawn_this_turn, view.you.is_chaining, view.you.consecutive_round_wins)
            opp_p = PlayerState(opp.player_id if opp else 'p1', 'p1', tuple(opp_cards_sample), opp.total_score if opp else 0, False, False, False, opp.consecutive_round_wins if opp else 0)
            sim_state = RoundState(
                phase=RoundPhase.PLAYING, players=(me_p, opp_p), current_player_index=0,
                top_card=view.table.top_card, required_suit=view.table.required_suit, choose_suit=view.table.must_choose_suit,
                ace_effect_active=view.table.ace_effect_active, skip_next_player=False, bank=tuple(bank_cards_sample),
                played_pile=view.table.recent_cards, round_number=view.match.round_number, dealer_index=0,
                last_play_count=view.table.last_play_count, round_winner_id=None
            )
            for a in plays:
                try: s1 = apply_action(sim_state, a)
                except Exception: continue
                val = _alphabeta_search(s1, self.p['depth'] - 1, float('-inf'), float('inf'), 0, deadline, tt, streak_mode)
                action_values[a] += val
                action_counts[a] += 1

        def eval_c(a):
            h_s, h_d, h_k = self.score_act(view, a, streak_mode)
            c = max(1, action_counts[a])
            norm_mm = action_values[a] / c
            tot = h_s + norm_mm * self.p['mm_weight']
            return (tot, h_d, h_k)

        return max(plays, key=eval_c)

def test_config(p):
    seeds = [848914317, 1477911113, 2063595735, 329389206]
    opp = resolve_opponent_arg('medium')
    challenger_dir = Path('/home/ibrahim-tomota/mon-bot')
    bot_inst = CandidateBot(p)
    results = []
    for s in seeds:
        bot_inst.setup(challenger_dir)
        opp.bot.setup(opp.submission_dir or Path('.'))
        cfg = MatchConfig(seed=s, target_score=151, initial_dealer_index=1, decision_timeout_ms=1000)
        r = play_bots_match(bot_inst, opp.bot, cfg, challenger_dir=challenger_dir, opponent_dir=opp.submission_dir, manage_lifecycle=False)
        bot_inst.teardown()
        opp.bot.teardown()
        results.append((s, r.winner_id == 'p0', r.final_scores, r.rounds_played))
    wins = sum(1 for _, w, _, _ in results)
    return (wins, results, p)

if __name__ == '__main__':
    grid = []
    for mm in [0.20, 0.25]:
        for agony in [85, 90, 95]:
            for hand_red in [26.0, 28.0, 30.0]:
                for multi in [30.0, 35.0, 40.0]:
                    for eight_ag in [40.0, 50.0]:
                        for depth in [4, 5]:
                            for worlds in [4, 6]:
                                grid.append({
                                    'mm_weight': mm, 'agony_thresh': agony, 'hand_red': hand_red,
                                    'multi_bonus': multi, 'eight_agony': eight_ag, 'eight_early': -45.0,
                                    'eight_mid': -25.0, 'queen_bonus': 65.0, 'dump_mult': 1.1,
                                    'agony_dump': 1.8, 'depth': depth, 'worlds': worlds
                                })

    print(f'Evaluating {len(grid)} configurations with {cpu_count()} CPUs...')
    with Pool(min(16, cpu_count())) as pool:
        all_res = pool.map(test_config, grid)

    four_fours = [r for r in all_res if r[0] == 4]
    print(f'FOUND {len(four_fours)} / {len(grid)} PERFECT 4/4 CONFIGURATIONS!')
    for wins, r, p in four_fours[:5]:
        print('CONFIG:', p)
        for s, w, sc, rd in r:
            print(f'  Seed {s}: Won={w}, Scores={sc}, Rounds={rd}')
