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
import heapq
import gzip


GZIP_MAGIC = b"\x1f\x8b"


@dataclass
class NodeInfo:
    """Information about a game tree node."""

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
        max_nodes: Optional[int] = None,
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
        self.nodes: Dict[bytes, NodeInfo] = {}
        self.iterations = 0
        self.payoff_sum = [0.0, 0.0]
        self.max_nodes = max_nodes if max_nodes and max_nodes > 0 else None
        self._max_nodes_warning_emitted = False

    def get_node(self, info_state_key: bytes) -> Optional[NodeInfo]:
        """Get or create node."""
        node = self.nodes.get(info_state_key)
        if node is not None:
            return node

        if self.max_nodes is not None and len(self.nodes) >= self.max_nodes:
            if not self._max_nodes_warning_emitted:
                print(
                    f"[MCCFR] Warning: max_nodes {self.max_nodes} reached; skipping new nodes"
                )
                self._max_nodes_warning_emitted = True
            return None

        node = NodeInfo()
        self.nodes[info_state_key] = node
        return node

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
                self.max_nodes,
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
        worker_nodes: Dict[bytes, NodeInfo],
        worker_iterations: int,
        worker_payoff_sum: List[float],
    ):
        for info_state_key, worker_node in worker_nodes.items():
            node = self.nodes.get(info_state_key)
            if node is None:
                if self.max_nodes is not None and len(self.nodes) >= self.max_nodes:
                    if not self._max_nodes_warning_emitted:
                        print(
                            f"[MCCFR] Warning: max_nodes {self.max_nodes} reached; skipping new nodes"
                        )
                        self._max_nodes_warning_emitted = True
                    continue
                self.nodes[info_state_key] = worker_node
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
        info_state_key = self._get_info_state_key(state, current_player)
        node = self.get_node(info_state_key)
        if node is None:
            # Skip updates when max_nodes reached; fall back to uniform random action
            action = random.choice(actions)
            if hasattr(state, "clone") and callable(getattr(state, "clone")):
                next_state = state.clone()
            else:
                next_state = copy.deepcopy(state)
            next_state.apply_action(action)
            reach_probs_next = reach_probs[:]
            reach_probs_next[current_player] *= 1.0 / len(actions)
            return self._mccfr_iteration(next_state, reach_probs_next, depth + 1)

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

    def _get_info_state_key(self, state, player: int) -> bytes:
        """Get a compact, hashable information-state key."""
        obs = np.asarray(state.observation_tensor(player), dtype=np.int32)
        # Prefix the active player so both perspectives remain distinct.
        return bytes([player]) + obs.tobytes()

    def _coerce_info_state_key(self, info_state) -> bytes:
        """Normalize legacy and current model keys to the compact byte format."""
        if isinstance(info_state, bytes):
            return info_state
        if isinstance(info_state, str):
            try:
                player_part, observation_part = info_state.split(":", 1)
                player = int(player_part[1:])
                observation_values = [
                    int(value) for value in observation_part.split(",") if value
                ]
                observation_array = np.asarray(observation_values, dtype=np.int32)
                return bytes([player]) + observation_array.tobytes()
            except (ValueError, IndexError):
                return info_state.encode("utf-8", errors="surrogatepass")
        return str(info_state).encode("utf-8", errors="surrogatepass")

    def get_best_action(self, state) -> int:
        """Get best action from current state using learned strategy."""
        if state.is_terminal():
            return None

        current_player = state.current_player()
        actions = state.legal_actions()

        if not actions:
            return None

        info_state_key = self._get_info_state_key(state, current_player)
        node = self.get_node(info_state_key) if info_state_key in self.nodes else None

        if node is None:
            # Random action if node not in tree
            return random.choice(actions)

        # Use average strategy
        avg_strategy = node.get_average_strategy(actions)
        best_action = actions[np.argmax(avg_strategy)]
        return best_action

    def save(
        self,
        filepath: str,
        shard_size: Optional[int] = None,
        quantize_dtype: Optional[str] = None,
        compress: bool = False,
    ):
        """Save solver state.

        If shard_size is provided and > 0, nodes are saved into multiple shard
        files to reduce peak memory usage during pickling.
        """
        resolved_dtype = self._resolve_quantize_dtype(quantize_dtype)
        if shard_size is not None and shard_size > 0:
            self._save_sharded(
                filepath,
                shard_size,
                quantize_dtype=resolved_dtype,
                compress=compress,
            )
            return

        nodes = (
            self._quantize_nodes(self.nodes, resolved_dtype)
            if resolved_dtype is not None
            else self.nodes
        )
        data = {
            "nodes": nodes,
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
                if compress:
                    with gzip.GzipFile(fileobj=f, mode="wb") as gz:
                        pickle.dump(data, gz, protocol=pickle.HIGHEST_PROTOCOL)
                        gz.flush()
                else:
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

    def load(
        self,
        filepath: str,
        max_nodes: Optional[int] = None,
        dequantize: bool = False,
    ) -> bool:
        """Load solver state."""
        if os.path.isdir(filepath):
            return self._load_sharded(
                filepath, max_nodes=max_nodes, dequantize=dequantize
            )

        shard_dir = f"{filepath}.shards"
        if not os.path.exists(filepath) and os.path.isdir(shard_dir):
            return self._load_sharded(
                shard_dir, max_nodes=max_nodes, dequantize=dequantize
            )

        if not os.path.exists(filepath):
            return False
        if os.path.getsize(filepath) == 0:
            print(f"[MCCFR] Warning: Empty model file at {filepath}; starting fresh")
            return False

        try:
            data = self._load_pickle_file(filepath)
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

        loaded_nodes = data.get("nodes", {})
        if isinstance(loaded_nodes, dict):
            if all(isinstance(key, bytes) for key in loaded_nodes.keys()):
                self.nodes = loaded_nodes
            else:
                self.nodes = {
                    self._coerce_info_state_key(info_state): node
                    for info_state, node in loaded_nodes.items()
                }
        else:
            self.nodes = {}
        self.iterations = data.get("iterations", 0)
        self.payoff_sum = data.get("payoff_sum", [0.0, 0.0])
        self._limit_loaded_nodes(max_nodes)
        self._maybe_dequantize_nodes(dequantize)
        return True

    def _resolve_quantize_dtype(self, quantize_dtype: Optional[str]):
        if quantize_dtype is None:
            return None
        if isinstance(quantize_dtype, str):
            normalized = quantize_dtype.strip().lower()
            if normalized in {"none", "off", "false", "0"}:
                return None
            if normalized in {"float16", "fp16", "f16"}:
                return np.float16
        if quantize_dtype is np.float16:
            return np.float16
        raise ValueError(f"Unsupported quantize dtype: {quantize_dtype}")

    def _quantize_nodes(
        self,
        nodes: Dict[bytes, NodeInfo],
        dtype,
    ) -> Dict[bytes, NodeInfo]:
        if dtype is None:
            return nodes
        return {key: self._quantize_node(node, dtype) for key, node in nodes.items()}

    def _quantize_node(self, node: "NodeInfo", dtype) -> "NodeInfo":
        quantized = NodeInfo()
        cast = dtype
        for action, value in node.regrets.items():
            quantized.regrets[action] = cast(value)
        for action, value in node.strategy_sums.items():
            quantized.strategy_sums[action] = cast(value)
        quantized.visits = node.visits
        return quantized

    def _maybe_dequantize_nodes(self, dequantize: bool):
        if not dequantize:
            return
        for node in self.nodes.values():
            if not isinstance(node, NodeInfo):
                continue
            for action, value in list(node.regrets.items()):
                node.regrets[action] = float(value)
            for action, value in list(node.strategy_sums.items()):
                node.strategy_sums[action] = float(value)

    def _limit_loaded_nodes(self, max_nodes: Optional[int]):
        if max_nodes is None or max_nodes <= 0:
            return
        if len(self.nodes) <= max_nodes:
            return

        heap = []
        for key, node in self.nodes.items():
            self._push_top_node(heap, max_nodes, key, node)
        self.nodes = {key: node for _, key, node in heap}

    def _push_top_node(self, heap, max_nodes: int, key: bytes, node: "NodeInfo"):
        visits = getattr(node, "visits", 0)
        entry = (visits, key, node)
        if len(heap) < max_nodes:
            heapq.heappush(heap, entry)
            return
        if visits > heap[0][0]:
            heapq.heapreplace(heap, entry)

    def _save_sharded(
        self,
        filepath: str,
        shard_size: int,
        quantize_dtype=None,
        compress: bool = False,
    ):
        shard_dir = filepath if os.path.isdir(filepath) else f"{filepath}.shards"
        os.makedirs(shard_dir, exist_ok=True)

        # Remove old shard files to avoid stale leftovers on smaller saves.
        for filename in os.listdir(shard_dir):
            if filename.startswith("nodes_") and filename.endswith(".pkl"):
                try:
                    os.remove(os.path.join(shard_dir, filename))
                except OSError:
                    pass

        meta = {
            "format_version": 1,
            "iterations": self.iterations,
            "payoff_sum": self.payoff_sum,
            "node_count": len(self.nodes),
            "shard_size": shard_size,
            "quantized_dtype": "float16" if quantize_dtype is np.float16 else None,
            "compressed": bool(compress),
        }
        self._atomic_pickle_dump(
            meta, os.path.join(shard_dir, "meta.pkl"), compress=compress
        )

        shard_index = 0
        chunk: Dict[bytes, NodeInfo] = {}
        for info_state_key, node in self.nodes.items():
            chunk[info_state_key] = node
            if len(chunk) >= shard_size:
                shard_path = os.path.join(shard_dir, f"nodes_{shard_index:05d}.pkl")
                payload = (
                    self._quantize_nodes(chunk, quantize_dtype)
                    if quantize_dtype is not None
                    else chunk
                )
                self._atomic_pickle_dump(payload, shard_path, compress=compress)
                shard_index += 1
                chunk = {}

        if chunk:
            shard_path = os.path.join(shard_dir, f"nodes_{shard_index:05d}.pkl")
            payload = (
                self._quantize_nodes(chunk, quantize_dtype)
                if quantize_dtype is not None
                else chunk
            )
            self._atomic_pickle_dump(payload, shard_path, compress=compress)

    def _load_sharded(
        self,
        shard_dir: str,
        max_nodes: Optional[int] = None,
        dequantize: bool = False,
    ) -> bool:
        meta_path = os.path.join(shard_dir, "meta.pkl")
        if not os.path.exists(meta_path):
            print(
                f"[MCCFR] Warning: Missing shard metadata at {meta_path}; starting fresh"
            )
            return False

        try:
            meta = self._load_pickle_file(meta_path)
        except (EOFError, pickle.UnpicklingError, AttributeError, ValueError) as e:
            print(
                f"[MCCFR] Warning: Failed to load shard metadata from {meta_path}: {e}; starting fresh"
            )
            return False

        shard_files = sorted(
            name
            for name in os.listdir(shard_dir)
            if name.startswith("nodes_") and name.endswith(".pkl")
        )

        max_nodes = max_nodes if max_nodes and max_nodes > 0 else None
        if max_nodes is None:
            self.nodes = {}
            for name in shard_files:
                shard_path = os.path.join(shard_dir, name)
                try:
                    shard_nodes = self._load_pickle_file(shard_path)
                except (EOFError, pickle.UnpicklingError, AttributeError, ValueError) as e:
                    print(
                        f"[MCCFR] Warning: Failed to load shard {shard_path}: {e}; skipping"
                    )
                    continue

                if isinstance(shard_nodes, dict):
                    for info_state, node in shard_nodes.items():
                        key = self._coerce_info_state_key(info_state)
                        self.nodes[key] = node
        else:
            heap = []
            for name in shard_files:
                shard_path = os.path.join(shard_dir, name)
                try:
                    shard_nodes = self._load_pickle_file(shard_path)
                except (EOFError, pickle.UnpicklingError, AttributeError, ValueError) as e:
                    print(
                        f"[MCCFR] Warning: Failed to load shard {shard_path}: {e}; skipping"
                    )
                    continue

                if isinstance(shard_nodes, dict):
                    for info_state, node in shard_nodes.items():
                        key = self._coerce_info_state_key(info_state)
                        self._push_top_node(heap, max_nodes, key, node)

            self.nodes = {key: node for _, key, node in heap}

        self.iterations = meta.get("iterations", 0)
        self.payoff_sum = meta.get("payoff_sum", [0.0, 0.0])
        self._maybe_dequantize_nodes(dequantize)
        return True

    def _atomic_pickle_dump(self, data, filepath: str, compress: bool = False):
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
                if compress:
                    with gzip.GzipFile(fileobj=f, mode="wb") as gz:
                        pickle.dump(data, gz, protocol=pickle.HIGHEST_PROTOCOL)
                        gz.flush()
                else:
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

    def _load_pickle_file(self, filepath: str):
        with open(filepath, "rb") as f:
            magic = f.read(2)
        if magic == GZIP_MAGIC:
            with gzip.open(filepath, "rb") as f:
                return pickle.load(f)
        with open(filepath, "rb") as f:
            return pickle.load(f)


class FafnirMCCFRAI:
    """MCCFR-based AI player for Fafnir."""

    def __init__(
        self,
        game_class,
        model_path: str = None,
        auto_train: bool = False,
        max_depth: int = 512,
        max_nodes: Optional[int] = None,
        load_max_nodes: Optional[int] = None,
        load_dequantize: bool = False,
    ):
        """
        Initialize AI.

        Args:
            game_class: OpenSpiel game class
            model_path: Path to save/load model
            auto_train: If True, automatically train on init if no model exists
        """
        self.game_class = game_class
        self.solver = MCCFRSolver(
            game_class, max_depth=max_depth, max_nodes=max_nodes
        )
        self.model_path = model_path or "fafnir_mccfr_model.pkl"

        # Try to load existing model
        model_available = (
            os.path.exists(self.model_path)
            or os.path.isdir(self.model_path)
            or os.path.isdir(f"{self.model_path}.shards")
        )
        if model_available:
            print(f"[MCCFR AI] Loading existing model from {self.model_path}")
            if self.solver.load(
                self.model_path,
                max_nodes=load_max_nodes,
                dequantize=load_dequantize,
            ):
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

    def train(
        self,
        num_iterations: int = 100,
        num_workers: int = 1,
        save_shard_size: Optional[int] = None,
        save_quantize: Optional[str] = None,
        save_compress: bool = False,
    ):
        """Train the model further."""
        self.solver.run_mccfr(
            num_iterations=num_iterations, num_workers=num_workers, show_progress=True
        )
        self.save_model(
            shard_size=save_shard_size,
            save_quantize=save_quantize,
            save_compress=save_compress,
        )

    def save_model(
        self,
        shard_size: Optional[int] = None,
        save_quantize: Optional[str] = None,
        save_compress: bool = False,
    ):
        """Save trained model."""
        self.solver.save(
            self.model_path,
            shard_size=shard_size,
            quantize_dtype=save_quantize,
            compress=save_compress,
        )
        if shard_size is not None and shard_size > 0:
            shard_dir = (
                self.model_path
                if os.path.isdir(self.model_path)
                else f"{self.model_path}.shards"
            )
            print(f"[MCCFR AI] Model shards saved to {shard_dir}")
        else:
            print(f"[MCCFR AI] Model saved to {self.model_path}")

    def load_model(
        self,
        load_max_nodes: Optional[int] = None,
        load_dequantize: bool = False,
    ):
        """Load trained model."""
        if self.solver.load(
            self.model_path,
            max_nodes=load_max_nodes,
            dequantize=load_dequantize,
        ):
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
    (
        game_class,
        num_iterations,
        learning_rate,
        exploration_bonus,
        max_depth,
        max_nodes,
        seed,
    ) = job
    if seed is not None:
        np.random.seed(seed)
        random.seed(seed)

    solver = MCCFRSolver(
        game_class,
        learning_rate=learning_rate,
        exploration_bonus=exploration_bonus,
        max_depth=max_depth,
        max_nodes=max_nodes,
    )
    solver.run_mccfr(
        num_iterations=num_iterations, num_workers=1, show_progress=False
    )
    return solver.nodes, solver.iterations, solver.payoff_sum
