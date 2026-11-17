"""Bitboard Engine, Transposition Table, Exact Endgame Solver & Heuristic Evaluator for i151."""

from __future__ import annotations

import random
from collections import Counter
from typing import Sequence
from arena_sdk import Action, ActionType, PlayerView
from i151_engine.models.card import Card, Rank, Suit

# ---------------------------------------------------------------------------
# Constants & Bitboard Representations
# ---------------------------------------------------------------------------

RANK_LIST: tuple[Rank, ...] = (
    Rank.SEVEN,   # 0
    Rank.EIGHT,   # 1
    Rank.NINE,    # 2
    Rank.TEN,     # 3
    Rank.JACK,    # 4
    Rank.QUEEN,   # 5
    Rank.KING,    # 6
    Rank.ACE,     # 7
)

RANK_TO_ID: dict[Rank, int] = {r: i for i, r in enumerate(RANK_LIST)}
ID_TO_RANK: tuple[Rank, ...] = RANK_LIST

SUIT_LIST: tuple[Suit, ...] = (
    Suit.SPADES,    # 0
    Suit.HEARTS,    # 1
    Suit.DIAMONDS,  # 2
    Suit.CLUBS,     # 3
)

SUIT_TO_ID: dict[Suit, int] = {s: i for i, s in enumerate(SUIT_LIST)}
ID_TO_SUIT: tuple[Suit, ...] = SUIT_LIST

CARD_BY_ID: tuple[Card, ...] = tuple(
    Card(rank=RANK_LIST[r], suit=SUIT_LIST[s])
    for r in range(8)
    for s in range(4)
)

ID_BY_CARD: dict[Card, int] = {c: i for i, c in enumerate(CARD_BY_ID)}

CARD_RANK_ID: tuple[int, ...] = tuple(r for r in range(8) for _ in range(4))
CARD_SUIT_ID: tuple[int, ...] = tuple(s for _ in range(8) for s in range(4))
CARD_POINTS: tuple[int, ...] = tuple(CARD_BY_ID[i].points for i in range(32))

RANK_MASK: tuple[int, ...] = tuple(0xF << (r * 4) for r in range(8))
SUIT_MASK: tuple[int, ...] = tuple(
    sum(1 << ((r << 2) | s) for r in range(8))
    for s in range(4)
)

EIGHTS_MASK: int = RANK_MASK[1]
QUEENS_MASK: int = RANK_MASK[5]
ACES_MASK: int = RANK_MASK[7]
ALL_CARDS_MASK: int = (1 << 32) - 1

MOVE_SINGLE = 1
MOVE_MULTIPLE = 2
MOVE_DRAW = 3
MOVE_PASS = 4
MOVE_CHOOSE_SUIT = 5

# ---------------------------------------------------------------------------
# Zobrist Hashing Constants (64-bit)
# ---------------------------------------------------------------------------
_rng = random.Random(0x151_B07_C0DE)
Z_P0_HAND: tuple[int, ...] = tuple(_rng.getrandbits(64) for _ in range(32))
Z_P1_HAND: tuple[int, ...] = tuple(_rng.getrandbits(64) for _ in range(32))
Z_TOP_CARD: tuple[int, ...] = tuple(_rng.getrandbits(64) for _ in range(33))
Z_REQ_SUIT: tuple[int, ...] = tuple(_rng.getrandbits(64) for _ in range(5))
Z_TURN: tuple[int, ...] = tuple(_rng.getrandbits(64) for _ in range(2))
Z_ACE_EFFECT: tuple[int, ...] = tuple(_rng.getrandbits(64) for _ in range(2))
Z_CHAINING: tuple[int, ...] = tuple(_rng.getrandbits(64) for _ in range(2))
Z_HAS_DRAWN: tuple[int, ...] = tuple(_rng.getrandbits(64) for _ in range(2))


