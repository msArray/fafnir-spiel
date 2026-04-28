"""
Main entry point for Fafnir MCCFR AI project.
"""

import sys
import argparse
import os


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Fafnir MCCFR AI using OpenSpiel")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Validate command
    subparsers.add_parser("validate", help="Validate implementation")

    # Test command
    subparsers.add_parser("test", help="Run test suite")

    # Train command
    train_parser = subparsers.add_parser("train", help="Train AI model")
    train_parser.add_argument(
        "--iterations", type=int, default=1000, help="Training iterations"
    )
    train_parser.add_argument(
        "--model-path", default="fafnir_mccfr_model.pkl", help="Model save path"
    )
    train_parser.add_argument(
        "--continue",
        dest="continue_train",
        action="store_true",
        help="Continue training from existing model (default)",
    )
    train_parser.add_argument(
        "--reset",
        action="store_true",
        help="Start fresh training (ignore existing model)",
    )

    # Play command
    play_parser = subparsers.add_parser("play", help="Play against server")
    play_parser.add_argument(
        "--url", default="http://127.0.0.1:8765", help="Server URL"
    )
    play_parser.add_argument("--room", default="room1", help="Room ID")
    play_parser.add_argument("--name", default="MCCFR-AI", help="Player name")
    play_parser.add_argument(
        "--model-path", default="fafnir_mccfr_model.pkl", help="Model path"
    )

    args = parser.parse_args()

    if args.command == "validate":
        print("Running validation...")
        try:
            import validate
        except Exception as e:
            print(f"✗ Validation failed: {e}")
            sys.exit(1)

    elif args.command == "test":
        print("Running test suite...")
        try:
            import test_fafnir

            test_fafnir.main()
        except Exception as e:
            print(f"✗ Tests failed: {e}")
            sys.exit(1)

    elif args.command == "train":
        from fafnir_game import FafnirGame
        from mccfr_ai import FafnirMCCFRAI

        model_exists = os.path.exists(args.model_path)

        # Determine training mode
        if args.reset:
            print(f"[TRAIN] Starting fresh training (--reset flag)")
            print(f"[TRAIN] Model path: {args.model_path}")
            if model_exists:
                print(
                    f"[TRAIN] Warning: Existing model at {args.model_path} will be overwritten"
                )
            # Delete any existing model to force reset
            try:
                os.remove(args.model_path)
            except:
                pass
            # Create fresh AI without loading existing model
            ai = FafnirMCCFRAI(FafnirGame, model_path=args.model_path, auto_train=False)
        else:
            if model_exists:
                print(f"[TRAIN] Continuing from existing model: {args.model_path}")
            else:
                print(
                    f"[TRAIN] No existing model found, starting fresh training: {args.model_path}"
                )
            # Load existing model or create new one
            ai = FafnirMCCFRAI(FafnirGame, model_path=args.model_path, auto_train=False)

        print(f"[TRAIN] Training {args.iterations} iterations...")
        print(
            f"[TRAIN] Current model state: {ai.solver.iterations} iterations completed"
        )

        ai.train(args.iterations)

        print(f"[TRAIN] ✓ Training complete!")
        print(f"[TRAIN] Total iterations: {ai.solver.iterations}")
        print(f"[TRAIN] Learned states: {len(ai.solver.nodes)}")
        print(f"[TRAIN] Model saved to: {args.model_path}")

    elif args.command == "play":
        import asyncio
        import ai_bot_mccfr

        # Configure bot
        ai_bot_mccfr.cfg["url"] = args.url
        ai_bot_mccfr.cfg["room"] = args.room
        ai_bot_mccfr.cfg["name"] = args.name

        print(f"[PLAY] Starting AI bot: {args.name}")
        print(f"[PLAY] Connecting to {args.url}/{args.room}")
        print(f"[PLAY] Using model: {args.model_path}")

        try:
            asyncio.run(
                ai_bot_mccfr.main_with_config(
                    args.url, args.room, args.name, args.model_path
                )
            )
        except KeyboardInterrupt:
            print(f"\n[PLAY] Bot stopped by user")
            sys.exit(0)
        except Exception as e:
            print(f"[PLAY] ✗ Error: {e}")
            import traceback

            traceback.print_exc()
            sys.exit(1)

    else:
        parser.print_help()
        print("\n=== Examples ===")
        print("Train for 1000 iterations:")
        print("  python main.py train --iterations 1000")
        print("\nContinue training existing model:")
        print(
            "  python main.py train --iterations 500 --model-path my_model.pkl --continue"
        )
        print("\nStart fresh training:")
        print("  python main.py train --iterations 1000 --reset")
        print("\nPlay on server:")
        print("  python main.py play --url http://localhost:8765 --room room1")


if __name__ == "__main__":
    main()
