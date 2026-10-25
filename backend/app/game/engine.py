"""The authoritative game. Nothing else is allowed to mutate GameState.

Invariants every public method upholds:
  1. Take the room lock.
  2. Mutate state, bump `seq`, refresh `server_time`.
  3. Broadcast the new snapshot (and any transient event) to the room.

Long sleeps happen *outside* the lock, so a running round never blocks frame ingestion.

The rules this file implements:
  * Passing -- a round names a `target` label. The first frame of a player's that the
    processor reads as that label passes them: their slot is frozen on that frame and
    no more are accepted from them this round. Once every connected player has passed,
    the round ends early.
  * Scoring -- only players who passed score, at most 200 a round (see `score_round`):
    up to 100 for speed (share of the round left when the passing frame was captured,
    times 1.0 for first, 0.95 for second, ...) and up to 100 for accuracy (the
    processor's confidence in the passing read). Nothing else scores.
  * Timing -- every round has a deadline, and the game as a whole has one. The game
    timer wins: it truncates the round that would overrun it and ends the game. Round 1
    runs for `config.round_seconds` and each later round is `round_decrement_seconds`
    shorter; the host sets both in the lobby.
  * Rooms -- created with a 4-letter join code, restartable once a game is over, and
    destroyed when the last player goes (immediately on leave, or after a grace period
    for players who just closed the tab).
"""

import asyncio
import logging
import math
from datetime import datetime, timedelta
from typing import Literal, NamedTuple

from app.config import Settings
from app.game.highscores import HighScoreStore
from app.game.hub import ConnectionManager
from app.game.prompts import Prompt, build_sequence, pick_prompt
from app.game.store import CodeExhausted, InMemoryRoomStore, Room, new_id
from app.game.voice import VoiceStudio
from app.models import (
    BlitzFace,
    BlitzRun,
    BlitzState,
    EventMessage,
    GameConfig,
    GameMode,
    GameState,
    Highlight,
    Phase,
    Player,
    ProcessResult,
    Round,
    RoundScore,
    StateMessage,
    Submission,
    SubmissionStatus,
    utcnow,
)

log = logging.getLogger(__name__)

# Below this, the leftover game time is not worth a round of its own.
MIN_ROUND_SECONDS = 1.0
# The game lengths the host can pick in the lobby.
ROUND_CHOICES = (5, 10)
# Headroom on a picked game's timer, so scheduling jitter never costs its last round.
GAME_SLACK_SECONDS = 5

# Scoring. A round is worth at most SPEED_POINTS + ACCURACY_POINTS to one player.
SPEED_POINTS = 100
ACCURACY_POINTS = 100
# Each place after first keeps 5% less of its speed points: 1.0, 0.95, 0.90, ...
PLACEMENT_STEP = 0.05
# How many of a round's faces make its highlight reel.
HIGHLIGHT_COUNT = 3

# The shortest round a host may schedule. Below this a player barely gets a frame scored
# before the round ends, so the last round would be unwinnable.
SHORTEST_PLAYABLE_ROUND_SECONDS = 3

# Blitz: flat points for passing a face, plus ACCURACY_POINTS for the read's confidence,
# so one face is worth 100..200 and the player who makes more faces wins. There is no
# placement term: with everyone on their own cursor, "who was first" compares nothing.
BLITZ_BASE_POINTS = 100


class AcceptedFrame(NamedTuple):
    """A registered submission, plus the round context the frame has to be processed with.

    Handed back whole so the upload path never has to read the round a second time: by
    the time it looked again, the round could already have ended.
    """

    submission: Submission
    prompt: str
    target: str


def _not_in_lobby(phase: Phase, action: str) -> str:
    """Why a lobby-only action was refused, worded for the player who tried it."""
    if phase is Phase.GAME_OVER:
        return f"This game is over. Run it back to {action}."
    return f"The game has already started, so you can't {action} now."