def compute_zobrist(
    p0_hand: int,
    p1_hand: int,
    top_card_id: int,
    req_suit: int,
    current_player: int,
    ace_active: bool,
    is_chaining: bool,
    has_drawn: bool,
) -> int:
    """Compute 64-bit Zobrist hash key for game state."""
    key = Z_TURN[current_player]
    if ace_active:
        key ^= Z_ACE_EFFECT[1]
    if is_chaining:
        key ^= Z_CHAINING[1]
    if has_drawn:
        key ^= Z_HAS_DRAWN[1]

    top_idx = top_card_id if top_card_id >= 0 else 32
    key ^= Z_TOP_CARD[top_idx]

    suit_idx = req_suit if req_suit >= 0 else 4
    key ^= Z_REQ_SUIT[suit_idx]

    m0 = p0_hand
    while m0:
        lsb = m0 & -m0
        cid = lsb.bit_length() - 1
        key ^= Z_P0_HAND[cid]
        m0 ^= lsb

    m1 = p1_hand
    while m1:
        lsb = m1 & -m1
        cid = lsb.bit_length() - 1
        key ^= Z_P1_HAND[cid]
        m1 ^= lsb

    return key


# ---------------------------------------------------------------------------
# Fast Bitboard Operations
# ---------------------------------------------------------------------------

def cards_to_mask(cards: Sequence[Card]) -> int:
    mask = 0
    for c in cards:
        cid = ID_BY_CARD.get(c)
        if cid is not None:
            mask |= (1 << cid)
    return mask


def mask_to_cards(mask: int) -> list[Card]:
    result: list[Card] = []
    m = mask
    while m:
        lsb = m & -m
        cid = lsb.bit_length() - 1
        result.append(CARD_BY_ID[cid])
        m ^= lsb
    return result


def mask_points(mask: int) -> int:
    pts = 0
    m = mask
    while m:
        lsb = m & -m
        cid = lsb.bit_length() - 1
        pts += CARD_POINTS[cid]
        m ^= lsb
    return pts


def playable_cards_mask(
    hand_mask: int,
    top_card_id: int,
    req_suit: int,
    ace_effect_active: bool,
    is_chaining: bool,
) -> int:
    if not hand_mask:
        return 0

    if ace_effect_active:
        return hand_mask & (ACES_MASK | EIGHTS_MASK)

    if req_suit >= 0:
        return hand_mask & (SUIT_MASK[req_suit] | EIGHTS_MASK)

    if top_card_id < 0:
        return hand_mask

    top_rank = CARD_RANK_ID[top_card_id]
    top_suit = CARD_SUIT_ID[top_card_id]

    if is_chaining:
        return hand_mask & RANK_MASK[top_rank]

    if top_rank == 7:  # Top card is an Ace
        return hand_mask & (ACES_MASK | EIGHTS_MASK)

    return hand_mask & (RANK_MASK[top_rank] | SUIT_MASK[top_suit] | EIGHTS_MASK)


# ---------------------------------------------------------------------------
# Suit Starvation Pressure Model (Famine des Couleurs)
# ---------------------------------------------------------------------------

def compute_suit_pressure(
    my_hand_mask: int,
    seen_mask: int,
    opp_hand_size: int,
    opp_void_masks: list[int] | None = None,
) -> dict[Suit, float]:
    """Calculate game-theoretic suit starvation pressure."""
    has_another_eight = bool(my_hand_mask & EIGHTS_MASK)
    pressure: dict[Suit, float] = {}

    for s_idx, suit in enumerate(SUIT_LIST):
        s_mask = SUIT_MASK[s_idx]
        h_count = (my_hand_mask & s_mask).bit_count()
        t_count = (seen_mask & s_mask).bit_count()
        u_count = 8 - h_count - t_count

        if h_count == 0:
            if not has_another_eight:
                pressure[suit] = -10_000.0
            else:
                pressure[suit] = -50.0
            continue

        # Holding multiple cards of this suit is great for chaining/dumping
        p = h_count * 25.0 + t_count * 2.5

        # Opponent void: guaranteed forced bank draw!
        if opp_void_masks:
            for v in opp_void_masks:
                if (v & s_mask) == s_mask:
                    p += 90.0

        # Scarcity: if few remain unrevealed, opponent likely doesn't have it
        if u_count <= 0:
            p += 45.0
        elif u_count <= 1 and h_count >= 2:
            p += 30.0

        # Queen in hand with this suit: enables immediate skip follow-up!
        if my_hand_mask & (QUEENS_MASK & s_mask):
            p += 30.0

        pressure[suit] = p

    return pressure


