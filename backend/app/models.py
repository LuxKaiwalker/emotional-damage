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
    """Whatever your processor decides about one frame. Extend freely via `meta`.

    `label` is the part the game rules read: it is compared against the round's `target`
    to decide whether the player got it right. `score` and `confidence` are the raw read,
    kept for the UI and for debugging -- they do not feed the point total.
    """

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
    # Set when the result lands: did this frame hit the round's target? `None` while pending.
    correct: bool | None = None


class Player(BaseModel):
    id: str
    name: str
    connected: bool = False
    # One point per round the player got right. Integer on purpose: the whole scoring rule
    # is "correct answer -> +1", so there is nothing fractional to represent.
    points: int = 0
    rounds_correct: int = 0
    joined_at: datetime = Field(default_factory=utcnow)
    # Server-side only bookkeeping, harmless to expose: drives the rate limiter.
    last_frame_at: datetime | None = None
    # Latest client-reported vitals (pulse, breathing, ...) and when they landed.
    # Deliberately NOT an input to scoring: the numbers are produced in the player's own
    # browser and the server cannot verify them, so letting them pay out points would
    # make the game trivially cheatable. Stored so every client can see them.
    vitals: dict[str, float] | None = None
    vitals_at: datetime | None = None


class Round(BaseModel):
    number: int
    prompt: str
    # The label a submission must carry to count as correct.
    target: str
    started_at: datetime
    ends_at: datetime
    # One slot per player: the newest frame wins, which is what you want for live capture.
    submissions: dict[str, Submission] = Field(default_factory=dict)
    # Filled in when the server ends the round: player_id -> points gained.
    points_awarded: dict[str, int] = Field(default_factory=dict)
    # Uncle Damage's line for this round, and the id of its audio in the voice store.
    # Both start None and are patched in once generation finishes: a TTS round trip takes
    # seconds, and the round is never delayed waiting for it. `audio_id` stays None when
    # no TTS key is configured, so the line can still be shown as text.
    voice_line: str | None = None
    audio_id: str | None = None


class GameConfig(BaseModel):
    """Echoed to clients so the UI never hardcodes timings."""

    round_seconds: int
    rounds_per_game: int
    game_seconds: int
    points_per_correct: int
    capture_interval_ms: int
    max_players: int


class GameState(BaseModel):
    room_id: str
    join_code: str
    phase: Phase = Phase.LOBBY
    host_id: str
    round: Round | None = None
    # Every round of this game once it has been scored, oldest first. `round` only ever
    # holds the latest, so this is what the end-of-game deep scan reads its prompts from.
    history: list[Round] = Field(default_factory=list)
    players: dict[str, Player] = Field(default_factory=dict)
    config: GameConfig
    # Which game this is in the room's life. Bumped by every restart, so a client can tell
    # "scores reset" from "scores lost".
    game_no: int = 1
    # The game timer. Both are None in the lobby; the client anchors its countdown to
    # `game_ends_at` the same way it anchors the round countdown to `round.ends_at`.
    game_started_at: datetime | None = None
    game_ends_at: datetime | None = None
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


class VitalsReport(BaseModel):
    """One client-reported vitals sample.

    Numbers only, and the route caps how many: this is untrusted input that ends up in
    every snapshot, so it has to stay small and flat.
    """

    player_id: str
    metrics: dict[str, float]


class PlayerSession(BaseModel):
    """What a client needs to persist in order to act as this player."""

    room_id: str
    join_code: str
    player_id: str
    state: GameState


class LeaveRoomResponse(BaseModel):
    status: Literal["left"] = "left"
    # True when that was the last player: the room and its game are gone.
    room_destroyed: bool


class FrameAccepted(BaseModel):
    submission_id: str
    skipped: Literal[False] = False


class FrameSkipped(BaseModel):
    skipped: Literal[True] = True
    reason: str
