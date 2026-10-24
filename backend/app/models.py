"""Wire DTOs. These are the contract the React client mirrors in `frontend/src/types.ts`."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Phase(str, Enum):
    LOBBY = "lobby"
    ROUND = "round"
    SCORING = "scoring"
    GAME_OVER = "game_over"


class SubmissionStatus(str, Enum):
    PENDING = "pending"
    DONE = "done"
    FAILED = "failed"


class ProcessResult(BaseModel):
    """Whatever your processor decides about one frame. Extend freely via `meta`."""

    score: float
    label: str
    confidence: float = Field(ge=0.0, le=1.0)
    meta: dict[str, Any] = Field(default_factory=dict)


class Submission(BaseModel):
    id: str
    player_id: str
    round_no: int
    received_at: datetime
    status: SubmissionStatus = SubmissionStatus.PENDING
    result: ProcessResult | None = None
    error: str | None = None


class Player(BaseModel):
    id: str
    name: str
    connected: bool = False
    score: float = 0.0
    joined_at: datetime = Field(default_factory=utcnow)
    # Server-side only bookkeeping, harmless to expose: drives the rate limiter.
    last_frame_at: datetime | None = None


class Round(BaseModel):
    number: int
    prompt: str
    started_at: datetime
    ends_at: datetime
    # One slot per player: the newest frame wins, which is what you want for live capture.
    submissions: dict[str, Submission] = Field(default_factory=dict)


class GameConfig(BaseModel):
    """Echoed to clients so the UI never hardcodes timings."""

    round_seconds: int
    rounds_per_game: int
    capture_interval_ms: int


class GameState(BaseModel):
    room_id: str
    join_code: str
    phase: Phase = Phase.LOBBY
    host_id: str
    round: Round | None = None
    players: dict[str, Player] = Field(default_factory=dict)
    config: GameConfig
    # Monotonic. Clients drop any snapshot that is not strictly newer than the last seen.
    seq: int = 0
    server_time: datetime = Field(default_factory=utcnow)


# --- websocket envelopes -------------------------------------------------


class StateMessage(BaseModel):
    type: Literal["state"] = "state"
    seq: int
    state: GameState


class EventMessage(BaseModel):
    type: Literal["event"] = "event"
    kind: str
    payload: dict[str, Any] = Field(default_factory=dict)


# --- rest request / response bodies --------------------------------------


class CreateRoomRequest(BaseModel):
    name: str = Field(min_length=1, max_length=32)


class JoinRoomRequest(BaseModel):
    name: str = Field(min_length=1, max_length=32)
    join_code: str | None = None


class PlayerSession(BaseModel):
    """What a client needs to persist in order to act as this player."""

    room_id: str
    join_code: str
    player_id: str
    state: GameState


class FrameAccepted(BaseModel):
    submission_id: str
    skipped: Literal[False] = False


class FrameSkipped(BaseModel):
    skipped: Literal[True] = True
    reason: str