def best_suit_action(
    view: PlayerView,
    actions: list[Action],
    opp_void_masks: list[int] | None = None,
    full_seen_mask: int = 0,
) -> Action:
    my_mask = cards_to_mask(view.you.hand)
    # Use full seen mask from tracker if available, otherwise table recent
    seen_mask = full_seen_mask if full_seen_mask else (cards_to_mask(view.table.recent_cards) | cards_to_mask(view.table.last_play_cards))
    opp = view.sole_opponent()
    opp_size = opp.hand_size if opp else 8
    pressure = compute_suit_pressure(my_mask, seen_mask, opp_size, opp_void_masks)

    return max(
        actions,
        key=lambda a: (
            pressure.get(a.chosen_suit, -10_000.0) if a.chosen_suit is not None else -10_000.0,
            a.chosen_suit.value if a.chosen_suit is not None else "",
        ),
    )


# ---------------------------------------------------------------------------
# Queen Finish Anti-Trap Guard
# ---------------------------------------------------------------------------

def finishes_on_queen_two_player(view: PlayerView, action: Action) -> bool:
    if view.match.player_count != 2:
        return False
    if action.type == ActionType.PLAY_CARD and action.card is not None:
        return view.you.hand_size == 1 and action.card.rank == Rank.QUEEN
    if action.type == ActionType.PLAY_MULTIPLE_CARDS and action.cards:
        return view.you.hand_size == len(action.cards) and action.cards[-1].rank == Rank.QUEEN
    return False


# ---------------------------------------------------------------------------
# Exact Analytical Terminal Endgame Solver (|U| <= 6)
# ---------------------------------------------------------------------------

