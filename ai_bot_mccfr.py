# clients/ai_bot_mccfr.py
"""
MCCFR-based AI bot for Fafnir game server.
"""

import asyncio
import argparse
import random
from typing import Any, Dict, List, Optional
from collections import defaultdict
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

# Opponent memory (kept in RAM only; persists across matches while running).
opponent_memory: Dict[str, Dict[str, Any]] = {}
_last_result_sig: Optional[tuple] = None

# Anti-spam
_action_lock = asyncio.Lock()
_last_emit_ts = 0.0

# OK debounce
_ok_sent_key: Optional[str] = None

AUTO_NEXT = True
ALLOW_EMPTY_BID = False


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


def _opponent_key(st: Dict[str, Any]) -> str:
    ps = players_of(st)
    if my_index is None or len(ps) < 2:
        return "unknown"
    opp_idx = 1 - my_index
    opp_view = ps[opp_idx] if 0 <= opp_idx < len(ps) else {}
    if isinstance(opp_view, dict):
        name = opp_view.get("name")
        if name:
            return f"name:{name}"
    return f"idx:{opp_idx}"


def _get_opponent_stats(key: str) -> Dict[str, Any]:
    stats = opponent_memory.get(key)
    if stats is None:
        stats = {
            "turns": 0,
            "sum_bid_size": 0,
            "color_counts": defaultdict(int),
        }
        opponent_memory[key] = stats
    return stats


def _update_opponent_memory_from_state(st: Dict[str, Any]):
    global _last_result_sig

    if my_index is None:
        return

    last_result = st.get("last_result")
    if not isinstance(last_result, dict) or not last_result:
        return

    bids_by_player = last_result.get("bids_by_player")
    if not isinstance(bids_by_player, list) or len(bids_by_player) < 2:
        return

    # Avoid duplicate updates for the same resolved auction.
    round_no = st.get("round")
    turn_no = st.get("turn")
    winner = last_result.get("winner")
    sig = (
        round_no,
        turn_no,
        winner,
        tuple(tuple(x for x in (b or []) if isinstance(x, str)) for b in bids_by_player),
    )
    if sig == _last_result_sig:
        return
    _last_result_sig = sig

    opp_idx = 1 - my_index
    opp_bid_raw = bids_by_player[opp_idx] if 0 <= opp_idx < len(bids_by_player) else []
    opp_bid = [x for x in (opp_bid_raw or []) if isinstance(x, str)]

    stats = _get_opponent_stats(_opponent_key(st))
    stats["turns"] += 1
    stats["sum_bid_size"] += len(opp_bid)
    for stone in opp_bid:
        stats["color_counts"][stone] += 1


def _target_bid_size_from_stats(stats: Dict[str, Any], max_size: int) -> Optional[int]:
    turns = int(stats.get("turns") or 0)
    if turns < 3:
        return None
    avg = float(stats.get("sum_bid_size") or 0.0) / max(1, turns)
    target = int(round(avg))
    if avg <= 1.2:
        target += 1

    min_size = 0 if ALLOW_EMPTY_BID else 1
    return max(min_size, min(max_size, target))


def _adjust_bid_by_opponent(hand: List[str], forbidden: set, bid: List[str], st: Dict[str, Any]) -> List[str]:
    key = _opponent_key(st)
    stats = opponent_memory.get(key)
    if not stats:
        return bid

    candidates = [x for x in hand if x not in forbidden]
    if not candidates:
        return bid

    target = _target_bid_size_from_stats(stats, len(candidates))
    if target is None:
        return bid

    current = [x for x in bid if x in candidates]
    if target == len(current):
        return current

    if target > len(current):
        # Add stones from remaining candidates (multiset-aware).
        available = candidates[:]
        for stone in current:
            if stone in available:
                available.remove(stone)
        need = min(target - len(current), len(available))
        if need > 0:
            current.extend(random.sample(available, need))
        return current

    # Trim if too large; keep as close to the current bid as possible.
    return current[:target]


def sanitize_bid(proposal: List[str], hand: List[str], forbidden: set) -> List[str]:
    """
    - Avoid colors listed in the offer.
    - Must be a multiset of the current hand.
    """
    tmp = hand[:]
    out: List[str] = []
    for s in proposal:
        if not isinstance(s, str):
            continue
        if s in forbidden:
            continue
        if s in tmp:
            out.append(s)
            tmp.remove(s)
    return out


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
        forbidden = offer_set(st)

        if not hand:
            return []

        candidates = [x for x in hand if x not in forbidden]
        if not candidates:
            return []

        # Conservative bidding: bid 1-2 coins
        n = random.randint(1, min(2, len(candidates)))
        return random.sample(candidates, n)

    try:
        # Get best action from MCCFR AI
        best_action = ai_engine.select_action(state)

        # Decode action and enforce server-side legality
        hand = my_hand(st)
        forbidden = offer_set(st)
        if best_action is not None:
            if best_action >= (1 << len(hand)):
                proposal: List[str] = []
            else:
                proposal = decode_bid_action(hand, best_action)

            bid = sanitize_bid(proposal, hand, forbidden)
            if (not ALLOW_EMPTY_BID) and (len(bid) == 0) and hand:
                candidates = [x for x in hand if x not in forbidden]
                if candidates:
                    bid = [random.choice(candidates)]

            bid = _adjust_bid_by_opponent(hand, forbidden, bid, st)

            print(
                f"[MCCFR AI] Selected action -> proposal: {proposal} | bid: {bid}"
            )
            return bid
    except Exception as e:
        print(f"[MCCFR AI] Error in MCCFR selection: {e}")

    # Fallback
    hand = my_hand(st)
    if not hand:
        return []

    forbidden = offer_set(st)
    candidates = [x for x in hand if x not in forbidden]
    if not candidates:
        return []

    n = random.randint(1, min(2, len(candidates)))
    bid = random.sample(candidates, n)
    return _adjust_bid_by_opponent(hand, forbidden, bid, st)


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

    if ph == "GAME_END":
        # Allow new games to be learned even if bids repeat.
        global _last_result_sig
        _last_result_sig = None
        return

    _update_opponent_memory_from_state(state)


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
    ap.add_argument(
        "--load-max-nodes",
        type=int,
        default=None,
        help="Max number of nodes to load (None = load all)",
    )
    ap.add_argument(
        "--load-quantized",
        action="store_true",
        help="Keep quantized values on load (lower memory, lower precision)",
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
            load_max_nodes=args.load_max_nodes,
            load_dequantize=not args.load_quantized,
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


async def main_with_config(
    url: str,
    room: str,
    name: str,
    model_path: str = None,
    load_max_nodes: int = None,
    load_quantized: bool = False,
):
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
            load_max_nodes=load_max_nodes,
            load_dequantize=not load_quantized,
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
