"""
Fafnir Game implementation for OpenSpiel.

Fafnir is a 2-player auction and hand management game with strategic scoring.
"""

import pyspiel
import numpy as np
from typing import List, Dict, Tuple, Optional, Any
import itertools


# Game constants
COLORS = ["red", "orange", "yellow", "green", "blue"]
GOLD = "gold"
ALL_STONES = COLORS + [GOLD]

STONE_COUNT = {GOLD: 20, "red": 12, "orange": 12, "yellow": 12, "green": 12, "blue": 12}
TRASH_LIMIT = 6
SEED_TRASH_AT_ROUND_START = 3
POINT_CHIP = 1
SCORE_TO_WIN = 1000

# Action encoding
# Actions: (player_index, selected_indices_bitmap)
# For bidding phase: bitmap of stone indices to bid
# For proceed phase: empty (next phase)

# Game states (phases)
PHASE_BIDDING = 0
PHASE_RESULT = 1
PHASE_ROUND_END = 2
PHASE_GAME_END = 3


class FafnirGameState(pyspiel.State):
    """Game state for Fafnir."""

    def __init__(self, game):
        super().__init__(game)
        self.game = game

        # Bag and distribution
        self._bag: List[str] = self._make_bag()
        self._trash: Dict[str, int] = {s: 0 for s in ALL_STONES}
        self._trash_pile: List[str] = []

        # Player states
        self._hands: List[List[str]] = [[], []]
        self._bids_submitted: List[bool] = [False, False]
        self._bids: List[List[str]] = [[], []]
        self._scores: List[int] = [0, 0]
        self._ok_ready: List[bool] = [False, False]

        # Game flow
        self._offer: List[str] = []
        self._caretaker: int = 0
        self._phase: int = PHASE_BIDDING
        self._round: int = 1
        self._turn: int = 0
        self._current_player: int = 0

        # Last action tracking
        self._last_offer: List[str] = []
        self._last_result: Dict[str, Any] = {}
        self._round_end_info: Dict[str, Any] = {}

        # Initialize game
        self._reset_round()

    def __getstate__(self):
        """Custom pickling: exclude heavy or recursive references (like `game`)."""
        state = self.__dict__.copy()
        # Do not pickle the game object to avoid recursive structures
        if "game" in state:
            state["_game_marker"] = True
            state.pop("game", None)
        else:
            state["_game_marker"] = False
        return state

    def __setstate__(self, state):
        """Restore state without re-running full initialization.

        Recreate a minimal `game` reference to allow methods that expect it.
        """
        # Restore attributes
        self.__dict__.update(state)

        # Recreate a lightweight game reference if marker present
        if self.__dict__.get("_game_marker", False):
            try:
                # Prefer creating the local wrapper game
                self.game = FafnirGame()
            except Exception:
                # Fallback: leave as None
                self.game = None
        else:
            self.game = None

    def _make_bag(self) -> List[str]:
        """Create shuffled bag of stones."""
        bag = []
        for color, count in STONE_COUNT.items():
            bag.extend([color] * count)
        np.random.shuffle(bag)
        return bag

    def _draw_one(self) -> Optional[str]:
        """Draw one stone from bag."""
        if not self._bag:
            return None
        return self._bag.pop()

    def _seed_trash(self, n: int = SEED_TRASH_AT_ROUND_START) -> List[str]:
        """Seed trash at round start."""
        seeded = []
        for _ in range(n):
            stone = self._draw_one()
            if stone is None:
                break
            seeded.append(stone)
            self._trash[stone] = self._trash.get(stone, 0) + 1
            self._trash_pile.append(stone)
        return seeded

    def _setup_offer(self) -> bool:
        """Draw offer stones (must have different colors if possible)."""
        self._offer = []
        if not self._bag:
            return False

        stones = []
        while True:
            draw_n = min(2, len(self._bag))
            for _ in range(draw_n):
                s = self._draw_one()
                if s:
                    stones.append(s)

            # Accept if <2 (bag low) OR >=2 colors
            if len(set(stones)) > 1 or not self._bag:
                break

        self._offer = stones
        return bool(self._offer)

    def _deal_initial_hands(self):
        """Deal initial hands for the round."""
        self._hands = [[], []]
        self._bids = [[], []]
        self._bids_submitted = [False, False]
        self._ok_ready = [False, False]

        for player_idx in range(2):
            hand_size = 11 if player_idx == self._caretaker else 10
            for _ in range(hand_size):
                stone = self._draw_one()
                if stone:
                    self._hands[player_idx].append(stone)

    def _reset_round(self):
        """Reset for new round."""
        self._bag = self._make_bag()
        self._trash = {s: 0 for s in ALL_STONES}
        self._trash_pile = []

        self._bids = [[], []]
        self._bids_submitted = [False, False]
        self._ok_ready = [False, False]

        self._deal_initial_hands()
        self._seed_trash()
        self._setup_offer()

        self._phase = PHASE_BIDDING
        self._turn = 0
        self._current_player = 0

    def _is_trash_limit_reached(self) -> bool:
        """Check if any color reached trash limit."""
        for color in COLORS + [GOLD]:
            if self._trash.get(color, 0) >= TRASH_LIMIT:
                return True
        return False

    def _get_trash_trigger_color(self) -> Optional[str]:
        """Get the color that triggered trash limit."""
        for color in COLORS + [GOLD]:
            if self._trash.get(color, 0) >= TRASH_LIMIT:
                return color
        return None

    def _rank_colors_by_total(self) -> List[Tuple[str, int]]:
        """Rank colors by total count in both hands."""
        totals = {c: 0 for c in COLORS}
        for hand in self._hands:
            for stone in hand:
                if stone in COLORS:
                    totals[stone] += 1

        color_priority = list(COLORS)
        return sorted(totals.items(), key=lambda x: (-x[1], color_priority.index(x[0])))

    def _compute_round_scores(self) -> Tuple[List[Tuple[str, int]], List[int]]:
        """Compute scores for the round."""
        ranked = self._rank_colors_by_total()
        first_color = ranked[0][0] if ranked else None
        second_color = ranked[1][0] if len(ranked) > 1 else None

        adds = []
        for player_idx in range(2):
            score = 0
            hand = self._hands[player_idx]

            # Gold points
            score += hand.count(GOLD)

            # Color scoring
            for color in COLORS:
                cnt = hand.count(color)
                if cnt == 0 or cnt >= 5:
                    continue

                if color == first_color:
                    mult = 3
                elif color == second_color:
                    mult = 2
                else:
                    mult = -1

                score += cnt * mult

            adds.append(max(0, score))

        return ranked, adds

    def _resolve_auction(self) -> Optional[int]:
        """Resolve current auction. Returns winner index or None if no bids."""
        bid_counts = [len(self._bids[0]), len(self._bids[1])]
        max_bid = max(bid_counts) if bid_counts else 0

        if max_bid == 0:
            # No bids - everyone loses points
            self._scores[0] = max(0, self._scores[0] - 1)
            self._scores[1] = max(0, self._scores[1] - 1)

            # Trash the offer
            for stone in self._offer:
                self._trash[stone] = self._trash.get(stone, 0) + 1
                self._trash_pile.append(stone)
            self._offer = []

            return None

        # Determine winner (caretaker loses ties)
        candidates = [i for i, bc in enumerate(bid_counts) if bc == max_bid]
        if len(candidates) == 1:
            winner = candidates[0]
        else:
            if self._caretaker in candidates:
                non_ct = [i for i in candidates if i != self._caretaker]
                winner = min(non_ct) if non_ct else self._caretaker
            else:
                winner = min(candidates)

        loser = 1 - winner

        # Process winner
        used = self._bids[winner][:]
        for stone in used:
            if stone in self._hands[winner]:
                self._hands[winner].remove(stone)

        # Trash used stones
        for stone in used:
            self._trash[stone] = self._trash.get(stone, 0) + 1
            self._trash_pile.append(stone)

        # Winner gets offer
        self._hands[winner].extend(self._offer)

        # Score
        self._scores[winner] += POINT_CHIP

        # Caretaker updates
        self._caretaker = winner

        # Store result for history
        self._last_offer = self._offer[:]
        self._last_result = {
            "winner": winner,
            "loser": loser,
            "bids": [self._bids[0][:], self._bids[1][:]],
            "offer": self._offer[:],
            "used": used,
        }

        # Clear bids
        self._bids = [[], []]
        self._bids_submitted = [False, False]

        return winner

    def is_terminal(self) -> bool:
        """Check if game is terminal."""
        return self._phase == PHASE_GAME_END

    def returns(self) -> List[float]:
        """Return utility for each player."""
        if not self.is_terminal():
            return [0.0, 0.0]

        # Winner gets 1, loser gets 0
        if self._scores[0] >= SCORE_TO_WIN:
            return [1.0, 0.0]
        elif self._scores[1] >= SCORE_TO_WIN:
            return [0.0, 1.0]
        else:
            return [0.0, 0.0]

    def current_player(self) -> int:
        """Return current player index."""
        if self.is_terminal():
            return pyspiel.PlayerId.TERMINAL
        # During bidding, return current bidder
        if self._phase == PHASE_BIDDING:
            return self._current_player
        # Result phase: return the next player who hasn't confirmed ready yet
        if self._phase == PHASE_RESULT:
            for p in range(2):
                if not self._ok_ready[p]:
                    return p
            # Both ready -> terminal/transition handled in apply_action
            return pyspiel.PlayerId.TERMINAL

        # Round end or other phases: let player 0 act by default
        return 0

    def _legal_actions_bidding(self) -> List[int]:
        """Get legal bid actions for current player."""

        hand = self._hands[self._current_player]
        actions = []

        # Generate all subsets of hand (bitmask encoding)
        for mask in range(1 << len(hand)):
            bid = [hand[i] for i in range(len(hand)) if mask & (1 << i)]
            # Action = mask (subset encoding)
            actions.append(mask)

        # Also allow passing to next player
        actions.append(1 << len(hand))  # "proceed" action

        # If already submitted, return proceed action only
        if self._bids_submitted[self._current_player]:
            return [1 << len(hand)]

        return actions

    def legal_actions(self) -> List[int]:
        """Return list of legal action indices."""
        if self._phase == PHASE_BIDDING:
            return self._legal_actions_bidding()
        elif self._phase == PHASE_RESULT:
            return list(range(2))  # Both players can proceed
        elif self._phase == PHASE_ROUND_END:
            return [0]  # One action: continue
        else:
            return []

    def action_to_string(self, action: int) -> str:
        """Convert action code to string."""
        if self._phase == PHASE_BIDDING:
            hand = self._hands[self._current_player]
            if action >= (1 << len(hand)):
                return "proceed"
            bid = [hand[i] for i in range(len(hand)) if action & (1 << i)]
            return f"bid:{','.join(bid)}"
        elif self._phase == PHASE_RESULT:
            return "proceed" if action == 0 else "cancel"
        else:
            return f"action_{action}"

    def apply_action(self, action: int):
        """Apply action to the game state."""
        if self._phase == PHASE_BIDDING:
            self._apply_bidding_action(action)
        elif self._phase == PHASE_RESULT:
            self._apply_result_action(action)
        elif self._phase == PHASE_ROUND_END:
            self._apply_round_end_action(action)

    def _apply_bidding_action(self, action: int):
        """Apply bidding phase action."""
        hand = self._hands[self._current_player]
        proceed_mask = 1 << len(hand)

        if action >= proceed_mask:
            # Next player
            self._current_player = 1 - self._current_player
            if self._current_player == 0:
                self._turn += 1
                if self._turn >= 2:  # Both players have acted
                    self._phase = PHASE_RESULT
                    self._ok_ready = [False, False]
        else:
            # Bid action
            bid = [hand[i] for i in range(len(hand)) if action & (1 << i)]
            self._bids[self._current_player] = bid
            self._bids_submitted[self._current_player] = True
            self._current_player = 1 - self._current_player

    def _apply_result_action(self, action: int):
        """Apply result phase action (proceed to next turn or end round)."""
        player = self.current_player()
        self._ok_ready[player] = True

        if all(self._ok_ready):
            # Both players ready
            winner = self._resolve_auction()

            # Check if round should end
            if (
                self._is_trash_limit_reached()
                or len(self._bag) < 2
                or not self._setup_offer()
            ):
                # Round end
                self._phase = PHASE_ROUND_END
            else:
                # Next turn
                self._phase = PHASE_BIDDING
                self._turn = 0
                self._current_player = 0
                self._bids = [[], []]
                self._bids_submitted = [False, False]
                self._ok_ready = [False, False]

    def _apply_round_end_action(self, action: int):
        """Apply round end action."""
        # Score the round
        ranked, adds = self._compute_round_scores()
        for i in range(2):
            self._scores[i] += adds[i]

        self._round_end_info = {
            "ranked": ranked,
            "adds": adds,
            "round_winner": 0 if adds[0] > adds[1] else 1,
        }

        # Check if game ends
        if max(self._scores) >= SCORE_TO_WIN:
            self._phase = PHASE_GAME_END
        else:
            # Start new round
            self._round += 1
            self._reset_round()

    def observation_tensor(self, player: int) -> np.ndarray:
        """Return observation tensor for player."""
        # Simple observation: concatenate relevant state
        obs = []

        # Player's hand (one-hot encoding)
        for stone in ALL_STONES:
            obs.append(float(self._hands[player].count(stone)))

        # Opponent's hand size
        obs.append(float(len(self._hands[1 - player])))

        # Bids
        for stone in ALL_STONES:
            obs.append(float(self._bids[0].count(stone)))
            obs.append(float(self._bids[1].count(stone)))

        # Offer
        for stone in ALL_STONES:
            obs.append(float(self._offer.count(stone)))

        # Scores
        obs.append(float(self._scores[player]))
        obs.append(float(self._scores[1 - player]))

        # Trash counts
        for stone in ALL_STONES:
            obs.append(float(self._trash.get(stone, 0)))

        # Bag left
        obs.append(float(len(self._bag)))

        # Phase (one-hot)
        for ph in range(4):
            obs.append(1.0 if self._phase == ph else 0.0)

        return np.array(obs, dtype=np.float32)

    def __str__(self) -> str:
        return f"Fafnir(round={self._round}, turn={self._turn}, phase={self._phase})"

    def clone(self):
        """Create a safe shallow clone of the state for search/traversal.

        This avoids using pickle/deepcopy on objects that may contain
        recursive references (like the `game` object). Only container
        fields are shallow-copied so the clone is independent for
        simulation purposes.
        """
        # Use class __new__ to satisfy pyspiel.State safety checks
        new = FafnirGameState.__new__(FafnirGameState)
        # Preserve game reference
        new.game = self.game

        # Copy bag and piles
        new._bag = list(self._bag)
        new._trash = dict(self._trash)
        new._trash_pile = list(self._trash_pile)

        # Player-specific state
        new._hands = [list(h) for h in self._hands]
        new._bids_submitted = list(self._bids_submitted)
        new._bids = [list(b) for b in self._bids]
        new._scores = list(self._scores)
        new._ok_ready = list(self._ok_ready)

        # Game flow
        new._offer = list(self._offer)
        new._caretaker = self._caretaker
        new._phase = self._phase
        new._round = self._round
        new._turn = self._turn
        new._current_player = self._current_player

        # Last action/history
        new._last_offer = list(self._last_offer)
        new._last_result = dict(self._last_result)
        new._round_end_info = dict(self._round_end_info)

        return new