def solve_exact_endgame(
    my_hand_mask: int,
    opp_hand_mask: int,
    top_card_id: int,
    req_suit: int,
    is_my_turn: bool,
    ace_active: bool = False,
    is_chaining: bool = False,
    has_drawn: bool = False,
) -> tuple[float, tuple[int, int, int] | None]:
    """Exhaustive deterministic Minimax solver for endgame (|U| <= 6, 0 bank)."""
    memo: dict[int, tuple[float, tuple[int, int, int] | None]] = {}

    def minimax(
        p0_hand: int,
        p1_hand: int,
        top_cid: int,
        r_suit: int,
        turn: int,
        ace: bool,
        chaining: bool,
        drawn: bool,
        depth: int,
        alpha: float,
        beta: float,
    ) -> float:
        if not p0_hand:
            return 10000.0 + mask_points(p1_hand) * 25.0
        if not p1_hand:
            return -10000.0 - mask_points(p0_hand) * 30.0

        if depth <= 0:
            return (p1_hand.bit_count() - p0_hand.bit_count()) * 50.0 + (mask_points(p1_hand) - mask_points(p0_hand)) * 2.0

        z_key = compute_zobrist(p0_hand, p1_hand, top_cid, r_suit, turn, ace, chaining, drawn)
        if z_key in memo:
            return memo[z_key][0]

        curr_hand = p0_hand if turn == 0 else p1_hand
        p_mask = playable_cards_mask(curr_hand, top_cid, r_suit, ace, chaining)

        moves: list[tuple[int, int, int]] = []

        m = p_mask
        while m:
            lsb = m & -m
            cid = lsb.bit_length() - 1
            rank = CARD_RANK_ID[cid]
            if rank == 1:
                rem_h = curr_hand ^ (1 << cid)
                chosen_any = False
                for s_idx in range(4):
                    if rem_h & SUIT_MASK[s_idx]:
                        moves.append((MOVE_SINGLE, cid, s_idx))
                        chosen_any = True
                if not chosen_any:
                    for s_idx in range(4):
                        moves.append((MOVE_SINGLE, cid, s_idx))
            else:
                moves.append((MOVE_SINGLE, cid, -1))
            m ^= lsb

        for r_idx in range(8):
            r_cards = curr_hand & RANK_MASK[r_idx]
            if r_cards.bit_count() >= 2:
                first_playable = r_cards & p_mask
                if first_playable:
                    if r_idx == 1:
                        rem_h = curr_hand ^ r_cards
                        for s_idx in range(4):
                            if rem_h & SUIT_MASK[s_idx]:
                                moves.append((MOVE_MULTIPLE, r_cards, s_idx))
                    else:
                        moves.append((MOVE_MULTIPLE, r_cards, -1))

        if top_cid >= 0:
            if drawn or chaining:
                moves.append((MOVE_PASS, 0, -1))
            else:
                moves.append((MOVE_DRAW, 0, -1))
        else:
            if drawn or chaining:
                moves.append((MOVE_PASS, 0, -1))
            elif not moves:
                moves.append((MOVE_DRAW, 0, -1))

        if not moves:
            moves.append((MOVE_PASS, 0, -1))

        is_max = (turn == 0)
        best_val = float("-inf") if is_max else float("inf")
        best_mv = None

        for mv in moves:
            m_type, cid, s_idx = mv

            next_p0 = p0_hand
            next_p1 = p1_hand
            next_top = top_cid
            next_req = r_suit
            next_turn = 1 - turn
            next_ace = False
            next_chain = False
            next_drawn = False

            if m_type == MOVE_SINGLE:
                rank = CARD_RANK_ID[cid]
                card_bit = 1 << cid
                if turn == 0:
                    next_p0 = p0_hand ^ card_bit
                    rem_hand = next_p0
                else:
                    next_p1 = p1_hand ^ card_bit
                    rem_hand = next_p1

                next_top = cid
                next_req = s_idx if rank == 1 else -1
                next_ace = (rank == 7)

                if not rem_hand:
                    if rank == 5:
                        val = -10000.0 if turn == 0 else 10000.0
                        if is_max:
                            if val > best_val:
                                best_val = val
                                best_mv = mv
                            if val > alpha:
                                alpha = val
                            if beta <= alpha:
                                break
                        else:
                            if val < best_val:
                                best_val = val
                                best_mv = mv
                            if val < beta:
                                beta = val
                            if beta <= alpha:
                                break
                        continue
                elif rank == 5:
                    next_turn = turn

                if rank != 1 and (rem_hand & RANK_MASK[rank]):
                    if top_cid >= 0 and CARD_RANK_ID[top_cid] == rank:
                        next_chain = True
                        next_turn = turn

            elif m_type == MOVE_MULTIPLE:
                cards_mask = cid
                last_cid = (cards_mask & -cards_mask).bit_length() - 1
                rank = CARD_RANK_ID[last_cid]

                if turn == 0:
                    next_p0 = p0_hand ^ cards_mask
                    rem_hand = next_p0
                else:
                    next_p1 = p1_hand ^ cards_mask
                    rem_hand = next_p1

                next_top = last_cid
                next_req = s_idx if rank == 1 else -1
                next_ace = (rank == 7)

                if not rem_hand:
                    if rank == 5:
                        val = -10000.0 if turn == 0 else 10000.0
                        if is_max:
                            if val > best_val:
                                best_val = val
                                best_mv = mv
                            if val > alpha:
                                alpha = val
                            if beta <= alpha:
                                break
                        else:
                            if val < best_val:
                                best_val = val
                                best_mv = mv
                            if val < beta:
                                beta = val
                            if beta <= alpha:
                                break
                        continue
                elif rank == 5:
                    next_turn = turn

            elif m_type == MOVE_DRAW:
                next_drawn = True
                next_turn = turn
                if ace:
                    next_ace = False
                    next_turn = 1 - turn

            elif m_type == MOVE_PASS:
                next_turn = 1 - turn
                next_drawn = False
                next_chain = False

            val = minimax(
                next_p0, next_p1, next_top, next_req, next_turn,
                next_ace, next_chain, next_drawn, depth - 1, alpha, beta
            )

            if is_max:
                if val > best_val:
                    best_val = val
                    best_mv = mv
                if val > alpha:
                    alpha = val
                if beta <= alpha:
                    break
            else:
                if val < best_val:
                    best_val = val
                    best_mv = mv
                if val < beta:
                    beta = val
                if beta <= alpha:
                    break

        memo[z_key] = (best_val, best_mv)
        return best_val

    root_turn = 0 if is_my_turn else 1
    score = minimax(
        my_hand_mask, opp_hand_mask, top_card_id, req_suit,
        root_turn, ace_active, is_chaining, has_drawn, depth=12,
        alpha=float("-inf"), beta=float("inf")
    )
    root_key = compute_zobrist(
        my_hand_mask, opp_hand_mask, top_card_id, req_suit,
        root_turn, ace_active, is_chaining, has_drawn
    )
    best_move = memo.get(root_key, (score, None))[1]
    return score, best_move


