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


class GameMode(str, Enum):
    """Which rules a room plays by. A GameConfig field, so it survives a restart."""

    # Shared rounds: everyone is asked for the same face at the same time, scored on
    # speed and placement against each other.
    CLASSIC = "classic"
    # One clock, no rounds: every player runs asynchronously through a shared sequence
    # of faces and is paid per face passed. See app/game/engine.py, `_run_blitz`.
    BLITZ = "blitz"


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
    # The round number in classic; the submitting player's own `face_no` in blitz, where
    # there are no rounds and every player is at a different point in the sequence. Either
    # way it is what `apply_result` checks to drop a result whose face has moved on.
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
    # Sum of every round's RoundScore.points: up to 200 per round, rounded to whole points.
    points: int = 0
    # Rounds passed in classic; faces passed in blitz.
    rounds_correct: int = 0
    joined_at: datetime = Field(default_factory=utcnow)
    # The browser's long-lived id, so this game's final score can count toward its high
    # score. Never serialized: every client sees every Player, and it is not theirs to see.
    client_id: str | None = Field(default=None, exclude=True)
    # Server-side only bookkeeping, harmless to expose: drives the rate limiter.
    last_frame_at: datetime | None = None
    # Latest client-reported vitals (pulse, breathing, ...) and when they landed.
    # Deliberately NOT an input to scoring: the numbers are produced in the player's own
    # browser and the server cannot verify them, so letting them pay out points would
    # make the game trivially cheatable. Stored so every client can see them.
    vitals: dict[str, float] | None = None
    vitals_at: datetime | None = None


class RoundScore(BaseModel):
    """How one player's points for a round were made up. Only players who passed get one."""

    # 1 = first to pass. Ordered by when the passing frame was captured, not when its
    # result came back, so a slow model cannot reorder the players.
    place: int
    # Up to 100: share of the round left when the passing frame was captured, times the
    # placement factor (1.0 for first, 0.95 for second, ...).
    speed_points: int
    # Up to 100: the processor's confidence in the passing read.
    accuracy_points: int
    # speed_points + accuracy_points, so at most 200.
    points: int


class Highlight(BaseModel):
    """One of a round's best faces: a passing frame, ranked by the processor's confidence."""

    player_id: str
    # The frame itself, served at /api/media/{submission_id} until the media TTL reaps it.
    submission_id: str
    label: str
    # Copied from the player's RoundScore, so the gallery needs nothing else to rank by.
    accuracy_points: int
    place: int
    # Blitz only: which face this was. A classic highlight sits inside the Round it came
    # from, so the client reads the number off that; a blitz one is loose on BlitzState
    # and has to carry its own.
    face_no: int | None = None


class Round(BaseModel):
    number: int
    prompt: str
    # The label a submission must carry to count as correct.
    target: str
    started_at: datetime
    ends_at: datetime
    # One slot per player: the newest frame wins, until the player passes -- then the slot
    # holds the passing frame and no more are accepted from them this round.
    submissions: dict[str, Submission] = Field(default_factory=dict)
    # player_id -> the frame that first matched the target. Provisional while the round
    # runs (placement is settled from capture times when it ends).
    passed: dict[str, Submission] = Field(default_factory=dict)
    # Filled in when the server ends the round: the breakdown per player who passed, and
    # player_id -> points gained (the same totals, kept flat for the leaderboard).
    scores: dict[str, RoundScore] = Field(default_factory=dict)
    points_awarded: dict[str, int] = Field(default_factory=dict)
    # The round's top faces by accuracy, best first, at most three. Picked when the round
    # ends, alongside `scores`, so they are kept in `history` with the rest of the round.
    highlights: list[Highlight] = Field(default_factory=list)
    # Uncle Damage's line for this round, and the id of its audio in the voice store.
    # Both start None and are patched in once generation finishes: a TTS round trip takes
    # seconds, and the round is never delayed waiting for it. `audio_id` stays None when
    # no TTS key is configured, so the line can still be shown as text.
    voice_line: str | None = None
    audio_id: str | None = None


