import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.game.engine import GameError

log = logging.getLogger(__name__)
router = APIRouter(tags=["realtime"])


@router.websocket("/ws/rooms/{room_id}")
async def room_socket(websocket: WebSocket, room_id: str, player_id: str) -> None:
    """Outbound-only state channel: snapshots and events, server -> client.

    Clients send nothing meaningful here; actions go over REST. That keeps the
    "server owns the truth" boundary impossible to accidentally cross.
    """
    engine = websocket.app.state.engine
    hub = websocket.app.state.hub

    try:
        room = engine.resolve(room_id)
    except GameError:
        await websocket.close(code=4404, reason="no such room")
        return
    if player_id not in room.state.players:
        await websocket.close(code=4403, reason="unknown player")
        return

    await websocket.accept()
    hub.add(room.state.room_id, websocket)
    try:
        await engine.snapshot_to(room, websocket)
        await engine.set_connected(room.state.room_id, player_id, True)
        while True:
            # Drain client pings; we have no inbound protocol.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        log.debug("socket error in room %s", room_id, exc_info=True)
    finally:
        hub.remove(room.state.room_id, websocket)
        await engine.set_connected(room.state.room_id, player_id, False)
