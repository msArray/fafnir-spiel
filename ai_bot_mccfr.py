# clients/ai_bot_mccfr.py
"""
MCCFR-based AI bot for Fafnir game server.
"""

import asyncio
import argparse
import random
from typing import Any, Dict, List, Optional
import socketio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fafnir_game import FafnirGame, FafnirGameState
from mccfr_ai import FafnirMCCFRAI, MCCFRSolver

sio = socketio.AsyncClient(reconnection=True)

cfg = {"room": "room1", "name": "MCCFR-AI", "url": "http://127.0.0.1:8765"}

my_index: Optional[int] = None
last_state: Optional[Dict[str, Any]] = None
ai_engine: Optional[FafnirMCCFRAI] = None

# Anti-spam
_action_lock = asyncio.Lock()
_last_emit_ts = 0.0

# OK debounce
_ok_sent_key: Optional[str] = None

AUTO_NEXT = True


def _loop_time() -> float:
    return asyncio.get_running_loop().time()


def safe_list(x: Any) -> List[Any]:
    return x if isinstance(x, list) else []


def phase_of(st: Dict[str, Any]) -> str:
    return str(st.get("phase") or "WAITING")


def current_bidder(st: Dict[str, Any]) -> Optional[int]:
    cb = st.get("current_bidder", None)
    try:
        return int(cb)
    except Exception:
        return None


def players_of(st: Dict[str, Any]) -> List[Dict[str, Any]]:
    ps = st.get("players")
    return ps if isinstance(ps, list) else []


def me_view(st: Dict[str, Any]) -> Dict[str, Any]:
    ps = players_of(st)
    if my_index is None or my_index < 0 or my_index >= len(ps):
        return {}
    v = ps[my_index]
    return v if isinstance(v, dict) else {}


def my_hand(st: Dict[str, Any]) -> List[str]:
    hand = me_view(st).get("hand")
    return [x for x in hand] if isinstance(hand, list) else []


def my_bid_submitted(st: Dict[str, Any]) -> bool:
    return bool(me_view(st).get("bid_submitted", False))


def my_ok_ready(st: Dict[str, Any]) -> bool:
    return bool(me_view(st).get("ok_ready", False))


def offer_set(st: Dict[str, Any]) -> set:
    offer = safe_list(st.get("offer"))
    return set([x for x in offer if isinstance(x, str)])


def _phase_key(st: Dict[str, Any]) -> str:
    """Use these as keys to prevent duplication."""
    ph = phase_of(st)
    r = st.get("round", "?")
    t = st.get("turn", "?")
    if ph == "ROUND_END":
        return f"ROUND_END:r{r}"
    if ph == "RESULT":
        return f"RESULT:r{r}:t{t}"
    return f"{ph}:r{r}:t{t}"


def reconstruct_game_state(server_state: Dict[str, Any]) -> Optional[FafnirGameState]:
    """
    Reconstruct internal game state from server state.
    This is a simplified reconstruction for AI decision-making.
    """
    try:
        # Create a new game state
        game = FafnirGame()
        state = game.new_initial_state()

        # The reconstruction is complex because we need to replay actions
        # For now, we'll use a simplified approach based on current state
        # In production, this should replay the game from log

        return state
    except Exception as e:
        print(f"[MCCFR AI] Error reconstructing state: {e}")
        return None


def encode_bid_action(hand: List[str], stones: List[str]) -> int:
    """Encode bid as bitmask action."""
    mask = 0
    for stone in stones:
        if stone in hand:
            idx = hand.index(stone)
            mask |= 1 << idx
    return mask


def decode_bid_action(hand: List[str], action: int) -> List[str]:
    """Decode bitmask action to stone list."""
    bid = []
    for i in range(len(hand)):
        if action & (1 << i):
            bid.append(hand[i])
    return bid


async def _emit_throttled(
    event: str, payload: Dict[str, Any], min_interval: float = 0.12
):
    global _last_emit_ts
    async with _action_lock:
        dt = _loop_time() - _last_emit_ts
        if dt < min_interval:
            await asyncio.sleep(min_interval - dt)
        _last_emit_ts = _loop_time()
        await sio.emit(event, payload)


