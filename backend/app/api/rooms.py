from fastapi import APIRouter, HTTPException

from app.api.deps import EngineDep
from app.game.engine import GameError
from app.models import CreateRoomRequest, GameState, JoinRoomRequest, PlayerSession

router = APIRouter(prefix="/api/rooms", tags=["rooms"])


@router.post("", response_model=PlayerSession, status_code=201)
async def create_room(body: CreateRoomRequest, engine: EngineDep) -> PlayerSession:
    room, host_id = await engine.create_room(body.name)
    return PlayerSession(
        room_id=room.state.room_id,
        join_code=room.state.join_code,
        player_id=host_id,
        state=room.state,
    )


@router.post("/{room_id}/join", response_model=PlayerSession)
async def join_room(room_id: str, body: JoinRoomRequest, engine: EngineDep) -> PlayerSession:
    """`room_id` accepts either a full room id or the short join code."""
    try:
        room = engine.resolve(room_id)
        player_id = await engine.join(room.state.room_id, body.name)
    except GameError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return PlayerSession(
        room_id=room.state.room_id,
        join_code=room.state.join_code,
        player_id=player_id,
        state=room.state,
    )


@router.get("/{room_id}", response_model=GameState)
async def get_room(room_id: str, engine: EngineDep) -> GameState:
    """REST fallback for the WS snapshot -- handy for curl and for cold page loads."""
    try:
        return engine.resolve(room_id).state
    except GameError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post("/{room_id}/start", status_code=202)
async def start_game(room_id: str, player_id: str, engine: EngineDep) -> dict[str, str]:
    try:
        await engine.start_game(room_id, player_id)
    except GameError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return {"status": "started"}
