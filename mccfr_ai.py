"""
MCCFR (Monte Carlo Counterfactual Regret Minimization) AI for Fafnir.

This module implements a Monte Carlo CFR-based AI player that learns
Nash equilibrium strategies through self-play and iterative improvements.
"""

import numpy as np
from typing import Dict, List, Tuple, Optional, DefaultDict
from collections import defaultdict
import random
import copy
import multiprocessing as mp
from dataclasses import dataclass, field
import pickle
import os
import tempfile


@dataclass
class NodeInfo:
    """Information about a game tree node."""

    info_state: str
    regrets: DefaultDict[int, float] = field(default_factory=lambda: defaultdict(float))
    strategy_sums: DefaultDict[int, float] = field(
        default_factory=lambda: defaultdict(float)
    )
    visits: int = 0

    def get_strategy(self, actions: List[int], epsilon: float = 1e-6) -> np.ndarray:
        """Get current strategy using regret matching."""
        strategy = np.zeros(len(actions))
        regret_sum = 0.0

        for i, action in enumerate(actions):
            regret = max(0, self.regrets[action])
            strategy[i] = regret
            regret_sum += regret

        if regret_sum > epsilon:
            strategy /= regret_sum
        else:
            strategy[:] = 1.0 / len(actions)

        return strategy

    def update_strategy(self, actions: List[int], action_probs: np.ndarray):
        """Update strategy sum."""
        for i, action in enumerate(actions):
            self.strategy_sums[action] += action_probs[i]

    def get_average_strategy(self, actions: List[int]) -> np.ndarray:
        """Get average strategy."""
        avg_strategy = np.zeros(len(actions))
        strategy_sum = sum(self.strategy_sums.values())

        if strategy_sum > 0:
            for i, action in enumerate(actions):
                avg_strategy[i] = self.strategy_sums[action] / strategy_sum
        else:
            avg_strategy[:] = 1.0 / len(actions)

        return avg_strategy