# ---------------------------------------------------------------------------
# Tactical Heuristic Evaluation & Dynamic Modes
# ---------------------------------------------------------------------------

def ace_is_tactical(view: PlayerView) -> bool:
    """Return True if Ace is tactically urgent."""
    if view.table.ace_effect_active:
        return False
    if view.table.required_suit is not None:
        hand_counts = Counter(card.suit for card in view.you.hand)
        return hand_counts[view.table.required_suit] == 0
    top = view.table.top_card
    if top is None:
        return False
    if top.rank == Rank.ACE:
        return True
    hand_counts = Counter(card.suit for card in view.you.hand)
    return hand_counts[top.suit] == 0


def card_context(view: PlayerView, card: Card, *, remaining_after: int, streak_mode: int = 0) -> float:
    """Card context evaluation incorporating game dynamics."""
    opp = view.sole_opponent()
    opp_size = opp.hand_size if opp else 8
    bonus = 0.0
    my_size = view.you.hand_size

    # STRICT ROUND-LEVEL AGONY: Only when opponent or we are genuinely close to finishing
    is_agony = (opp_size <= 3 or my_size <= 3 or remaining_after <= 1)

    if card.rank == Rank.EIGHT:
        if remaining_after == 0:
            # Finishing on an 8 is a glorious win
            bonus += 150.0
        elif opp_size <= 2:
            # Opponent is 1-2 cards away: dump the 32-pt wildcard immediately!
            bonus += 65.0
        elif opp_size <= 3:
            bonus += 30.0
        elif remaining_after <= 1:
            bonus += 25.0
        elif my_size >= 6:
            # EARLY ROUND: Retain the 8 wildcard as an emergency escape / counter
            bonus -= 70.0
        elif my_size >= 4:
            # MID ROUND: Strong penalty for burning 8 prematurely
            bonus -= 40.0
        else:
            bonus += 5.0

    elif card.rank == Rank.ACE:
        if view.table.ace_effect_active:
            # Countering an active Ace attack: highly rewarded!
            bonus += 40.0
        elif view.table.top_card is None:
            # MASTER OPENING MOVE: Ace on empty table forces opponent to draw 2 or burn Ace/8!
            bonus += 50.0
        elif opp_size <= 3:
            # Attack opponent with Ace when they are short to force bank draw
            bonus += 35.0
        elif ace_is_tactical(view):
            bonus += 25.0
        elif my_size >= 6:
            bonus += 5.0
        else:
            bonus += 15.0

    elif card.rank == Rank.TEN:
        if view.table.top_card is None and my_size >= 7:
            bonus += 12.0  # Opening high penalty card disposal
        elif is_agony:
            bonus += 20.0
        else:
            bonus += 8.0

    elif card.rank == Rank.KING:
        if is_agony:
            bonus += 10.0
        else:
            bonus += 5.0

    elif card.rank == Rank.QUEEN:
        if view.match.player_count == 2 and remaining_after == 0:
            bonus -= 10_000.0  # Illegal Queen win trap
        elif view.table.top_card is None and my_size >= 7:
            # Do NOT waste Queen on empty table on turn 1 unless part of a multi-play
            bonus -= 15.0
        elif view.match.player_count == 2 and remaining_after > 0:
            # Queen in 2P skips opponent = replay immediately!
            other_cards = [c for c in view.you.hand if c != card]
            has_followup = any(
                c.suit == card.suit or c.rank in (Rank.QUEEN, Rank.EIGHT)
                for c in other_cards
            )
            if has_followup:
                bonus += 55.0  # Chain into another play
            else:
                bonus += 10.0
        elif is_agony:
            bonus += 8.0
        else:
            bonus += 5.0

    return bonus


