from fastapi import APIRouter, HTTPException

from app.api.deps import EngineDep
from app.game.engine import GameError
from app.models import (
    CreateRoomRequest,
    GameState,
    JoinRoomRequest,
    LeaveRoomResponse,
    PlayerSession,
)

router = APIRouter(prefix="/api/rooms", tags=["rooms"])


@router.post("", response_model=PlayerSession, status_code=201)
async def create_room(body: CreateRoomRequest, engine: EngineDep) -> PlayerSession:
    try:
        room, host_id = await engine.create_room(body.name)
    except GameError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
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
        room = engine.resolve(body.join_code or room_id)
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


@router.post("/{room_id}/rounds", status_code=200)
async def set_rounds(
    room_id: str, player_id: str, rounds: int, engine: EngineDep
) -> dict[str, int]:
    """Host only, in the lobby: how many rounds the next game plays (5 or 10)."""
    try:
        await engine.set_rounds(room_id, player_id, rounds)
    except GameError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return {"rounds_per_game": rounds}


@router.post("/{room_id}/restart", status_code=200)
async def restart_game(room_id: str, player_id: str, engine: EngineDep) -> dict[str, str]:
    """Host only, after `game_over`: clears every score and returns the room to its lobby.

    The next game is not started here -- the lobby is what lets new players in between
    games, and the host starts it with `POST /start` as usual.
    """
    try:
        await engine.restart_game(room_id, player_id)
    except GameError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return {"status": "lobby"}


@router.post("/{room_id}/leave", response_model=LeaveRoomResponse)
async def leave_room(room_id: str, player_id: str, engine: EngineDep) -> LeaveRoomResponse:
    """Give up this player's seat. The last player out destroys the room."""
    try:
        destroyed = await engine.leave(room_id, player_id)
    except GameError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return LeaveRoomResponse(room_destroyed=destroyed)