class BlitzFace(BaseModel):
    """One finished face in one player's run, for the end-of-game breakdown.

    Kept server-side on `store.Room.blitz_done` while the blitz runs and copied onto
    `BlitzRun.faces` once, in `_finish_game`: thirty faces times twelve players is a lot
    of JSON to put in every snapshot when a blitz publishes several times a second.
    """

    index: int
    prompt: str
    target: str
    outcome: Literal["passed", "skipped", "expired"]
    # 0 unless passed. See `engine.score_face`.
    points: int = 0
    # The passing read's confidence; None when the face was skipped or ran out.
    confidence: float | None = None
    # The frame that passed it, served at /api/media/{id} until the media TTL reaps it.
    # None unless passed. Under PROCESSOR=presage the fast path borrows the player's
    # newest upload for this id, so a reading pass has a photo too -- see api/presage.py.
    submission_id: str | None = None
    # How long this player spent on it.
    seconds: float = 0.0


class BlitzRun(BaseModel):
    """One player's cursor into the room's shared sequence: blitz's answer to `Round`.

    Every player has their own, and they diverge -- that asynchrony is the mode. What
    keeps it fair is that `cursor` indexes one sequence shared by the whole room, so a
    given face number asks everyone for the same thing.
    """

    player_id: str
    # 0-based index into the room's sequence, and the 1-based face number shown to the
    # player. `face_no` is what this player's Submissions carry as `round_no`.
    cursor: int = 0
    face_no: int = 1
    prompt: str
    target: str
    face_started_at: datetime
    # Clamped to `game_ends_at`, so no per-face deadline outlives the game clock.
    face_ends_at: datetime
    # Newest frame's read, for the UI. What `round.submissions[player_id]` is in classic.
    submission: Submission | None = None
    passed: int = 0
    skipped: int = 0
    expired: int = 0
    # How the face just before this one ended, so the UI can react to it.
    last_outcome: Literal["passed", "skipped", "expired"] | None = None
    last_points: int = 0
    last_confidence: float | None = None
    # When the face on screen becomes skippable: `face_started_at` plus
    # `blitz_skip_after_seconds`. Reset by every advance, so each face has to be looked
    # at before it can be waved away. The client anchors a countdown to it exactly like
    # every other deadline. None means skippable right now.
    skip_ready_at: datetime | None = None
    # Empty until the game is over; see BlitzFace.
    faces: list[BlitzFace] = Field(default_factory=list)


class BlitzState(BaseModel):
    """The live working set of a blitz, the way `round` is for classic.

    Note what is NOT here: the sequence itself. It lives on `store.Room`, server-side,
    both because it is bulky and because a client holding it could read ahead and
    pre-make the next face -- which would defeat the shared sequence's whole purpose.
    """

    sequence_length: int
    runs: dict[str, BlitzRun] = Field(default_factory=dict)
    # The whole blitz's best faces, filled in once at game over. Blitz has no rounds to
    # hang them off, so they live here; `Round.highlights` is the classic equivalent.
    highlights: list[Highlight] = Field(default_factory=list)


