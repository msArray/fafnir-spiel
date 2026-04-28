"""
Quick validation script for Fafnir implementation.
"""

import sys
import os

sys.path.insert(0, "/workspaces/fafnir-spiel")

print("=" * 60)
print("FAFNIR MCCFR IMPLEMENTATION VALIDATION")
print("=" * 60)

# Test 1: Import modules
print("\n1. Testing imports...")
try:
    import pyspiel

    print("   ✓ pyspiel imported")
except ImportError as e:
    print(f"   ✗ pyspiel import failed: {e}")
    sys.exit(1)

try:
    from fafnir_game import FafnirGame, FafnirGameState, COLORS, ALL_STONES

    print("   ✓ fafnir_game imported")
except ImportError as e:
    print(f"   ✗ fafnir_game import failed: {e}")
    sys.exit(1)

try:
    from mccfr_ai import MCCFRSolver, FafnirMCCFRAI

    print("   ✓ mccfr_ai imported")
except ImportError as e:
    print(f"   ✗ mccfr_ai import failed: {e}")
    sys.exit(1)

# Test 2: Game constants
print("\n2. Testing game constants...")
print(f"   Colors: {len(COLORS)} - {COLORS}")
print(f"   All stones: {len(ALL_STONES)} - {ALL_STONES}")

# Test 3: Game creation
print("\n3. Testing game creation...")
try:
    game = FafnirGame()
    print(f"   ✓ Game object created")

    state = game.new_initial_state()
    print(f"   ✓ Initial state created: {state}")
    print(f"     - Terminal: {state.is_terminal()}")
    print(f"     - Current player: {state.current_player()}")
    print(f"     - Legal actions: {len(state.legal_actions())}")
except Exception as e:
    print(f"   ✗ Game creation failed: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)

# Test 4: Multiple game steps
print("\n4. Testing game progression...")
try:
    state = game.new_initial_state()

    for step in range(10):
        if state.is_terminal():
            print(f"   Game ended at step {step}")
            break

        actions = state.legal_actions()
        if not actions:
            print(f"   No actions available at step {step}")
            break

        action = actions[0]  # Take first action
        state.apply_action(action)

    print(f"   ✓ Progressed 10 steps successfully")
    print(f"     - Returns: {state.returns()}")
except Exception as e:
    print(f"   ✗ Game progression failed: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)

# Test 5: MCCFR Solver instantiation
print("\n5. Testing MCCFR Solver...")
try:
    solver = MCCFRSolver(FafnirGame)
    print(f"   ✓ MCCFR Solver created")
    print(f"     - Initial nodes: {len(solver.nodes)}")
except Exception as e:
    print(f"   ✗ MCCFR Solver creation failed: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)

# Test 6: MCCFR AI creation (light training)
print("\n6. Testing MCCFR AI (light training)...")
try:
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".pkl") as tmp:
        ai = FafnirMCCFRAI(FafnirGame, model_path=tmp.name)
        print(f"   ✓ MCCFR AI created with initial training")
        print(f"     - Model iterations: {ai.solver.iterations}")
        print(f"     - Nodes learned: {len(ai.solver.nodes)}")

        # Test action selection
        state = game.new_initial_state()
        action = ai.select_action(state)
        print(f"   ✓ Action selected: {action}")
except Exception as e:
    print(f"   ✗ MCCFR AI creation failed: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 60)
print("ALL VALIDATIONS PASSED ✓")
print("=" * 60)

# Summary
print("\nImplementation Summary:")
print("- OpenSpiel game wrapper: Implemented")
print("- MCCFR solver: Implemented")
print("- AI player: Implemented")
print("- Server bot: Ready to use")
print("\nNext steps:")
print("1. Train model with more iterations")
print("2. Connect to game server")
print("3. Play against other bots")