class MCCFRSolver:
    """MCCFR solver for Fafnir game."""

    def __init__(
        self,
        game_class,
        learning_rate: float = 0.1,
        exploration_bonus: float = 0.1,
        max_depth: int = 512,
    ):
        """
        Initialize MCCFR solver.

        Args:
            game_class: OpenSpiel game class
            learning_rate: Learning rate for regret updates
            exploration_bonus: Bonus for exploration (UCB style)
            max_depth: Maximum recursion depth per traversal
        """
        self.game_class = game_class
        self.learning_rate = learning_rate
        self.exploration_bonus = exploration_bonus
        self.max_depth = max_depth
        self.nodes: Dict[str, NodeInfo] = {}
        self.iterations = 0
        self.payoff_sum = [0.0, 0.0]

    def get_node(self, info_state: str) -> NodeInfo:
        """Get or create node."""
        if info_state not in self.nodes:
            self.nodes[info_state] = NodeInfo(info_state=info_state)
        return self.nodes[info_state]

    def run_mccfr(
        self,
        num_iterations: int = 1000,
        num_workers: int = 1,
        show_progress: bool = True,
    ):
        """Run MCCFR iterations (optionally in parallel workers)."""
        if num_iterations <= 0:
            return

        if num_workers is None or num_workers <= 1:
            self._run_mccfr_serial(num_iterations, show_progress=show_progress)
            return

        max_workers = os.cpu_count() or 1
        worker_count = min(max_workers, max(1, int(num_workers)))
        if worker_count == 1:
            self._run_mccfr_serial(num_iterations, show_progress=show_progress)
            return

        counts = _split_iterations(num_iterations, worker_count)
        if len(counts) <= 1:
            self._run_mccfr_serial(num_iterations, show_progress=show_progress)
            return

        seeds = [random.randint(0, 2**31 - 1) for _ in counts]
        jobs = [
            (
                self.game_class,
                count,
                self.learning_rate,
                self.exploration_bonus,
                self.max_depth,
                seeds[i],
            )
            for i, count in enumerate(counts)
        ]

        ctx = mp.get_context("spawn")
        with ctx.Pool(processes=len(jobs)) as pool:
            results = pool.map(_mccfr_worker, jobs)

        for nodes, iterations, payoff_sum in results:
            self._merge_worker_result(nodes, iterations, payoff_sum)

        if show_progress:
            avg_utility_0 = (
                self.payoff_sum[0] / self.iterations if self.iterations else 0.0
            )
            avg_utility_1 = (
                self.payoff_sum[1] / self.iterations if self.iterations else 0.0
            )
            print(
                f"[MCCFR] Parallel run +{num_iterations} iters "
                f"({len(jobs)} workers) - Nodes: {len(self.nodes)} - "
                f"P0 util: {avg_utility_0:.4f}, P1 util: {avg_utility_1:.4f}"
            )

    def _run_mccfr_serial(self, num_iterations: int, show_progress: bool = True):
        for iteration in range(num_iterations):
            state = self.game_class().new_initial_state()
            utilities = self._mccfr_iteration(state, [1.0, 1.0], 0)
            self.payoff_sum[0] += utilities[0]
            self.payoff_sum[1] += utilities[1]
            self.iterations += 1

            if show_progress and (iteration + 1) % 100 == 0:
                avg_utility_0 = self.payoff_sum[0] / (self.iterations)
                avg_utility_1 = self.payoff_sum[1] / (self.iterations)
                print(
                    f"[MCCFR] Iteration {iteration + 1}/{num_iterations} "
                    f"- Nodes: {len(self.nodes)} - "
                    f"P0 util: {avg_utility_0:.4f}, P1 util: {avg_utility_1:.4f}"
                )

    def _merge_worker_result(
        self,
        worker_nodes: Dict[str, NodeInfo],
        worker_iterations: int,
        worker_payoff_sum: List[float],
    ):
        for info_state, worker_node in worker_nodes.items():
            node = self.nodes.get(info_state)
            if node is None:
                self.nodes[info_state] = worker_node
                continue

            for action, regret in worker_node.regrets.items():
                node.regrets[action] += regret
            for action, strat_sum in worker_node.strategy_sums.items():
                node.strategy_sums[action] += strat_sum
            node.visits += worker_node.visits

        self.iterations += worker_iterations
        self.payoff_sum[0] += worker_payoff_sum[0]
        self.payoff_sum[1] += worker_payoff_sum[1]

    def _mccfr_iteration(
        self, state, reach_probs: List[float], depth: int = 0
    ) -> List[float]:
        """
        Single MCCFR iteration (recursive).

        Returns utilities [u0, u1] from current player's perspective.
        """
        if self.max_depth is not None and depth >= self.max_depth:
            # Cut off long trajectories to avoid Python recursion limits
            return [0.0, 0.0]

        if state.is_terminal():
            return list(state.returns())

        current_player = state.current_player()
        actions = state.legal_actions()

        if not actions:
            return [0.0, 0.0]

        # Get or create node
        info_state_str = self._get_info_state(state, current_player)
        node = self.get_node(info_state_str)
        node.visits += 1

        # Compute strategy
        strategy = node.get_strategy(actions)

        # Sample action from strategy
        action = np.random.choice(actions, p=strategy)

        # Recursive call - prefer a safe `clone()` if the state provides it
        if hasattr(state, "clone") and callable(getattr(state, "clone")):
            next_state = state.clone()
        else:
            next_state = copy.deepcopy(state)
        next_state.apply_action(action)

        reach_probs_next = reach_probs[:]
        reach_probs_next[current_player] *= strategy[actions.index(action)]

        utilities = self._mccfr_iteration(next_state, reach_probs_next, depth + 1)

        # Update regrets
        u_current = utilities[current_player]
        for i, action in enumerate(actions):
            # Counterfactual value
            counterfactual_reach = 1.0
            for p in range(len(reach_probs)):
                if p != current_player:
                    counterfactual_reach *= reach_probs[p]

            counterfactual_util = (
                u_current
                if action == actions[np.argmax(strategy)]
                else utilities[current_player]
            )
            regret = counterfactual_util - u_current
            node.regrets[action] += regret * self.learning_rate * counterfactual_reach

        # Update strategy sum
        node.update_strategy(actions, strategy)

        return utilities

    def _get_info_state(self, state, player: int) -> str:
        """Get legible information state string."""
        obs = state.observation_tensor(player)
        return f"P{player}:" + ",".join(str(int(o)) for o in obs[:20])  # Simplified

    def get_best_action(self, state) -> int:
        """Get best action from current state using learned strategy."""
        if state.is_terminal():
            return None

        current_player = state.current_player()
        actions = state.legal_actions()

        if not actions:
            return None

        info_state_str = self._get_info_state(state, current_player)
        node = self.get_node(info_state_str) if info_state_str in self.nodes else None

        if node is None:
            # Random action if node not in tree
            return random.choice(actions)

        # Use average strategy
        avg_strategy = node.get_average_strategy(actions)
        best_action = actions[np.argmax(avg_strategy)]
        return best_action

    def save(self, filepath: str):
        """Save solver state."""
        data = {
            "nodes": self.nodes,
            "iterations": self.iterations,
            "payoff_sum": self.payoff_sum,
        }
        target_dir = os.path.dirname(filepath) or "."
        os.makedirs(target_dir, exist_ok=True)

        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                delete=False,
                dir=target_dir,
                prefix=".tmp_mccfr_",
                suffix=".pkl",
            ) as f:
                tmp_path = f.name
                pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, filepath)
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

    def load(self, filepath: str) -> bool:
        """Load solver state."""
        if not os.path.exists(filepath):
            return False
        if os.path.getsize(filepath) == 0:
            print(f"[MCCFR] Warning: Empty model file at {filepath}; starting fresh")
            return False

        try:
            with open(filepath, "rb") as f:
                data = pickle.load(f)
        except (EOFError, pickle.UnpicklingError, AttributeError, ValueError) as e:
            print(
                f"[MCCFR] Warning: Failed to load model from {filepath}: {e}; starting fresh"
            )
            return False

        if not isinstance(data, dict):
            print(
                f"[MCCFR] Warning: Unexpected model format in {filepath}; starting fresh"
            )
            return False

        self.nodes = data.get("nodes", {})
        self.iterations = data.get("iterations", 0)
        self.payoff_sum = data.get("payoff_sum", [0.0, 0.0])
        return True