class GameError(Exception):
    """Caller did something the rules do not allow. Mapped to 4xx in the API layer."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class AlreadyPassed(GameError):
    """A frame from a player who has already passed this round. Normal, not an error."""

    def __init__(self) -> None:
        super().__init__("already passed this round", status_code=409)


def score_face(confidence: float) -> int:
    """What one passed blitz face pays. Pure, so the rule can be tested on its own.

    Flat base plus accuracy, and nothing else: volume is meant to be the axis that
    decides a blitz, so a player who makes more faces out-scores a slower, more precise
    one. Deliberately not a function of how fast the face was made -- the global clock
    already pays for speed, by letting a quick player fit more faces into it.
    """
    return BLITZ_BASE_POINTS + round(ACCURACY_POINTS * min(1.0, max(0.0, confidence)))


def score_round(rnd: Round) -> dict[str, RoundScore]:
    """Turn a round's passes into points. Pure, so the rule can be tested on its own.

    Placement and time left both come from when the passing frame was *captured*: a
    player who made the face first should not lose out because their frame took longer
    to come back from the model. Measured against the round's scheduled window, so ending
    early when everyone has passed takes nothing away from anyone.
    """
    window = (rnd.ends_at - rnd.started_at).total_seconds()
    ordered = sorted(rnd.passed.items(), key=lambda item: item[1].received_at)
    scores: dict[str, RoundScore] = {}
    for index, (player_id, submission) in enumerate(ordered):
        left = (rnd.ends_at - submission.received_at).total_seconds()
        share = min(1.0, max(0.0, left / window)) if window > 0 else 0.0
        placement = max(0.0, 1.0 - PLACEMENT_STEP * index)
        confidence = submission.result.confidence if submission.result else 0.0
        speed = round(SPEED_POINTS * share * placement)
        # ProcessResult caps confidence at 1.0, which is what caps accuracy at 100.
        accuracy = round(confidence * ACCURACY_POINTS)
        scores[player_id] = RoundScore(
            place=index + 1,
            speed_points=speed,
            accuracy_points=accuracy,
            points=speed + accuracy,
        )
    return scores


def pick_highlights(rnd: Round, scores: dict[str, RoundScore]) -> list[Highlight]:
    """The round's best faces: most accurate first, an earlier pass breaking a tie.

    Only passing frames qualify -- a miss has no accuracy to rank, and the frame that
    passed a player is the one their score was read from.
    """
    ranked = sorted(scores.items(), key=lambda item: (-item[1].accuracy_points, item[1].place))
    highlights: list[Highlight] = []
    for player_id, score in ranked[:HIGHLIGHT_COUNT]:
        submission = rnd.passed.get(player_id)
        if submission is None:
            continue
        highlights.append(Highlight(
            player_id=player_id,
            submission_id=submission.id,
            label=submission.result.label if submission.result else rnd.target,
            accuracy_points=score.accuracy_points,
            place=score.place,
        ))
    return highlights


class GameEngine:
    def __init__(
        self,
        store: InMemoryRoomStore,
        hub: ConnectionManager,
        settings: Settings,
        voice: VoiceStudio | None = None,
        highscores: HighScoreStore | None = None,
    ) -> None:
        self.store = store
        # Optional: without it, finished games simply are not recorded.
        self.highscores = highscores
        self.hub = hub
        self.settings = settings
        # Optional: without it (or without API keys) rounds simply carry no narration.
        self.voice = voice
        # Narration runs outside the round driver, so it is tracked here and cancelled
        # on shutdown rather than being left to outlive the app.
        self._voice_tasks: set[asyncio.Task] = set()

    # --- lookup ----------------------------------------------------------

    def require_room(self, room_id: str) -> Room:
        room = self.store.get(room_id)
        if room is None:
            raise GameError(
                "That lobby doesn't exist anymore. Check the code, or start a new one.", 404
            )
        return room

    def resolve(self, room_id_or_code: str) -> Room:
        """Accept either a room id or a short join code, so the UI can take either."""
        return (
            self.store.get(room_id_or_code)
            or self.store.get_by_code(room_id_or_code)
            or self.require_room(room_id_or_code)
        )

    # --- rooms -----------------------------------------------------------

    async def create_room(
        self, host_name: str, client_id: str | None = None
    ) -> tuple[Room, str]:
        host = Player(id=new_id("p"), name=host_name, client_id=client_id)
        try:
            join_code = self.store.allocate_join_code(self.settings.join_code_length)
        except CodeExhausted as exc:
            raise GameError("Every lobby code is taken right now. Try again in a minute.", 503) from exc

        state = GameState(
            room_id=new_id("r"),
            join_code=join_code,
            host_id=host.id,
            players={host.id: host},
            config=GameConfig(
                round_seconds=self.settings.round_seconds,
                round_decrement_seconds=self.settings.round_decrement_seconds,
                rounds_per_game=self.settings.rounds_per_game,
                game_seconds=self.settings.game_seconds,
                max_points_per_round=SPEED_POINTS + ACCURACY_POINTS,
                capture_interval_ms=self.settings.capture_interval_ms,
                max_players=self.settings.max_players_per_room,
                mode=GameMode(self.settings.game_mode),
                blitz_seconds=self.settings.blitz_seconds,
                blitz_face_seconds=self.settings.blitz_face_seconds,
                blitz_pass_confidence=self.settings.blitz_pass_confidence,
                blitz_live_leaderboard=self.settings.blitz_live_leaderboard,
                blitz_skip_after_seconds=self.settings.blitz_skip_after_seconds,
                max_points_per_face=BLITZ_BASE_POINTS + ACCURACY_POINTS,
            ),
        )
        room = self.store.create(state)
        # Nobody has opened a socket yet, so the clock on an abandoned room starts here:
        # a room created by a client that then vanishes is reaped like any other.
        room.empty_since = utcnow()
        return room, host.id

    async def join(self, room_id: str, name: str, client_id: str | None = None) -> str:
        """Join at any phase. Mid-game joiners play from the next round at zero points."""
        room = self.resolve(room_id)
        async with room.lock:
            if len(room.state.players) >= self.settings.max_players_per_room:
                raise GameError("This lobby is full. Ask the host to make room, or start your own.", 409)
            player = Player(id=new_id("p"), name=name, client_id=client_id)
            room.state.players[player.id] = player
            await self._publish(room, EventMessage(kind="player_joined", payload={
                "player_id": player.id, "name": player.name,
            }))
        return player.id

    async def leave(self, room_id: str, player_id: str) -> bool:
        """Remove a player for good. Returns True if that emptied and destroyed the room.

        This is the explicit exit. A player who merely drops their socket keeps their seat
        until the reaper decides the whole room is abandoned (see `reap_empty_rooms`).
        """
        room = self.require_room(room_id)
        async with room.lock:
            state = room.state
            player = state.players.pop(player_id, None)
            if player is None:
                raise GameError("You're not in this lobby anymore. Rejoin with the code.", 404)
            if state.round is not None:
                state.round.submissions.pop(player_id, None)
                state.round.passed.pop(player_id, None)
            if state.blitz is not None:
                state.blitz.runs.pop(player_id, None)
            room.blitz_done.pop(player_id, None)

            if not state.players:
                await self._destroy(room, reason="empty")
                return True

            if state.host_id == player_id:
                state.host_id = self._next_host(state)
            if not any(p.connected for p in state.players.values()):
                room.empty_since = room.empty_since or utcnow()
            # The last holdout leaving can be what completes the round.
            self._end_round_if_all_passed(room)

            await self._publish(room, EventMessage(kind="player_left", payload={
                "player_id": player_id, "name": player.name, "host_id": state.host_id,
            }))
            return False

    @staticmethod
    def _next_host(state: GameState) -> str:
        """Longest-tenured player, preferring one who is actually connected."""
        return min(
            state.players.values(), key=lambda p: (not p.connected, p.joined_at)
        ).id

    async def destroy_room(self, room_id: str, reason: str) -> None:
        room = self.store.get(room_id)
        if room is None:
            return
        async with room.lock:
            await self._destroy(room, reason)

    async def _destroy(self, room: Room, reason: str) -> None:
        """Tear down a room. Caller holds the room lock."""
        room_id = room.state.room_id
        if room.task is not None and not room.task.done():
            room.task.cancel()
        self.store.delete(room_id)
        log.info("destroyed room %s (%s)", room_id, reason)
        await self.hub.broadcast(
            room_id, EventMessage(kind="room_closed", payload={"reason": reason})
        )
        await self.hub.close_room(room_id, code=4000, reason=f"room closed: {reason}")

    async def reap_empty_rooms(self) -> int:
        """Destroy rooms that have had nobody connected for longer than the grace period."""
        cutoff = utcnow() - timedelta(seconds=self.settings.empty_room_grace_seconds)
        destroyed = 0
        for room in self.store.all():
            async with room.lock:
                if any(p.connected for p in room.state.players.values()):
                    room.empty_since = None
                    continue
                if room.empty_since is None:
                    room.empty_since = utcnow()
                    continue
                if room.empty_since <= cutoff:
                    await self._destroy(room, reason="abandoned")
                    destroyed += 1
        return destroyed

    async def reap_empty_rooms_forever(self) -> None:
        interval = max(1, self.settings.room_reap_interval_seconds)
        while True:
            try:
                await asyncio.sleep(interval)
                await self.reap_empty_rooms()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("room reaper iteration failed")

    # --- players ---------------------------------------------------------

    async def set_connected(self, room_id: str, player_id: str, connected: bool) -> None:
        """Socket up / socket down. Tolerates a room that has already been destroyed."""
        room = self.store.get(room_id)
        if room is None:
            return
        async with room.lock:
            player = room.state.players.get(player_id)
            if player is None or player.connected == connected:
                return
            player.connected = connected
            if connected:
                room.empty_since = None
            elif not any(p.connected for p in room.state.players.values()):
                room.empty_since = utcnow()
            else:
                # Nobody waits on a player who dropped out before passing.
                self._end_round_if_all_passed(room)
            await self._publish(room)

    # --- game lifecycle --------------------------------------------------

    async def start_game(self, room_id: str, player_id: str) -> None:
        """Host starts a game from the lobby and the game timer begins ticking."""
        room = self.require_room(room_id)
        async with room.lock:
            state = room.state
            if player_id != state.host_id:
                raise GameError("Only the host can start the game.", status_code=403)
            if state.phase is not Phase.LOBBY:
                raise GameError(_not_in_lobby(state.phase, "start a new game"), 409)
            if room.task is not None and not room.task.done():
                raise GameError("The game is already running.", status_code=409)

            now = utcnow()
            config = state.config
            blitz = config.mode is GameMode.BLITZ
            # In blitz the mode's own clock *is* the game clock; `game_seconds` is sized
            # for a round schedule and means nothing here.
            seconds = config.blitz_seconds if blitz else config.game_seconds
            state.game_started_at = now
            state.game_ends_at = now + timedelta(seconds=seconds)
            await self._publish(room, EventMessage(kind="game_started", payload={
                "game_no": state.game_no,
                "mode": config.mode.value,
                "ends_at": state.game_ends_at.isoformat(),
            }))

        runner = self._run_blitz if blitz else self._run_game
        room.task = asyncio.create_task(runner(room), name=f"game:{room_id}")

    async def set_rounds(self, room_id: str, player_id: str, rounds: int) -> None:
        """Host picks the game length in the lobby. It sticks across restarts.

        The game timer grows to fit: a hard cap shorter than the rounds asked for would
        quietly end the game early, and the deep scan would list fewer rounds than promised.
        """
        room = self.require_room(room_id)
        async with room.lock:
            state = room.state
            if player_id != state.host_id:
                raise GameError("Only the host can change the number of rounds.", status_code=403)
            if state.phase is not Phase.LOBBY:
                raise GameError(_not_in_lobby(state.phase, "change the rounds"), 409)
            if rounds not in ROUND_CHOICES:
                choices = " or ".join(map(str, ROUND_CHOICES))
                raise GameError(f"Pick {choices} rounds.", status_code=422)

            # Sized from the room's own timing, so a host's longer or shrinking rounds
            # are what the timer fits -- and ten shrinking rounds can be refused.
            state.config = self._fit_schedule(
                state.config.model_copy(update={"rounds_per_game": rounds})
            )
            await self._publish(room, EventMessage(kind="config_changed", payload={
                "rounds_per_game": rounds,
                "game_seconds": state.config.game_seconds,
            }))

    async def restart_game(self, room_id: str, player_id: str) -> None:
        """Back to the lobby with a clean slate, so the same room can play again.

        Deliberately does not start the next game: returning to the lobby is what lets
        new players join between games, and the host then starts as usual.
        """
        room = self.require_room(room_id)
        async with room.lock:
            state = room.state
            if player_id != state.host_id:
                raise GameError("Only the host can run it back.", status_code=403)
            if state.phase is not Phase.GAME_OVER:
                raise GameError(
                    "You can only run it back once the game is over.", 409
                )
            if room.task is not None and not room.task.done():
                raise GameError("The game is still wrapping up. Try again in a second.", 409)

            for player in state.players.values():
                player.points = 0
                player.rounds_correct = 0
                player.last_frame_at = None
            state.round = None
            state.history = []
            state.blitz = None
            room.blitz_sequence.clear()
            room.blitz_done.clear()
            room.inflight.clear()
            state.phase = Phase.LOBBY
            state.game_no += 1
            state.game_started_at = None
            state.game_ends_at = None
            room.task = None

            await self._publish(room, EventMessage(kind="game_restarted", payload={
                "game_no": state.game_no,
            }))

    async def set_round_timing(
        self, room_id: str, player_id: str, round_seconds: int, round_decrement_seconds: int
    ) -> GameConfig:
        """Host sets round 1's length and how much shorter each later round gets.

        Lobby only, so a running game never changes pace under the players. See
        `_fit_schedule` for what is refused and how the game timer follows.
        """
        room = self.require_room(room_id)
        async with room.lock:
            state = room.state
            if player_id != state.host_id:
                raise GameError("Only the host can change the round timing.", status_code=403)
            if state.phase is not Phase.LOBBY:
                raise GameError(_not_in_lobby(state.phase, "change the round timing"), 409)

            state.config = self._fit_schedule(state.config.model_copy(update={
                "round_seconds": round_seconds,
                "round_decrement_seconds": round_decrement_seconds,
            }))
            await self._publish(room, EventMessage(kind="config_changed", payload={
                "round_seconds": round_seconds,
                "round_decrement_seconds": round_decrement_seconds,
                "game_seconds": state.config.game_seconds,
            }))
            return state.config

    # --- blitz actions ---------------------------------------------------

    async def skip_face(self, room_id: str, player_id: str) -> BlitzRun:
        """Move this player past a face they cannot land. Costs no points.

        Free, but not instant: a face has to have been on screen for
        `blitz_skip_after_seconds` first (`run.skip_ready_at`). That is what stops a face
        which simply will not register from eating a player's clock, while also stopping
        skip-hammering from being a faster way through the sequence than playing it.
        The wait is per face, so it resets every time a new one comes up.
        """
        room = self.require_room(room_id)
        async with room.lock:
            state = room.state
            if player_id not in state.players:
                raise GameError("You're not in this lobby anymore. Rejoin with the code.", 404)
            if state.config.mode is not GameMode.BLITZ:
                raise GameError("Skipping is a blitz thing. This game plays in rounds.", 409)
            if state.phase is not Phase.ROUND or state.blitz is None:
                raise GameError("There's no face to skip right now.", 409)
            run = self._active_run(room, player_id)
            if run is None:
                raise GameError("The blitz is over.", 409)

            now = utcnow()
            if run.skip_ready_at is not None and now < run.skip_ready_at:
                wait = max(1, math.ceil((run.skip_ready_at - now).total_seconds()))
                raise GameError(f"Skip again in {wait}s.", status_code=429)

            skipped = run.face_no
            # `_advance` arms the next face's own unlock; there is no separate cooldown.
            self._advance(room, run, now, "skipped")
            await self._publish(room, EventMessage(kind="blitz_face_skipped", payload={
                "player_id": player_id, "face_no": skipped,
            }))
            return run

    async def set_mode(self, room_id: str, player_id: str, mode: GameMode) -> GameConfig:
        """Host picks the rules in the lobby. Sticks across restarts, like every setting.

        Both modes' settings stay independently settable whatever the mode is, so a host
        can switch back and forth without reconfiguring; the lobby just shows the rows
        belonging to whichever is selected.
        """
        room = self.require_room(room_id)
        async with room.lock:
            state = room.state
            if player_id != state.host_id:
                raise GameError("Only the host can change the mode.", status_code=403)
            if state.phase is not Phase.LOBBY:
                raise GameError(_not_in_lobby(state.phase, "change the mode"), 409)

            state.config = state.config.model_copy(update={"mode": mode})
            await self._publish(room, EventMessage(kind="config_changed", payload={
                "mode": mode.value,
            }))
            return state.config

    async def set_blitz_config(
        self,
        room_id: str,
        player_id: str,
        *,
        blitz_seconds: int,
        blitz_face_seconds: int,
        blitz_pass_confidence: float,
        blitz_live_leaderboard: bool,
    ) -> GameConfig:
        """Host's blitz settings. Lobby only, so a running blitz never changes under it.

        Deliberately does not go through `_fit_schedule`: that exists to size a game timer
        to a *round schedule* and to refuse a last round too short to play, and a blitz has
        neither. Its clock is `blitz_seconds` directly, so the only thing left to check is
        the one pair pydantic cannot.
        """
        room = self.require_room(room_id)
        async with room.lock:
            state = room.state
            if player_id != state.host_id:
                raise GameError("Only the host can change the blitz settings.", 403)
            if state.phase is not Phase.LOBBY:
                raise GameError(_not_in_lobby(state.phase, "change the blitz settings"), 409)
            if blitz_face_seconds > blitz_seconds:
                raise GameError(
                    f"A {blitz_face_seconds}s limit per face does not fit in a"
                    f" {blitz_seconds}s blitz. Lower the limit or lengthen the blitz.",
                    status_code=422,
                )

            state.config = state.config.model_copy(update={
                "blitz_seconds": blitz_seconds,
                "blitz_face_seconds": blitz_face_seconds,
                "blitz_pass_confidence": blitz_pass_confidence,
                "blitz_live_leaderboard": blitz_live_leaderboard,
            })
            await self._publish(room, EventMessage(kind="config_changed", payload={
                "blitz_seconds": blitz_seconds,
                "blitz_face_seconds": blitz_face_seconds,
                "blitz_pass_confidence": blitz_pass_confidence,
                "blitz_live_leaderboard": blitz_live_leaderboard,
            }))
            return state.config

    def _fit_schedule(self, config: GameConfig) -> GameConfig:
        """Check a host's schedule whole, and size the game timer to it.

        A last round too short to play is refused rather than clamped: one that silently
        became 1s is worse than a clear "no". The game timer grows to fit instead, because
        a cap shorter than the rounds asked for would quietly end the game early, and the
        deep scan would list fewer rounds than promised. It never drops below
        GAME_SECONDS, so that stays the floor an operator sets.
        """
        rounds = config.rounds_per_game
        last = config.round_length(rounds)
        # An operator who configured shorter rounds than that meant it; hosts cannot go below.
        floor = min(SHORTEST_PLAYABLE_ROUND_SECONDS, self.settings.round_seconds)
        if last < floor:
            raise GameError(
                f"That timing leaves round {rounds} only {max(last, 0)}s. Every round needs at"
                f" least {floor}s: make round 1 longer or the drop per round smaller.",
                status_code=422,
            )
        needed = (
            sum(config.round_length(n) for n in range(1, rounds + 1))
            + (rounds - 1) * self.settings.intermission_seconds
            + GAME_SLACK_SECONDS
        )
        return config.model_copy(
            update={"game_seconds": max(self.settings.game_seconds, needed)}
        )

    # --- vitals ----------------------------------------------------------

    async def record_vitals(
        self, room_id: str, player_id: str, metrics: dict[str, float]
    ) -> None:
        """Store one client-reported vitals sample and broadcast it.

        This is intentionally a dead end as far as the rules are concerned. Nothing in
        `_end_round`, `_is_correct` or `apply_result` reads `player.vitals`, and nothing
        should: the numbers are computed in the player's own browser from their own
        camera, so the server cannot verify them and treating them as scoring input would
        make points trivially forgeable. They exist so every client can *see* the read.
        """
        room = self.require_room(room_id)
        async with room.lock:
            player = room.state.players.get(player_id)
            if player is None:
                raise GameError("You're not in this lobby anymore. Rejoin with the code.", 404)
            player.vitals = metrics
            player.vitals_at = utcnow()
            await self._publish(room)

    # --- frames ----------------------------------------------------------

    async def submit_frame(self, room_id: str, player_id: str, size: int) -> AcceptedFrame:
        """Register a pending submission. The frame itself is processed off-thread."""
        room = self.require_room(room_id)
        async with room.lock:
            state = room.state
            player = state.players.get(player_id)
            if player is None:
                raise GameError("You're not in this lobby anymore. Rejoin with the code.", 404)
            if state.phase is not Phase.ROUND:
                raise GameError("No round is running, so there's no face to send yet.", 409)

            if state.config.mode is GameMode.BLITZ:
                return await self._submit_blitz_frame(room, player)

            if state.round is None:
                raise GameError("No round is running, so there's no face to send yet.", 409)
            if player_id in state.round.passed:
                raise AlreadyPassed()

            now = utcnow()
            min_gap = timedelta(milliseconds=self.settings.min_frame_interval_ms)
            if player.last_frame_at is not None and now - player.last_frame_at < min_gap:
                raise GameError("rate_limited", status_code=429)
            player.last_frame_at = now

            submission = Submission(
                id=new_id("s"),
                player_id=player_id,
                round_no=state.round.number,
                received_at=now,
            )
            # Newest frame per player takes the slot the UI shows. The one it replaces is
            # still tracked in `inflight`: if that one turns out to be the correct face,
            # it passes the player all the same.
            state.round.submissions[player_id] = submission
            room.inflight[submission.id] = submission
            await self._publish(room)
            return AcceptedFrame(submission, state.round.prompt, state.round.target)

    async def _submit_blitz_frame(self, room: Room, player: Player) -> AcceptedFrame:
        """Register a frame against whichever face this player is on. Lock held.

        Note what is missing: `AlreadyPassed`. Passing a face advances you to the next one,
        so in blitz there is never a state where a player's frames stop being wanted --
        which is also why the client's uploader does not need an `iPassed` gate here.
        """
        run = self._active_run(room, player.id)
        if run is None:
            raise GameError("The blitz is over.", 409)

        now = utcnow()
        min_gap = timedelta(milliseconds=self.settings.min_frame_interval_ms)
        if player.last_frame_at is not None and now - player.last_frame_at < min_gap:
            raise GameError("rate_limited", status_code=429)
        player.last_frame_at = now

        submission = Submission(
            id=new_id("s"),
            player_id=player.id,
            # The player's own face number, not a round. `apply_result` compares it back
            # against the run, so a result for a face they have left is dropped.
            round_no=run.face_no,
            received_at=now,
        )
        run.submission = submission
        room.inflight[submission.id] = submission
        await self._publish(room)
        return AcceptedFrame(submission, run.prompt, run.target)

    async def apply_result(
        self,
        room_id: str,
        submission_id: str,
        result: ProcessResult | None,
        error: str | None = None,
    ) -> None:
        """Called by the frame workers. The only path from processing back into state."""
        room = self.store.get(room_id)
        if room is None:
            return

        async with room.lock:
            state = room.state
            submission = room.inflight.pop(submission_id, None)
            if submission is None:
                return

            if state.config.mode is GameMode.BLITZ:
                await self._apply_blitz_result(room, submission, result, error)
                return

            if state.round is None or submission.round_no != state.round.number:
                # From a round that has already moved on. Drop it.
                return

            if error is not None:
                submission.status = SubmissionStatus.FAILED
                submission.error = error
                submission.correct = None
            else:
                submission.status = SubmissionStatus.DONE
                submission.result = result
                # Judged now so the UI can show a hit immediately; the point itself is
                # only committed when the server ends the round. A result that arrives
                # after the round was committed is recorded but deliberately left
                # unjudged (`correct is None`): claiming a hit the player can no longer
                # be paid for is worse than showing the raw read on its own.
                submission.correct = (
                    self._is_correct(result, state.round.target)
                    if state.phase is Phase.ROUND
                    else None
                )

            player_id = submission.player_id
            passed_now = (
                submission.correct is True
                and player_id in state.players
                and player_id not in state.round.passed
            )
            if passed_now:
                state.round.passed[player_id] = submission
                # Freeze the slot on the passing frame, even if a newer one had taken it.
                state.round.submissions[player_id] = submission
                self._end_round_if_all_passed(room)
            elif state.round.submissions.get(player_id) is not submission:
                # Superseded and not a pass: nothing the player or the rules care about.
                return

            await self._publish(room, EventMessage(kind="submission_scored", payload={
                "player_id": player_id,
                "submission_id": submission.id,
                "status": submission.status.value,
                "correct": submission.correct,
                "passed": passed_now,
                "result": result.model_dump(mode="json") if result else None,
            }))

    async def _apply_blitz_result(
        self,
        room: Room,
        submission: Submission,
        result: ProcessResult | None,
        error: str | None,
    ) -> None:
        """Judge one frame against the face its player was on, and pay for it now.

        Points are committed here rather than at a boundary, because blitz has no
        boundary and its leaderboard is live. That is safe in a way classic's deferral is
        not meant to be: a passed face is final, and nothing later can take it back.
        """
        state = room.state
        blitz = state.blitz
        run = blitz.runs.get(submission.player_id) if blitz is not None else None
        if run is None or submission.round_no != run.face_no:
            # A face this player has already left -- passed, skipped or run out. Same rule
            # as classic's round check: record nothing, claim nothing.
            return

        if error is not None:
            submission.status = SubmissionStatus.FAILED
            submission.error = error
            submission.correct = None
        else:
            submission.status = SubmissionStatus.DONE
            submission.result = result
            submission.correct = (
                self._is_correct(result, run.target, self.pass_threshold(room))
                if state.phase is Phase.ROUND
                else None
            )

        player = state.players.get(submission.player_id)
        if submission.correct is True and player is not None and result is not None:
            points = score_face(result.confidence)
            player.points += points
            player.rounds_correct += 1
            face_no = run.face_no
            self._advance(room, run, utcnow(), "passed", points, result.confidence)
            event = EventMessage(kind="blitz_face_passed", payload={
                "player_id": player.id,
                "face_no": face_no,
                "points": points,
                "confidence": result.confidence,
                "total": player.points,
            })
        else:
            # Newest read, for the UI -- the same thing `round.submissions[pid]` shows.
            run.submission = submission
            event = EventMessage(kind="submission_scored", payload={
                "player_id": submission.player_id,
                "submission_id": submission.id,
                "status": submission.status.value,
                "correct": submission.correct,
                "passed": False,
                "result": result.model_dump(mode="json") if result else None,
            })
        await self._publish(room, event)

    @staticmethod
    def _is_correct(
        result: ProcessResult | None, target: str, min_confidence: float = 0.0
    ) -> bool:
        """The whole passing rule: the processor's label has to be the one asked for.

        `min_confidence` is blitz's pass threshold. It defaults to 0.0, so classic callers
        that pass nothing get exactly the behaviour they always had.
        """
        return (
            result is not None
            and result.label == target
            and result.confidence >= min_confidence
        )

    @staticmethod
    def _end_round_if_all_passed(room: Room) -> None:
        """Wake the round driver early once every connected player has passed.

        Caller holds the room lock. Only connected players count, so a closed tab does not
        hold the round open; with nobody connected the round simply runs out its clock.

        Blitz needs no check of its own here: it leaves `state.round` None for the whole
        game, so the guard below already makes every call a no-op. There is nothing to end
        early in a blitz anyway -- its clock is the only thing that finishes it.
        """
        state = room.state
        if state.phase is not Phase.ROUND or state.round is None:
            return
        connected = [p.id for p in state.players.values() if p.connected]
        if connected and all(pid in state.round.passed for pid in connected):
            room.round_done.set()

    # --- blitz runs ------------------------------------------------------
    #
    # A blitz has no rounds: each player holds a `BlitzRun` cursor into one sequence the
    # whole room shares, and they advance independently. Every deadline in here is a
    # stored timestamp evaluated lazily -- `_active_run` is the choke point every inbound
    # path goes through -- plus one sweep from the driver, so a blitz still costs exactly
    # one asyncio task per room. A task per player would not scale and is not needed.
    #
    # Every method below assumes the caller holds the room lock.

    def pass_threshold(self, room: Room) -> float:
        """The confidence a read needs to pass. Zero outside blitz, i.e. label-only."""
        config = room.state.config
        return config.blitz_pass_confidence if config.mode is GameMode.BLITZ else 0.0

    def _entry(self, room: Room, cursor: int) -> Prompt:
        """The sequence entry at `cursor`.

        Wraps modulo the length. The sequence is built long enough that nobody should
        reach the end, and wrapping is one line of insurance rather than a rule anyone has
        to reason about -- it wraps identically for every player, so the shared-order
        guarantee survives it.
        """
        sequence = room.blitz_sequence
        return sequence[cursor % len(sequence)]

    def _face_deadline(self, room: Room, started_at: datetime) -> datetime:
        """When the face started at `started_at` runs out, never past the game clock.

        The same clamp `_begin_round` applies to a round: it keeps "no per-player deadline
        outlives the game" exactly true, so the UI can never count down past the end.
        """
        ends_at = started_at + timedelta(seconds=room.state.config.blitz_face_seconds)
        if room.state.game_ends_at is not None:
            ends_at = min(ends_at, room.state.game_ends_at)
        return ends_at

    def _skip_unlock(self, room: Room, started_at: datetime) -> datetime:
        """When the face that opened at `started_at` becomes skippable.

        Per face, not per skip: a player has to look at a face for
        `blitz_skip_after_seconds` before they can wave it away, so hammering skip can
        never be a faster way through the sequence than actually playing it.

        A host can set `blitz_face_seconds` below this, in which case a face expires
        before its skip ever unlocks. That is harmless and left alone -- a face that
        short rolls over on its own anyway, so there is nothing to escape from.
        """
        return started_at + timedelta(seconds=room.state.config.blitz_skip_after_seconds)

    def _new_run(self, room: Room, player_id: str, now: datetime) -> BlitzRun:
        entry = self._entry(room, 0)
        return BlitzRun(
            player_id=player_id,
            cursor=0,
            face_no=1,
            prompt=entry.text,
            target=entry.target,
            face_started_at=now,
            face_ends_at=self._face_deadline(room, now),
            skip_ready_at=self._skip_unlock(room, now),
        )

    def _advance(
        self,
        room: Room,
        run: BlitzRun,
        now: datetime,
        outcome: Literal["passed", "skipped", "expired"],
        points: int = 0,
        confidence: float | None = None,
    ) -> None:
        """Close this player's face and open their next one.

        Re-arms `skip_ready_at` from the new face's start, so every face -- however the
        one before it ended -- has to be on screen for `blitz_skip_after_seconds` before
        it can be skipped.
        """
        room.blitz_done.setdefault(run.player_id, []).append(BlitzFace(
            index=run.cursor,
            prompt=run.prompt,
            target=run.target,
            outcome=outcome,
            points=points,
            confidence=confidence,
            seconds=max(0.0, (now - run.face_started_at).total_seconds()),
        ))
        if outcome == "passed":
            run.passed += 1
        elif outcome == "skipped":
            run.skipped += 1
        else:
            run.expired += 1

        run.cursor += 1
        run.face_no = run.cursor + 1
        entry = self._entry(room, run.cursor)
        run.prompt = entry.text
        run.target = entry.target
        run.face_started_at = now
        run.face_ends_at = self._face_deadline(room, now)
        run.skip_ready_at = self._skip_unlock(room, now)
        # The new face has had no frames yet; a stale read here would show the UI a
        # confidence belonging to the face the player just finished.
        run.submission = None
        run.last_outcome = outcome
        run.last_points = points
        run.last_confidence = confidence

    def _ensure_runs(self, room: Room, now: datetime) -> bool:
        """Open a run for anyone who does not have one yet. Covers mid-blitz joiners."""
        blitz = room.state.blitz
        if blitz is None:
            return False
        changed = False
        for player_id in room.state.players:
            if player_id not in blitz.runs:
                blitz.runs[player_id] = self._new_run(room, player_id, now)
                changed = True
        return changed

    def _expire_faces(self, room: Room, now: datetime) -> bool:
        """Roll over every face whose time ran out. Returns whether anything moved.

        Does nothing once the game clock is spent, and that guard is load-bearing:
        `_face_deadline` clamps every face to `game_ends_at`, so past that instant each
        replacement face is born already expired and the loop below would never
        terminate. The driver is about to end the game anyway, so there is nothing to do.
        """
        blitz = room.state.blitz
        if blitz is None:
            return False
        ends_at = room.state.game_ends_at
        if ends_at is not None and now >= ends_at:
            return False
        changed = False
        for run in blitz.runs.values():
            # A loop, not an `if`: a player whose tab was asleep can be several faces
            # behind, and leaving them on a long-dead face would freeze their UI.
            while run.face_ends_at <= now:
                self._advance(room, run, run.face_ends_at, "expired")
                changed = True
        return changed

    def _active_run(self, room: Room, player_id: str) -> BlitzRun | None:
        """This player's run, brought up to date first. The lazy-evaluation choke point."""
        if room.state.blitz is None or room.state.phase is not Phase.ROUND:
            return None
        now = utcnow()
        self._ensure_runs(room, now)
        self._expire_faces(room, now)
        return room.state.blitz.runs.get(player_id)

    def current_face(self, room: Room, player_id: str) -> tuple[str, str] | None:
        """The (prompt, target) this player is being asked for right now, either mode.

        None when there is nothing for them to do: no round, already passed it in classic,
        or no live run in blitz. The one helper the Presage fast path reads, so that path
        does not have to know which mode it is in.
        """
        state = room.state
        if state.phase is not Phase.ROUND:
            return None
        if state.config.mode is GameMode.BLITZ:
            run = self._active_run(room, player_id)
            return (run.prompt, run.target) if run is not None else None
        if state.round is None or player_id in state.round.passed:
            return None
        return (state.round.prompt, state.round.target)

    # --- round driver ----------------------------------------------------

    async def _run_game(self, room: Room) -> None:
        """One task per active room: owns every phase transition and its timing."""
        try:
            reason = "rounds_complete"
            rounds = room.state.config.rounds_per_game
            for round_no in range(1, rounds + 1):
                budget = self._round_budget(room, round_no)
                if budget is None:
                    reason = "time_up"
                    break

                # The round reports back how long it actually got: `budget` was measured
                # a moment earlier, and the round's deadline is clamped to the game's.
                # It ends at that deadline, or sooner once everyone has passed.
                duration = await self._begin_round(room, round_no, budget)
                try:
                    await asyncio.wait_for(room.round_done.wait(), timeout=duration)
                except TimeoutError:
                    pass
                await self._end_round(room)

                if round_no < rounds:
                    remaining = self._seconds_left(room)
                    if remaining <= MIN_ROUND_SECONDS:
                        reason = "time_up"
                        break
                    await asyncio.sleep(
                        min(self.settings.intermission_seconds, remaining)
                    )
            await self._finish_game(room, reason)
        except asyncio.CancelledError:
            log.info("game task cancelled for room %s", room.state.room_id)
            raise
        except Exception:
            log.exception("game task crashed for room %s", room.state.room_id)
            await self._finish_game(room, "crashed")

    async def _run_blitz(self, room: Room) -> None:
        """One task per active room, same as `_run_game`, for a game with no rounds.

        All it owns is the global clock and the per-face expiry sweep: there is nothing to
        begin or end per round, no intermission, and no early finish -- a blitz is over
        when its clock is, whatever anyone has done.

        Kept separate from `_run_game` rather than branching inside it, because the two
        share only `_seconds_left` and `_finish_game`; everything that makes `_run_game`
        what it is (the round loop, budgets, `round_done`, intermissions) has no meaning
        here, so a branch would have been dispatch with extra steps.
        """
        try:
            await self._begin_blitz(room)
            tick = max(0.05, self.settings.blitz_tick_ms / 1000)
            while True:
                left = self._seconds_left(room)
                if left <= 0:
                    break
                # Outside the lock, like every other wait in the drivers.
                await asyncio.sleep(min(tick, left))
                await self._sweep_blitz(room)
            await self._finish_game(room, "time_up")
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("blitz task crashed for room %s", room.state.room_id)
            await self._finish_game(room, "crashed")

    async def _begin_blitz(self, room: Room) -> None:
        """Materialize the shared sequence and open everyone's first face at once."""
        async with room.lock:
            state = room.state
            config = state.config
            # One face a second is the practical ceiling (min_frame_interval_ms gates
            # uploads at four a second and nobody changes face that fast), so this is
            # generous. `_entry` wraps anyway, so running out is not a failure mode.
            length = max(self.settings.blitz_sequence_min_length, config.blitz_seconds + 16)
            room.blitz_sequence = build_sequence(length)
            room.blitz_done.clear()
            room.inflight.clear()
            now = utcnow()
            state.phase = Phase.ROUND
            # Blitz has no rounds, and exactly one of `round` / `blitz` is ever set.
            state.round = None
            state.blitz = BlitzState(sequence_length=len(room.blitz_sequence))
            self._ensure_runs(room, now)
            await self._publish(room, EventMessage(kind="blitz_started", payload={
                "ends_at": state.game_ends_at.isoformat() if state.game_ends_at else None,
                "sequence_length": state.blitz.sequence_length,
                "face_seconds": config.blitz_face_seconds,
            }))
            # No narration: Uncle Damage speaks per round, and a blitz would mean a Gemini
            # line plus a TTS round trip per face per player, several times a second,
            # against prompts that differ per player. See deploy/README.md on the box's size.

    async def _sweep_blitz(self, room: Room) -> None:
        """Roll over lapsed faces, and pick up anyone who joined mid-blitz."""
        async with room.lock:
            if room.state.phase is not Phase.ROUND or room.state.blitz is None:
                return
            now = utcnow()
            changed = self._ensure_runs(room, now)
            # Bitwise, not `or`: both have to run, and `or` would short-circuit the sweep.
            changed |= self._expire_faces(room, now)
            if changed:
                await self._publish(room)

    def _seconds_left(self, room: Room) -> float:
        """Game time remaining. Read without the lock: one field, no await in between."""
        ends_at = room.state.game_ends_at
        if ends_at is None:
            return 0.0
        return (ends_at - utcnow()).total_seconds()

    def _round_budget(self, room: Room, round_no: int) -> float | None:
        """How long round `round_no` may run, or None when the game timer has no room left."""
        remaining = self._seconds_left(room)
        if remaining < MIN_ROUND_SECONDS:
            return None
        # The floor only matters for server defaults; host input is validated up front.
        scheduled = max(float(room.state.config.round_length(round_no)), MIN_ROUND_SECONDS)
        return min(scheduled, remaining)

    async def _begin_round(self, room: Room, round_no: int, seconds: float) -> float:
        """Open a round and return how many seconds it actually runs for."""
        async with room.lock:
            now = utcnow()
            ends_at = now + timedelta(seconds=seconds)
            if room.state.game_ends_at is not None:
                # The game timer always wins. Clamping here, against a deadline read at
                # this instant, is what keeps `round.ends_at <= game_ends_at` exactly true.
                ends_at = min(ends_at, room.state.game_ends_at)

            # No prompt twice in one game, while there are fresh ones left to pick.
            previous = {r.prompt for r in room.state.history}
            if room.state.round:
                previous.add(room.state.round.prompt)
            prompt = pick_prompt(round_no, exclude=previous)
            room.inflight.clear()
            room.round_done = asyncio.Event()
            room.state.phase = Phase.ROUND
            room.state.round = Round(
                number=round_no,
                prompt=prompt.text,
                target=prompt.target,
                started_at=now,
                ends_at=ends_at,
            )
            await self._publish(room, EventMessage(kind="round_started", payload={
                "round": round_no,
                "prompt": prompt.text,
                "target": prompt.target,
                "ends_at": ends_at.isoformat(),
            }))
            # Fire-and-forget: a Gemini line plus a TTS round trip takes seconds, and the
            # round's clock has already started. The narration lands via `voice_ready`.
            self._spawn_narration(room, round_no, prompt)
            return max(0.0, (ends_at - utcnow()).total_seconds())

    async def _end_round(self, room: Room) -> None:
        """Commit the round: score every player who passed, see `score_round`."""
        async with room.lock:
            state = room.state
            state.phase = Phase.SCORING
            awarded: dict[str, int] = {}
            if state.round is not None:
                scores = score_round(state.round)
                for player_id, score in scores.items():
                    player = state.players.get(player_id)
                    if player is None:
                        continue
                    player.points += score.points
                    player.rounds_correct += 1
                    awarded[player_id] = score.points
                state.round.scores = scores
                state.round.points_awarded = awarded
                state.round.highlights = pick_highlights(state.round, scores)
                state.history.append(state.round.model_copy(deep=True))

            await self._publish(room, EventMessage(kind="round_ended", payload={
                "round": state.round.number if state.round else None,
                "target": state.round.target if state.round else None,
                "awarded": awarded,
            }))

    async def _finish_game(self, room: Room, reason: str = "rounds_complete") -> None:
        async with room.lock:
            room.state.phase = Phase.GAME_OVER
            # Blitz's answer to appending a scored round to `history`: the per-face
            # breakdown is published once, here, instead of riding in every snapshot all
            # game. Runs through the crash and cancel paths too, which is the point.
            if room.state.blitz is not None:
                for player_id, run in room.state.blitz.runs.items():
                    run.faces = room.blitz_done.get(player_id, [])
            # A crashed game's scores are whatever it got to, not a result: not recorded.
            if self.highscores is not None and reason != "crashed":
                finals = [
                    (p.client_id, p.name, p.points)
                    for p in room.state.players.values()
                    if p.client_id
                ]
                try:
                    await self.highscores.record(
                        finals,
                        room.state.config.mode,
                        room.state.config.rounds_per_game,
                    )
                except OSError:
                    # A full or read-only disk must not stop the game from ending.
                    log.exception("could not save high scores for room %s", room.state.room_id)
            await self._publish(room, EventMessage(kind="game_over", payload={
                "game_no": room.state.game_no,
                "reason": reason,
                "ranking": [
                    {"player_id": p.id, "name": p.name, "points": p.points}
                    for p in self.ranking(room.state)
                ],
            }))

    @staticmethod
    def ranking(state: GameState) -> list[Player]:
        """Most points first; an earlier join breaks a tie."""
        return sorted(
            state.players.values(), key=lambda p: (-p.points, p.joined_at)
        )

    # --- narration -------------------------------------------------------

    def _spawn_narration(self, room: Room, round_no: int, prompt: Prompt) -> None:
        """Start generating this round's spoken line. Must not be awaited by the driver."""
        if self.voice is None or not self.voice.enabled:
            return
        task = asyncio.create_task(
            self._narrate(room, round_no, prompt),
            name=f"voice-{room.state.room_id}-r{round_no}",
        )
        self._voice_tasks.add(task)
        task.add_done_callback(self._voice_tasks.discard)

    async def _narrate(self, room: Room, round_no: int, prompt: Prompt) -> None:
        """Generate the line, then patch it onto the round if that round is still current."""
        assert self.voice is not None
        try:
            narration = await self.voice.narrate(prompt)
        except asyncio.CancelledError:
            raise
        except Exception:
            # Narration is decoration: a failure must never disturb the round.
            log.warning("narration failed for room %s round %s", room.state.room_id, round_no,
                        exc_info=True)
            return
        if narration is None:
            return

        async with room.lock:
            current = room.state.round
            # Generation outlived its round (a short round, or a slow vendor). Dropping it
            # is correct: narrating round 1 over round 2 is worse than silence.
            if current is None or current.number != round_no:
                log.info("discarding late narration for round %s", round_no)
                return
            current.voice_line = narration.line
            current.audio_id = narration.audio_id
            await self._publish(room, EventMessage(kind="voice_ready", payload={
                "round": round_no,
                "line": narration.line,
                "audio_id": narration.audio_id,
            }))

    # --- internals -------------------------------------------------------

    async def _publish(self, room: Room, event: EventMessage | None = None) -> None:
        """Bump seq and fan out. Must be called with the room lock held."""
        room.state.seq += 1
        room.state.server_time = utcnow()
        if event is not None:
            await self.hub.broadcast(room.state.room_id, event)
        await self.hub.broadcast(
            room.state.room_id, StateMessage(seq=room.state.seq, state=room.state)
        )

    async def snapshot_to(self, room: Room, ws) -> None:
        async with room.lock:
            await self.hub.send(ws, StateMessage(seq=room.state.seq, state=room.state))

    async def shutdown(self) -> None:
        """Cancel every running game and wait for it, so nothing outlives the app."""
        tasks = [
            room.task
            for room in self.store.all()
            if room.task is not None and not room.task.done()
        ]
        # Narration tasks are not owned by a room, so they are cancelled alongside.
        tasks.extend(t for t in self._voice_tasks if not t.done())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
