#!/usr/bin/env python
"""
Quick diagnostic script to check if the game initialization works.
"""

import sys
import os

print("=" * 60)
print("Fafnir Game Initialization Test")
print("=" * 60)

try:
    print("\n1. Importing modules...")
    from fafnir_game import FafnirGame

    print("   ✓ FafnirGame imported")

    print("\n2. Creating game instance...")
    game = FafnirGame()
    print("   ✓ Game created")

    print("\n3. Creating initial state...")
    state = game.new_initial_state()
    print("   ✓ Initial state created")
    print(f"   State: {state}")

    print("\n4. Testing basic game properties...")
    print(f"   - Is terminal: {state.is_terminal()}")
    print(f"   - Current player: {state.current_player()}")
    print(f"   - Num players: {game.num_players()}")
    print(f"   - Legal actions: {len(state.legal_actions())}")

    print("\n5. Testing game progression...")
    for i in range(5):
        if state.is_terminal():
            print(f"   Game ended at step {i}")
            break
        actions = state.legal_actions()
        action = actions[0]
        state.apply_action(action)
        print(f"   Step {i + 1}: Action {action}, Terminal: {state.is_terminal()}")

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED ✓")
    print("=" * 60)
    sys.exit(0)

except Exception as e:
    print(f"\n✗ ERROR: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)