async def suggest_bid_with_mccfr(st: Dict[str, Any]) -> List[str]:
    """
    Use MCCFR AI to suggest a bid.
    """
    global ai_engine

    # Try to reconstruct game state
    state = reconstruct_game_state(st)

    if state is None or ai_engine is None:
        # Fallback to heuristic
        hand = my_hand(st)
        bids_by_others = safe_list(st.get("offer", []))

        if not hand:
            return []

        # Conservative bidding: bid 1-2 coins
        n = random.randint(1, min(2, len(hand)))
        return random.sample(hand, n)

    try:
        # Get best action from MCCFR AI
        best_action = ai_engine.select_action(state)

        # Decode action
        hand = my_hand(st)
        if best_action is not None:
            bid = decode_bid_action(hand, best_action)
            print(f"[MCCFR AI] Selected action -> bid: {bid}")
            return bid
    except Exception as e:
        print(f"[MCCFR AI] Error in MCCFR selection: {e}")

    # Fallback
    hand = my_hand(st)
    if not hand:
        return []
    n = random.randint(1, min(2, len(hand)))
    return random.sample(hand, n)


async def do_submit_bid(st: Dict[str, Any], reason: str):
    hand = my_hand(st)

    if not hand:
        # Empty hand, send empty bid
        await asyncio.sleep(random.uniform(0.05, 0.1))
        await _emit_throttled("submit_bid", {"room_id": cfg["room"], "stones": []})
        print(f"[MCCFR-AI] submit ({reason}) stones=[] (empty hand)")
        return

    # Use MCCFR to suggest bid
    bid = await suggest_bid_with_mccfr(st)

    await asyncio.sleep(random.uniform(0.05, 0.15))
    await _emit_throttled("submit_bid", {"room_id": cfg["room"], "stones": bid})
    print(f"[MCCFR-AI] submit ({reason}) stones={bid}")


async def do_ok_next(st: Dict[str, Any], reason: str):
    global _ok_sent_key
    key = _phase_key(st)
    if _ok_sent_key == key:
        return
    if my_ok_ready(st):
        _ok_sent_key = key
        return

    await asyncio.sleep(random.uniform(0.05, 0.1))
    await _emit_throttled("proceed_phase", {"room_id": cfg["room"]})
    _ok_sent_key = key
    print(f"[MCCFR-AI] OK/Next ({reason})")


async def brain_loop():
    """
    Main AI loop - continuously monitors game state and makes decisions.
    """
    while True:
        st = last_state
        if st and my_index is not None and my_index >= 0:
            ph = phase_of(st)

            if ph == "BIDDING":
                cb = current_bidder(st)
                if cb == my_index and (not my_bid_submitted(st)):
                    await do_submit_bid(st, reason="brain_loop")

            elif ph in ("RESULT", "ROUND_END"):
                if AUTO_NEXT:
                    await do_ok_next(st, reason="brain_loop")

        await asyncio.sleep(0.10)


# ============ Socket handlers ============


@sio.event
async def connect():
    print("[MCCFR-AI] connected to server")
    await _emit_throttled(
        "join_room",
        {"room_id": cfg["room"], "player_name": cfg["name"]},
        min_interval=0.0,
    )


@sio.event
async def disconnect():
    print("[MCCFR-AI] disconnected from server")


@sio.on("player_assigned")
async def player_assigned(data):
    global my_index
    try:
        my_index = int(data.get("index"))
    except Exception:
        my_index = None
    print(f"[MCCFR-AI] assigned index = {my_index}")


@sio.on("state_update")
async def state_update(state):
    global last_state, _ok_sent_key
    last_state = state

    # Reset OK debounce when leaving RESULT/ROUND_END
    ph = phase_of(state)
    if ph not in ("RESULT", "ROUND_END"):
        _ok_sent_key = None


@sio.on("bid_rejected")
async def bid_rejected(data):
    """Handle bid rejection."""
    reason = data.get("reason") or ""
    msg = data.get("message") or reason
    print(f"[MCCFR-AI] BID REJECTED: {msg}")


