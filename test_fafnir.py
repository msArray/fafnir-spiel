"""
Test script for Fafnir game and MCCFR AI.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fafnir_game import FafnirGame, FafnirGameState
from mccfr_ai import FafnirMCCFRAI, MCCFRSolver
import numpy as np


def test_game_creation():
    """Test basic game creation."""
    print("\n=== Testing Game Creation ===")
    game = FafnirGame()
    state = game.new_initial_state()

    print(f"✓ Game created: {state}")
    print(f"  - Players: {game.num_players()}")
    print(f"  - Initial terminal: {state.is_terminal()}")
    print(f"  - Utility sum: {game.utility_sum()}")
    return state


def test_legal_actions(state):
    """Test legal actions."""
    print("\n=== Testing Legal Actions ===")
    actions = state.legal_actions()
    print(f"✓ Legal actions count: {len(actions)}")
    print(f"  - Current player: {state.current_player()}")
    print(f"  - Is terminal: {state.is_terminal()}")
    return actions


def test_game_play_deterministic():
    """Play through a game with deterministic strategy."""
    print("\n=== Testing Game Play ===")
    game = FafnirGame()
    state = game.new_initial_state()

    move_count = 0
    max_moves = 500

    while not state.is_terminal() and move_count < max_moves:
        actions = state.legal_actions()
        if not actions:
            break

        # Always pick first legal action (deterministic)
        action = actions[0]
        state.apply_action(action)
        move_count += 1

        if move_count % 50 == 0:
            print(f"  Move {move_count}: {state}")

    print(f"✓ Game finished after {move_count} moves")
    print(f"  - Terminal: {state.is_terminal()}")
    print(f"  - Returns: {state.returns()}")
    return state


def test_mccfr_solver():
    """Test MCCFR solver."""
    print("\n=== Testing MCCFR Solver ===")
    game = FafnirGame

    solver = MCCFRSolver(game, learning_rate=0.1)

    print("  Training solver...")
    solver.run_mccfr(num_iterations=100)

    print(f"✓ Solver trained")
    print(f"  - Iterations: {solver.iterations}")
    print(f"  - Nodes: {len(solver.nodes)}")
    print(f"  - Avg payoff P0: {solver.payoff_sum[0] / solver.iterations:.4f}")
    print(f"  - Avg payoff P1: {solver.payoff_sum[1] / solver.iterations:.4f}")

    return solver


def test_mccfr_ai():
    """Test MCCFR AI creation and action selection."""
    print("\n=== Testing MCCFR AI ===")

    ai = FafnirMCCFRAI(FafnirGame, model_path="/tmp/test_fafnir_ai.pkl")

    print("✓ AI created")
    print(f"  - Model iterations: {ai.solver.iterations}")

    # Test selecting action
    state = FafnirGame().new_initial_state()
    action = ai.select_action(state)

    print(f"✓ Action selected: {action}")

    return ai


def test_observation_tensor():
    """Test observation tensor generation."""
    print("\n=== Testing Observation Tensor ===")
    game = FafnirGame()
    state = game.new_initial_state()

    for player in range(2):
        obs = state.observation_tensor(player)
        print(f"✓ Player {player} observation shape: {obs.shape}")
        print(f"  - Non-zero elements: {np.count_nonzero(obs)}")
        print(f"  - Min value: {obs.min():.4f}, Max value: {obs.max():.4f}")


def test_game_flow():
    """Test complete game flow simulation."""
    print("\n=== Testing Complete Game Flow ===")
    game = FafnirGame()
    state = game.new_initial_state()

    # Create two simple players: random and first-action
    move_count = 0
    player_stats = [0, 0]

    while not state.is_terminal() and move_count < 300:
        actions = state.legal_actions()
        if not actions:
            break

        current = state.current_player()

        # Strategy: player 0 uses first action, player 1 uses random
        if current == 0:
            action = actions[0]
        else:
            action = np.random.choice(actions)

        state.apply_action(action)
        player_stats[current] += 1
        move_count += 1

    returns = state.returns()
    print(f"✓ Game completed in {move_count} moves")
    print(f"  - Player 0 moves: {player_stats[0]}")
    print(f"  - Player 1 moves: {player_stats[1]}")
    print(f"  - Returns: {returns}")
    print(f"  - Winner: Player {0 if returns[0] > returns[1] else 1}")


def main():
    print("=" * 60)
    print("FAFNIR GAME & MCCFR AI TEST SUITE")
    print("=" * 60)

    try:
        # Test 1: Game creation
        state = test_game_creation()

        # Test 2: Legal actions
        test_legal_actions(state)

        # Test 3: Observation tensor
        test_observation_tensor()

        # Test 4: Deterministic game play
        test_game_play_deterministic()

        # Test 5: Game flow with different strategies
        test_game_flow()

        # Test 6: MCCFR Solver
        test_mccfr_solver()

        # Test 7: MCCFR AI
        test_mccfr_ai()

        print("\n" + "=" * 60)
        print("ALL TESTS PASSED ✓")
        print("=" * 60)

    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
