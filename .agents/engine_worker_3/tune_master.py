import sys
import time
import random
from pathlib import Path
from multiprocessing import Pool

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

from evaluator import (
    CARD_BY_ID, ID_BY_CARD, CARD_RANK_ID, CARD_SUIT_ID, CARD_POINTS,
    RANK_MASK, SUIT_MASK, EIGHTS_MASK, QUEENS_MASK, ACES_MASK, ALL_CARDS_MASK,
    MOVE_SINGLE, MOVE_MULTIPLE, MOVE_DRAW, MOVE_PASS,
    cards_to_mask, mask_to_cards, mask_points, playable_cards_mask,
    compute_zobrist, compute_suit_pressure, best_suit_action,
    finishes_on_queen_two_player, solve_exact_endgame, ace_is_tactical
)
from card_tracker import CardTracker

class MasterBot(Bot):
    def __init__(self,
                 mm_weight=0.25,
                 dump_mult=1.1,
                 agony_dump=1.7,
                 eight_early=-35.0,
                 eight_mid=-15.0,
                 eight_agony=45.0,
                 multi_bonus=32.0,
                 hand_red_bonus=30.0,
                 queen_skip_bonus=60.0,
                 agony_thresh=90):
        self.mm_weight = mm_weight
        self.dump_mult = dump_mult
        self.agony_dump = agony_dump
        self.eight_early = eight_early
        self.eight_mid = eight_mid
        self.eight_agony = eight_agony
        self.multi_bonus = multi_bonus
        self.hand_red_bonus = hand_red_bonus
        self.queen_skip_bonus = queen_skip_bonus
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

    def card_ctx(self, view: PlayerView, card: Card, remaining_after: int, streak_mode: int) -> float:
        opp = view.sole_opponent()
        opp_size = opp.hand_size if opp else 8
        bonus = 0.0
        my_size = view.you.hand_size
        my_score = view.you.total_score
        is_agony = (opp_size <= 4 or my_size <= 4 or remaining_after <= 2 or streak_mode == 3 or my_score >= self.agony_thresh)

        if card.rank == Rank.EIGHT:
            if is_agony or remaining_after <= 2:
                bonus += self.eight_agony
            elif my_size >= 7:
                bonus += self.eight_early
            elif my_size >= 5:
                bonus += self.eight_mid
            else:
                bonus += 10.0
        elif card.rank == Rank.ACE:
            if view.table.ace_effect_active:
                bonus -= 12.0
            elif is_agony:
                bonus += 25.0
            elif ace_is_tactical(view):
                bonus += 22.0
            else:
                bonus += 8.0
        elif card.rank == Rank.TEN:
            if is_agony:
                bonus += 16.0
        elif card.rank == Rank.KING:
            if is_agony:
                bonus += 8.0
        elif card.rank == Rank.QUEEN:
            if view.match.player_count == 2 and remaining_after == 0:
                bonus -= 200.0
            elif is_agony:
                bonus += 6.0
        return bonus

    def score_act(self, view: PlayerView, action: Action, streak_mode: int) -> tuple[float, float, str]:
        if finishes_on_queen_two_player(view, action):
            return (-10000.0, 0.0, "queen-finish")
        cards = ()
        if action.type == ActionType.PLAY_CARD and action.card is not None:
            cards = (action.card,)
        elif action.type == ActionType.PLAY_MULTIPLE_CARDS and action.cards:
            cards = tuple(action.cards)
        if not cards:
            if action.type == ActionType.PASS_TURN: return (-5.0, 0.0, "pass")
            if action.type == ActionType.DRAW_CARD: return (-10.0, 0.0, "draw")
            return (0.0, 0.0, "")

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

        score += emptied * self.hand_red_bonus
        score += dump * self.dump_mult
        score -= remaining * 6.0

        if emptied >= 2:
            score += (emptied - 1) * self.multi_bonus

        is_agony = (opp_size <= 4 or view.you.hand_size <= 4 or streak_mode == 3 or my_score >= self.agony_thresh)
        if is_agony:
            score += emptied * 20.0
            score -= remaining * 12.0
            score += dump * self.agony_dump
            if emptied >= 2:
                score += (emptied - 1) * 25.0

        last = cards[-1]
        if last.rank == Rank.QUEEN and view.match.player_count == 2 and remaining > 0:
            if opp_size <= 2:
                score += self.queen_skip_bonus + 10.0
            elif opp_size <= 4:
                score += self.queen_skip_bonus - 15.0
            else:
                score += 15.0

        for card in cards:
            score += self.card_ctx(view, card, remaining, streak_mode)

        if view.you.is_chaining:
            top = view.table.top_card
            if top is not None and any(card.rank == top.rank for card in cards):
                score += 25.0

        if remaining == 1 and view.match.player_count == 2:
            left = list(view.you.hand)
            for c in cards:
                if c in left: left.remove(c)
            if len(left) == 1 and left[0].rank == Rank.QUEEN:
                score -= 60.0

        key = cards[0].code if len(cards) == 1 else f"M{len(cards)}-{cards[0].code}"
        return (score, dump, key)

    def decide(self, view: PlayerView, legal_actions_list: list[Action], time_left_ms: int | None = None) -> Action:
        if not legal_actions_list:
            raise RuntimeError("No legal actions")
        if len(legal_actions_list) == 1:
            return legal_actions_list[0]

        self.tracker.update_from_view(view)
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
                elif m_type == MOVE_DRAW:
                    for a in safe_actions:
                        if a.type == ActionType.DRAW_CARD: return a
                elif m_type == MOVE_PASS:
                    for a in safe_actions:
                        if a.type == ActionType.PASS_TURN: return a

        num_worlds = 6
        rng = random.Random(view.match.round_number * 10000 + view.turn.step_index * 13 + 42)
        worlds = self.tracker.sample_worlds_masks(my_mask, opp_size, num_worlds, rng)

        action_values: dict[Action, float] = {a: 0.0 for a in plays}
        action_counts: dict[Action, int] = {a: 0 for a in plays}
        tt: dict[int, tuple[int, float, Action | None]] = {}
        max_search_depth = 5

        deadline = time.monotonic() + 0.10

        for opp_mask_sample, bank_mask_sample in worlds:
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

            for a in plays:
                try:
                    s1 = apply_action(sim_state, a)
                except Exception:
                    continue
                from bot import _alphabeta_search
                val = _alphabeta_search(s1, max_search_depth - 1, float("-inf"), float("inf"), 0, deadline, tt, streak_mode)
                action_values[a] += val
                action_counts[a] += 1

        def eval_candidate(a: Action) -> tuple[float, float, str]:
            h_score, h_dump, h_key = self.score_act(view, a, streak_mode=streak_mode)
            c = max(1, action_counts[a])
            norm_minimax = action_values[a] / c
            total = h_score + norm_minimax * self.mm_weight
            return (total, h_dump, h_key)

        return max(plays, key=eval_candidate)