def score_action(
    view: PlayerView,
    action: Action,
    streak_mode: int = 0,
) -> tuple[float, float, str]:
    """Tactical heuristic evaluation for legal actions."""
    if finishes_on_queen_two_player(view, action):
        return (-10_000.0, 0.0, "queen-finish-trap")

    cards: tuple[Card, ...] = ()
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
    score = 0.0

    # 1. Round Finish Payoff (Immediate Win)
    if remaining == 0:
        score += 5_000.0
        if streak_mode == 1 or view.you.consecutive_round_wins == 2:
            score += 1_500.0
        if streak_mode == 4 or (opp and opp.total_score >= 120):
            score += 1_000.0

    # 2. Hand Reduction & Multi-Card Chaining (Primary Driver)
    score += emptied * 32.0
    score -= remaining * 8.0

    # Multi-card set bonus: heavily reward 2, 3, or 4 of a kind (except dual 8s early)
    if emptied >= 2:
        if cards[0].rank == Rank.EIGHT and opp_size > 3 and view.you.hand_size >= 5:
            # Do NOT dump multiple 8s at once in early game!
            score -= 100.0
        else:
            score += (emptied - 1) * 45.0

    # 3. Urgency & Agony Mode Dumping (strictly round-level opp_size <= 3 or my_size <= 3)
    if opp_size <= 3:
        score += emptied * 25.0
        score -= remaining * 16.0
        score += dump * 2.2
    elif view.you.hand_size <= 3:
        score += emptied * 20.0
        score -= remaining * 10.0
        score += dump * 1.0
    else:
        # Early/mid round: dump value should NOT dominate card choice
        score += dump * 0.4

    # 4. Queen Tempo in 2P (when remaining > 0)
    last = cards[-1]
    if last.rank == Rank.QUEEN and view.match.player_count == 2 and remaining > 0:
        other_cards = [c for c in view.you.hand if c not in cards]
        has_followup = any(
            c.suit == last.suit or c.rank in (Rank.QUEEN, Rank.EIGHT)
            for c in other_cards
        )
        if has_followup:
            score += 65.0
        else:
            score += 15.0

    for card in cards:
        score += card_context(view, card, remaining_after=remaining, streak_mode=streak_mode)

    # 5. Chaining bonus
    if view.you.is_chaining:
        top = view.table.top_card
        if top is not None and any(card.rank == top.rank for card in cards):
            score += 35.0

    # 6. Anti-single Queen leftover in 2P
    if remaining == 1 and view.match.player_count == 2:
        left = list(view.you.hand)
        for c in cards:
            if c in left:
                left.remove(c)
        if len(left) == 1 and left[0].rank == Rank.QUEEN:
            score -= 80.0

    key = cards[0].code if len(cards) == 1 else f"M{len(cards)}-{cards[0].code}"
    return (score, dump, key)