class FafnirMCCFRAI:
    """MCCFR-based AI player for Fafnir."""

    def __init__(
        self,
        game_class,
        model_path: str = None,
        auto_train: bool = False,
        max_depth: int = 512,
    ):
        """
        Initialize AI.

        Args:
            game_class: OpenSpiel game class
            model_path: Path to save/load model
            auto_train: If True, automatically train on init if no model exists
        """
        self.game_class = game_class
        self.solver = MCCFRSolver(game_class, max_depth=max_depth)
        self.model_path = model_path or "fafnir_mccfr_model.pkl"

        # Try to load existing model
        if os.path.exists(self.model_path):
            print(f"[MCCFR AI] Loading existing model from {self.model_path}")
            if self.solver.load(self.model_path):
                print(
                    f"[MCCFR AI] Model loaded: {self.solver.iterations} iterations, {len(self.solver.nodes)} states"
                )
            else:
                print(
                    "[MCCFR AI] Failed to load model; initialized empty solver"
                )
        elif auto_train:
            # Auto train if requested and no model exists
            print("[MCCFR AI] No model found, starting initial training...")
            self.solver.run_mccfr(num_iterations=1000)
            self.save_model()
        else:
            # Just initialize empty solver
            print(
                f"[MCCFR AI] Initialized empty solver (no model at {self.model_path})"
            )
            print(f"[MCCFR AI] Use train() method to start training")

    def select_action(self, state) -> int:
        """Select best action for current state."""
        return self.solver.get_best_action(state)

    def train(self, num_iterations: int = 100, num_workers: int = 1):
        """Train the model further."""
        self.solver.run_mccfr(
            num_iterations=num_iterations, num_workers=num_workers, show_progress=True
        )
        self.save_model()

    def save_model(self):
        """Save trained model."""
        self.solver.save(self.model_path)
        print(f"[MCCFR AI] Model saved to {self.model_path}")

    def load_model(self):
        """Load trained model."""
        if self.solver.load(self.model_path):
            print(f"[MCCFR AI] Model loaded from {self.model_path}")
        else:
            print(
                f"[MCCFR AI] Failed to load model from {self.model_path}; using empty solver"
            )


# Simplified regret matching strategy
class SimpleRegretMatching:
    """Simple regret matching for baseline."""

    def __init__(self):
        self.cumulative_regrets: Dict[str, Dict[int, float]] = defaultdict(
            lambda: defaultdict(float)
        )

    def get_strategy(self, info_state: str, actions: List[int]) -> np.ndarray:
        """Get strategy using regret matching."""
        regrets = self.cumulative_regrets[info_state]
        strategy = np.array(
            [max(0.0, regrets.get(a, 0.0)) for a in actions], dtype=np.float32
        )

        total = np.sum(strategy)
        if total > 0:
            return strategy / total
        else:
            return np.ones(len(actions)) / len(actions)

    def update_regrets(
        self, info_state: str, actions: List[int], utilities: np.ndarray
    ):
        """Update cumulative regrets."""
        action_util = utilities
        for i, action in enumerate(actions):
            regret = action_util[i] - np.mean(action_util)
            self.cumulative_regrets[info_state][action] += regret


def _split_iterations(total: int, num_workers: int) -> List[int]:
    if num_workers <= 1:
        return [total]
    base = total // num_workers
    remainder = total % num_workers
    counts = [base + (1 if i < remainder else 0) for i in range(num_workers)]
    return [c for c in counts if c > 0]


def _mccfr_worker(job) -> Tuple[Dict[str, NodeInfo], int, List[float]]:
    game_class, num_iterations, learning_rate, exploration_bonus, max_depth, seed = job
    if seed is not None:
        np.random.seed(seed)
        random.seed(seed)

    solver = MCCFRSolver(
        game_class,
        learning_rate=learning_rate,
        exploration_bonus=exploration_bonus,
        max_depth=max_depth,
    )
    solver.run_mccfr(
        num_iterations=num_iterations, num_workers=1, show_progress=False
    )
    return solver.nodes, solver.iterations, solver.payoff_sum