def test_seed(args):
    params, seed = args
    challenger = MasterBot(**params)
    opp = resolve_opponent_arg('medium')
    challenger_dir = Path('/home/ibrahim-tomota/mon-bot')
    challenger.setup(challenger_dir)
    opp.bot.setup(opp.submission_dir or Path('.'))
    config = MatchConfig(seed=seed, target_score=151, initial_dealer_index=1, decision_timeout_ms=1000)
    res = play_bots_match(
        challenger,
        opp.bot,
        config,
        challenger_name="mon-bot",
        opponent_name=opp.name,
        opponent_id=opp.opponent_id,
        challenger_dir=challenger_dir,
        opponent_dir=opp.submission_dir,
        manage_lifecycle=False,
    )
    challenger.teardown()
    opp.bot.teardown()
    won = (res.winner_id == "p0")
    return (seed, won, res.final_scores, res.rounds_played)

def test_config(params):
    seeds = [848914317, 1477911113, 2063595735, 329389206]
    results = [test_seed((params, s)) for s in seeds]
    wins = sum(1 for r in results if r[1])
    return (wins, results, params)

if __name__ == '__main__':
    # Test combinations
    trials = []
    for mm in [0.15, 0.25, 0.35]:
        for eight_early in [-35.0, -45.0]:
            for eight_mid in [-15.0, -25.0]:
                for agony_dump in [1.5, 1.8]:
                    for multi_bonus in [30.0, 40.0]:
                        for agony_thresh in [85, 95]:
                            trials.append({
                                'mm_weight': mm,
                                'dump_mult': 1.1,
                                'agony_dump': agony_dump,
                                'eight_early': eight_early,
                                'eight_mid': eight_mid,
                                'eight_agony': 45.0,
                                'multi_bonus': multi_bonus,
                                'hand_red_bonus': 30.0,
                                'queen_skip_bonus': 60.0,
                                'agony_thresh': agony_thresh,
                            })

    print(f"Testing {len(trials)} parameter combinations...")
    with Pool(8) as pool:
        results = pool.map(test_config, trials)
    
    four_wins = [r for r in results if r[0] == 4]
    print(f"Found {len(four_wins)} combinations that achieved 4/4 wins!")
    for wins, res, p in four_wins[:5]:
        print(f"\nWinning Config (4/4):")
        print(f"  Params: {p}")
        for r in res:
            print(f"    Seed {r[0]}: Won={r[1]}, Scores={r[2]}, Rounds={r[3]}")