class GameConfig(BaseModel):
    """Echoed to clients so the UI never hardcodes timings."""

    # How long round 1 runs; each later round is `round_decrement_seconds` shorter.
    # Per room: the host sets both in the lobby, and they survive a restart.
    round_seconds: int
    round_decrement_seconds: int = 0
    rounds_per_game: int
    game_seconds: int
    # 100 for speed plus 100 for accuracy. Fixed by the rules, echoed for the UI.
    max_points_per_round: int
    capture_interval_ms: int
    max_players: int

    # --- mode ------------------------------------------------------------
    # Which rules this room plays by. Host-set in the lobby; survives a restart, because
    # `restart_game` deliberately never touches `config`.
    mode: GameMode = GameMode.CLASSIC
    # Blitz only. `game_seconds` is ignored in blitz: `blitz_seconds` is the clock.
    blitz_seconds: int = 150
    blitz_face_seconds: int = 12
    blitz_pass_confidence: float = 0.0
    # A UI preference, not a privacy control: every snapshot carries every Player.points
    # whatever this says, because there is no per-recipient serializer. See game/hub.py.
    blitz_live_leaderboard: bool = True
    # Seconds a face must be on screen before it can be skipped. Echoed so the UI can
    # count down to it; not host-settable.
    blitz_skip_after_seconds: int = 5
    # 100 flat plus up to 100 for accuracy. Fixed by the rules, echoed for the UI.
    max_points_per_face: int = 200

    def round_length(self, round_no: int) -> int:
        """Scheduled seconds for round `round_no` (1-based), before the game timer clamps it."""
        return self.round_seconds - (round_no - 1) * self.round_decrement_seconds


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
    # The live blitz, when `config.mode` is blitz. `round` stays None for the whole game
    # in that mode, and this stays None in classic: exactly one of the two is ever set.
    blitz: BlitzState | None = None
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


# A random id minted by the browser (see frontend/src/session.ts). Optional, so an old
# client still plays; its games just do not count toward a high score.
ClientId = Field(default=None, pattern=r"^[A-Za-z0-9_-]{8,64}$")


class CreateRoomRequest(BaseModel):
    name: str = Field(min_length=1, max_length=32)
    client_id: str | None = ClientId


class JoinRoomRequest(BaseModel):
    name: str = Field(min_length=1, max_length=32)
    join_code: str | None = None
    client_id: str | None = ClientId


class HighScore(BaseModel):
    """One browser's best final score across every game it finished."""

    best: int
    # The name played under when the best was set; names are per game.
    best_name: str
    best_at: datetime
    games_played: int


class HighScoreResponse(BaseModel):
    """`best` is None until this browser has finished a game."""

    best: int | None = None
    best_name: str | None = None
    best_at: datetime | None = None
    games_played: int = 0


class RoundTimingRequest(BaseModel):
    """Host's round timing. The engine checks the schedule as a whole; these are sanity caps."""

    round_seconds: int = Field(ge=1, le=600)
    round_decrement_seconds: int = Field(ge=0, le=600)


class BlitzConfigRequest(BaseModel):
    """Host's blitz settings. Field bounds are sanity caps; the engine checks the pair.

    No skip allowance here on purpose: a free skip on a cooldown is a rule of the mode,
    not a dial, so the cooldown stays an operator setting.
    """

    blitz_seconds: int = Field(ge=30, le=600)
    blitz_face_seconds: int = Field(ge=2, le=60)
    # Capped below 1.0: `judge` reports the top expression's confidence and
    # `presage.STAND_INS` maps `disappointed` onto `sad`, so a near-perfect bar would
    # make some targets unpassable. See app/config.py.
    blitz_pass_confidence: float = Field(ge=0.0, le=0.95)
    blitz_live_leaderboard: bool


class BlitzSkipResponse(BaseModel):
    """What the skipping player gets back: the face they just moved on to."""

    status: Literal["skipped"] = "skipped"
    face_no: int
    prompt: str
    target: str
    # When the face they just landed on becomes skippable in its turn.
    skip_ready_at: datetime


class VitalsReport(BaseModel):
    """One client-reported vitals sample.

    Numbers only, and the route caps how many: this is untrusted input that ends up in
    every snapshot, so it has to stay small and flat.
    """

    player_id: str
    metrics: dict[str, float]


class ExpressionReport(BaseModel):
    """One Presage expression reading, pushed by the SmartSpectra sidecar over loopback."""

    room_id: str
    player_id: str
    # Presage expression name (lowercase ExpressionType) -> confidence, 0 to 100 as the
    # SDK reports it.
    scores: dict[str, float]
    stable: bool = True


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