def _register_fafnir():
    """Register Fafnir game with OpenSpiel."""
    game_type = pyspiel.GameType(
        short_name="fafnir",
        long_name="Fafnir",
        dynamics=pyspiel.GameType.Dynamics.SEQUENTIAL,
        chance_mode=pyspiel.GameType.ChanceMode.DETERMINISTIC,
        information=pyspiel.GameType.Information.PERFECT_INFORMATION,
        utility=pyspiel.GameType.Utility.ZERO_SUM,
        reward_model=pyspiel.GameType.RewardModel.TERMINAL,
        max_num_players=2,
        min_num_players=2,
        provides_information_state_string=False,
        provides_information_state_tensor=True,
        provides_observation_string=False,
        provides_observation_tensor=True,
    )

    # Register factory that returns a new FafnirGame
    pyspiel.register_game(game_type, lambda params=None: FafnirGame(params))


class FafnirGame(pyspiel.Game):
    """Fafnir game wrapper for OpenSpiel."""

    def __init__(self, params=None):
        game_type = pyspiel.GameType(
            short_name="fafnir",
            long_name="Fafnir",
            dynamics=pyspiel.GameType.Dynamics.SEQUENTIAL,
            chance_mode=pyspiel.GameType.ChanceMode.DETERMINISTIC,
            information=pyspiel.GameType.Information.PERFECT_INFORMATION,
            utility=pyspiel.GameType.Utility.ZERO_SUM,
            reward_model=pyspiel.GameType.RewardModel.TERMINAL,
            max_num_players=2,
            min_num_players=2,
            provides_information_state_string=False,
            provides_information_state_tensor=True,
            provides_observation_string=False,
            provides_observation_tensor=True,
        )

        # GameInfo requires: num_distinct_actions, max_chance_outcomes, num_players,
        # min_utility, max_utility, utility_sum, max_game_length
        # Max distinct actions: 2^11 (max hand size) + 1 (proceed) = 2049
        game_info = pyspiel.GameInfo(
            num_distinct_actions=2049,
            max_chance_outcomes=0,
            num_players=2,
            min_utility=0.0,
            max_utility=1.0,
            utility_sum=1.0,
            max_game_length=10000,
        )

        super().__init__(game_type, game_info, params or {})

    def new_initial_state(self):
        """Return new initial game state."""
        game_state = FafnirGameState(self)
        return game_state

    def max_chance_outcomes(self):
        return 0

    def get_parameters(self):
        return {}

    def num_players(self):
        return 2

    def min_utility(self):
        return 0.0

    def max_utility(self):
        return 1.0

    def utility_sum(self):
        return 1.0

    def max_game_length(self):
        return 10000  # Rough upper bound


# Register the game if needed
try:
    if "fafnir" not in pyspiel.registered_games():
        _register_fafnir()
except Exception:
    _register_fafnir()