# ============ Main ============


async def main():
    global AUTO_NEXT, ai_engine

    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8765")
    ap.add_argument("--room", default="room1")
    ap.add_argument("--name", default="MCCFR-AI")
    ap.add_argument("--model-path", default=None, help="Path to MCCFR model file")
    ap.add_argument(
        "--train-iterations", type=int, default=500, help="Training iterations"
    )
    ap.add_argument("--auto-next", type=int, default=1, help="Auto OK/Next")

    args = ap.parse_args()

    cfg["url"] = args.url
    cfg["room"] = args.room
    cfg["name"] = args.name

    AUTO_NEXT = bool(args.auto_next)

    # Initialize AI engine
    print("[MCCFR-AI] Initializing MCCFR AI engine...")
    try:
        game_class = FafnirGame
        ai_engine = FafnirMCCFRAI(
            game_class,
            model_path=args.model_path,
        )
        if args.train_iterations > 0:
            print(f"[MCCFR-AI] Additional training: {args.train_iterations} iterations")
            ai_engine.train(args.train_iterations)
    except Exception as e:
        print(f"[MCCFR-AI] Error initializing AI: {e}")
        print("[MCCFR-AI] Continuing with fallback strategy...")
        ai_engine = None

    task_brain = None
    try:
        print(f"[MCCFR-AI] Connecting to {cfg['url']}")
        await sio.connect(cfg["url"], wait_timeout=15)
        task_brain = asyncio.create_task(brain_loop())
        await sio.wait()
    except (KeyboardInterrupt, SystemExit):
        print("[MCCFR-AI] Shutting down...")
    finally:
        if task_brain:
            task_brain.cancel()
            try:
                await task_brain
            except Exception:
                pass
        try:
            if sio.connected:
                await sio.disconnect()
        except Exception:
            pass
        try:
            eio = getattr(sio, "eio", None)
            if eio is not None and getattr(eio, "connected", False):
                await eio.disconnect()
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())


async def main_with_config(url: str, room: str, name: str, model_path: str = None):
    """
    Entry point called from main.py with configuration.
    """
    global AUTO_NEXT, ai_engine, cfg

    cfg["url"] = url
    cfg["room"] = room
    cfg["name"] = name

    AUTO_NEXT = True

    # Initialize AI engine
    print("[MCCFR-AI] Initializing MCCFR AI engine...")
    try:
        game_class = FafnirGame
        model_file = model_path or "fafnir_mccfr_model.pkl"

        # Initialize AI without auto-training when loading model
        ai_engine = FafnirMCCFRAI(
            game_class,
            model_path=model_file,
            auto_train=False,  # Don't auto-train when loading for play
        )
        print(
            f"[MCCFR-AI] AI engine ready: {ai_engine.solver.iterations} iterations trained"
        )
        print(f"[MCCFR-AI] Learned states: {len(ai_engine.solver.nodes)}")

        if ai_engine.solver.iterations == 0:
            print("[MCCFR-AI] Warning: Model has 0 iterations (untrained)")
            print("[MCCFR-AI] Run: python main.py train --iterations 1000")

    except Exception as e:
        print(f"[MCCFR-AI] Error initializing AI: {e}")
        print("[MCCFR-AI] Continuing with fallback strategy...")
        import traceback

        traceback.print_exc()
        ai_engine = None

    task_brain = None
    try:
        print(f"[MCCFR-AI] Connecting to {cfg['url']}")
        await sio.connect(cfg["url"], wait_timeout=15)
        task_brain = asyncio.create_task(brain_loop())
        await sio.wait()
    except (KeyboardInterrupt, SystemExit):
        print("[MCCFR-AI] Shutting down...")
    finally:
        if task_brain:
            task_brain.cancel()
            try:
                await task_brain
            except Exception:
                pass
        try:
            if sio.connected:
                await sio.disconnect()
        except Exception:
            pass
        try:
            eio = getattr(sio, "eio", None)
            if eio is not None and getattr(eio, "connected", False):
                await eio.disconnect()
        except Exception:
            pass
