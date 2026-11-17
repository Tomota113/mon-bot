"""Bayesian Negative Inference Card Tracker & PIMC World Sampler for i151."""

from __future__ import annotations

import random
from typing import Sequence
from arena_sdk import PlayerView
from i151_engine.models.card import Card, Rank, Suit
from evaluator import (
    CARD_BY_ID,
    ID_BY_CARD,
    CARD_RANK_ID,
    CARD_SUIT_ID,
    EIGHTS_MASK,
    ACES_MASK,
    RANK_MASK,
    SUIT_MASK,
    ALL_CARDS_MASK,
    cards_to_mask,
    mask_to_cards,
)

ALL_CARDS: tuple[Card, ...] = CARD_BY_ID


class CardTracker:
    """Tracks played cards, infers opponent voids, and samples determinized worlds."""

    def __init__(self) -> None:
        self.round_number: int = -1
        self.seen_mask: int = 0
        self.opp_void_masks: list[int] = []
        self.last_opp_hand_size: int = 8
        self.last_bank_size: int = 16
        self.last_table_top: Card | None = None
        self.last_req_suit: Suit | None = None

    def reset_for_round(self, round_number: int) -> None:
        """Reset state for a new round."""
        self.round_number = round_number
        self.seen_mask = 0
        self.opp_void_masks = []
        self.last_opp_hand_size = 8
        self.last_bank_size = 16
        self.last_table_top = None
        self.last_req_suit = None

    def update_from_view(self, view: PlayerView) -> None:
        """Update tracker with table state and infer opponent voids."""
        if view.match.round_number != self.round_number:
            self.reset_for_round(view.match.round_number)

        # Detect deck recycling: if bank size increased or played pile was emptied
        if view.table.bank_size > self.last_bank_size and view.table.played_pile_size <= 2:
            # Recycle occurred: only recent cards are currently out of play
            self.seen_mask = cards_to_mask(view.table.recent_cards)
            self.opp_void_masks.clear()  # Clear void constraints since deck was recycled
        else:
            self.seen_mask |= cards_to_mask(view.table.recent_cards)
            self.seen_mask |= cards_to_mask(view.table.last_play_cards)

        opp = view.sole_opponent()
        curr_opp_size = opp.hand_size if opp else 8

        # Infer opponent voids:
        # If it is now our turn and opponent drew a card (hand size increased)
        if view.turn.is_your_turn and self.last_table_top is not None:
            if curr_opp_size > self.last_opp_hand_size:
                void_mask = 0
                if self.last_req_suit is not None:
                    from evaluator import SUIT_TO_ID
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

        # Update last known state
        self.last_opp_hand_size = curr_opp_size
        self.last_bank_size = view.table.bank_size
        self.last_table_top = view.table.top_card
        self.last_req_suit = view.table.required_suit

    def get_unrevealed_mask(self, my_hand_mask: int) -> int:
        """Return bitmask of all unrevealed cards (cards in opp hand + bank)."""
        known = my_hand_mask | self.seen_mask
        return ALL_CARDS_MASK & ~known

    def sample_opponent_and_bank(
        self,
        my_hand: tuple[Card, ...] | list[Card],
        opp_hand_size: int,
        rng: random.Random,
    ) -> tuple[list[Card], list[Card]]:
        my_mask = cards_to_mask(my_hand)
        opp_mask, bank_mask = self.sample_world(my_mask, opp_hand_size, rng)
        return mask_to_cards(opp_mask), mask_to_cards(bank_mask)

    def sample_world(
        self,
        my_hand_mask: int,
        opp_hand_size: int,
        rng: random.Random,
    ) -> tuple[int, int]:
        unrevealed_mask = self.get_unrevealed_mask(my_hand_mask)
        unrevealed_cards = []
        m = unrevealed_mask
        while m:
            lsb = m & -m
            cid = lsb.bit_length() - 1
            unrevealed_cards.append(cid)
            m ^= lsb

        total_unrevealed = len(unrevealed_cards)
        if total_unrevealed <= opp_hand_size:
            return unrevealed_mask, 0

        weights: list[float] = []
        for cid in unrevealed_cards:
            card_bit = 1 << cid
            is_void = any(bool(card_bit & v_mask) for v_mask in self.opp_void_masks)
            w = 0.0001 if is_void else 1.0
            weights.append(w)

        selected_opp: list[int] = []
        candidates = list(unrevealed_cards)
        cand_weights = list(weights)

        for _ in range(opp_hand_size):
            if not candidates:
                break
            total_w = sum(cand_weights)
            if total_w <= 0:
                idx = rng.randrange(len(candidates))
            else:
                r = rng.uniform(0, total_w)
                cum = 0.0
                idx = 0
                for i, w in enumerate(cand_weights):
                    cum += w
                    if cum >= r:
                        idx = i
                        break
            selected_opp.append(candidates.pop(idx))
            cand_weights.pop(idx)

        opp_mask = 0
        for cid in selected_opp:
            opp_mask |= (1 << cid)

        bank_mask = unrevealed_mask & ~opp_mask
        return opp_mask, bank_mask

    def sample_worlds_masks(
        self,
        my_hand_mask: int,
        opp_hand_size: int,
        num_worlds: int,
        rng: random.Random,
    ) -> list[tuple[int, int]]:
        unrevealed_mask = self.get_unrevealed_mask(my_hand_mask)
        total_unrevealed = unrevealed_mask.bit_count()

        if total_unrevealed <= opp_hand_size:
            return [(unrevealed_mask, 0)]

        worlds: list[tuple[int, int]] = []
        for _ in range(num_worlds):
            w = self.sample_world(my_hand_mask, opp_hand_size, rng)
            worlds.append(w)
        return worlds


global_tracker = CardTracker()
