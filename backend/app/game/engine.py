"""The authoritative game. Nothing else is allowed to mutate GameState.

Invariants every public method upholds:
  1. Take the room lock.
  2. Mutate state, bump `seq`, refresh `server_time`.
  3. Broadcast the new snapshot (and any transient event) to the room.

Long sleeps happen *outside* the lock, so a running round never blocks frame ingestion.

The rules this file implements:
  * Scoring -- a round names a `target` label; a player whose last scored frame of that
    round carries that label gets `settings.points_per_correct` (one) point for it.
    Nothing else scores.
  * Timing -- every round has a deadline, and the game as a whole has one. The game
    timer wins: it truncates the round that would overrun it and ends the game.
  * Rooms -- created with a 4-letter join code, restartable once a game is over, and
    destroyed when the last player goes (immediately on leave, or after a grace period
    for players who just closed the tab).
"""

import asyncio
import logging
from datetime import timedelta
from typing import NamedTuple

from app.config import Settings
from app.game.hub import ConnectionManager
from app.game.prompts import Prompt, pick_prompt
from app.game.store import CodeExhausted, InMemoryRoomStore, Room, new_id
from app.game.voice import VoiceStudio
from app.models import (
    EventMessage,
    GameConfig,
    GameState,
    Phase,
    Player,
    ProcessResult,
    Round,
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


class AcceptedFrame(NamedTuple):
    """A registered submission, plus the round context the frame has to be processed with.

    Handed back whole so the upload path never has to read the round a second time: by
    the time it looked again, the round could already have ended.
    """

    submission: Submission
    prompt: str
    target: str


class GameError(Exception):
    """Caller did something the rules do not allow. Mapped to 4xx in the API layer."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class GameEngine:
    def __init__(
        self,
        store: InMemoryRoomStore,
        hub: ConnectionManager,
        settings: Settings,
        voice: VoiceStudio | None = None,
    ) -> None:
        self.store = store
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
            raise GameError(f"no such room: {room_id}", status_code=404)
        return room

    def resolve(self, room_id_or_code: str) -> Room:
        """Accept either a room id or a short join code, so the UI can take either."""
        return (
            self.store.get(room_id_or_code)
            or self.store.get_by_code(room_id_or_code)
            or self.require_room(room_id_or_code)
        )

    # --- rooms -----------------------------------------------------------

    async def create_room(self, host_name: str) -> tuple[Room, str]:
        host = Player(id=new_id("p"), name=host_name)
        try:
            join_code = self.store.allocate_join_code(self.settings.join_code_length)
        except CodeExhausted as exc:
            raise GameError("no join codes available; try again later", 503) from exc

        state = GameState(
            room_id=new_id("r"),
            join_code=join_code,
            host_id=host.id,
            players={host.id: host},
            config=GameConfig(
                round_seconds=self.settings.round_seconds,
                rounds_per_game=self.settings.rounds_per_game,
                game_seconds=self.settings.game_seconds,
                points_per_correct=self.settings.points_per_correct,
                capture_interval_ms=self.settings.capture_interval_ms,
                max_players=self.settings.max_players_per_room,
            ),
        )
        room = self.store.create(state)
        # Nobody has opened a socket yet, so the clock on an abandoned room starts here:
        # a room created by a client that then vanishes is reaped like any other.
        room.empty_since = utcnow()
        return room, host.id

    async def join(self, room_id: str, name: str) -> str:
        """Join at any phase. Mid-game joiners play from the next round at zero points."""
        room = self.resolve(room_id)
        async with room.lock:
            if len(room.state.players) >= self.settings.max_players_per_room:
                raise GameError("room is full", status_code=409)
            player = Player(id=new_id("p"), name=name)
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
                raise GameError("unknown player for this room", status_code=404)
            if state.round is not None:
                state.round.submissions.pop(player_id, None)

            if not state.players:
                await self._destroy(room, reason="empty")
                return True

            if state.host_id == player_id:
                state.host_id = self._next_host(state)
            if not any(p.connected for p in state.players.values()):
                room.empty_since = room.empty_since or utcnow()

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
            await self._publish(room)

    # --- game lifecycle --------------------------------------------------

    async def start_game(self, room_id: str, player_id: str) -> None:
        """Host starts a game from the lobby and the game timer begins ticking."""
        room = self.require_room(room_id)
        async with room.lock:
            state = room.state
            if player_id != state.host_id:
                raise GameError("only the host can start the game", status_code=403)
            if state.phase is not Phase.LOBBY:
                raise GameError(f"cannot start from phase {state.phase.value}", 409)
            if room.task is not None and not room.task.done():
                raise GameError("game already running", status_code=409)

            now = utcnow()
            state.game_started_at = now
            state.game_ends_at = now + timedelta(seconds=state.config.game_seconds)
            await self._publish(room, EventMessage(kind="game_started", payload={
                "game_no": state.game_no,
                "ends_at": state.game_ends_at.isoformat(),
            }))

        room.task = asyncio.create_task(self._run_game(room), name=f"game:{room_id}")

    async def set_rounds(self, room_id: str, player_id: str, rounds: int) -> None:
        """Host picks the game length in the lobby. It sticks across restarts.

        The game timer grows to fit: a hard cap shorter than the rounds asked for would
        quietly end the game early, and the deep scan would list fewer rounds than promised.
        """
        room = self.require_room(room_id)
        async with room.lock:
            state = room.state
            if player_id != state.host_id:
                raise GameError("only the host can change the rounds", status_code=403)
            if state.phase is not Phase.LOBBY:
                raise GameError(f"cannot change rounds in phase {state.phase.value}", 409)
            if rounds not in ROUND_CHOICES:
                choices = " or ".join(map(str, ROUND_CHOICES))
                raise GameError(f"rounds must be {choices}", status_code=422)

            needed = (
                rounds * self.settings.round_seconds
                + (rounds - 1) * self.settings.intermission_seconds
                + GAME_SLACK_SECONDS
            )
            state.config.rounds_per_game = rounds
            state.config.game_seconds = max(self.settings.game_seconds, needed)
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
                raise GameError("only the host can restart the game", status_code=403)
            if state.phase is not Phase.GAME_OVER:
                raise GameError(
                    f"can only restart after a game is over (phase {state.phase.value})", 409
                )
            if room.task is not None and not room.task.done():
                raise GameError("game still running", status_code=409)

            for player in state.players.values():
                player.points = 0
                player.rounds_correct = 0
                player.last_frame_at = None
            state.round = None
            state.history = []
            state.phase = Phase.LOBBY
            state.game_no += 1
            state.game_started_at = None
            state.game_ends_at = None
            room.task = None

            await self._publish(room, EventMessage(kind="game_restarted", payload={
                "game_no": state.game_no,
            }))

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
                raise GameError("unknown player for this room", status_code=404)
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
                raise GameError("unknown player for this room", status_code=404)
            if state.phase is not Phase.ROUND or state.round is None:
                raise GameError(f"not accepting frames in phase {state.phase.value}", 409)

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
            # Newest frame per player wins; the previous pending one is simply superseded.
            state.round.submissions[player_id] = submission
            await self._publish(room)
            return AcceptedFrame(submission, state.round.prompt, state.round.target)

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
            if state.round is None:
                return
            submission = next(
                (s for s in state.round.submissions.values() if s.id == submission_id), None
            )
            if submission is None:
                # Superseded by a newer frame, or the round already moved on. Drop it.
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

            await self._publish(room, EventMessage(kind="submission_scored", payload={
                "player_id": submission.player_id,
                "submission_id": submission.id,
                "status": submission.status.value,
                "correct": submission.correct,
                "result": result.model_dump(mode="json") if result else None,
            }))

    @staticmethod
    def _is_correct(result: ProcessResult | None, target: str) -> bool:
        """The whole scoring rule: the processor's label has to be the one asked for."""
        return result is not None and result.label == target

    # --- round driver ----------------------------------------------------

    async def _run_game(self, room: Room) -> None:
        """One task per active room: owns every phase transition and its timing."""
        try:
            reason = "rounds_complete"
            rounds = room.state.config.rounds_per_game
            for round_no in range(1, rounds + 1):
                budget = self._round_budget(room)
                if budget is None:
                    reason = "time_up"
                    break

                # The round reports back how long it actually got: `budget` was measured
                # a moment earlier, and the round's deadline is clamped to the game's.
                await asyncio.sleep(await self._begin_round(room, round_no, budget))
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

    def _seconds_left(self, room: Room) -> float:
        """Game time remaining. Read without the lock: one field, no await in between."""
        ends_at = room.state.game_ends_at
        if ends_at is None:
            return 0.0
        return (ends_at - utcnow()).total_seconds()

    def _round_budget(self, room: Room) -> float | None:
        """How long the next round may run, or None when the game timer has no room left."""
        remaining = self._seconds_left(room)
        if remaining < MIN_ROUND_SECONDS:
            return None
        return min(float(self.settings.round_seconds), remaining)

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
        """Commit the round: one point to every player whose last frame hit the target."""
        async with room.lock:
            state = room.state
            state.phase = Phase.SCORING
            awarded: dict[str, int] = {}
            if state.round is not None:
                target = state.round.target
                for player_id, submission in state.round.submissions.items():
                    player = state.players.get(player_id)
                    if player is None or submission.status is not SubmissionStatus.DONE:
                        continue
                    if not self._is_correct(submission.result, target):
                        continue
                    player.points += self.settings.points_per_correct
                    player.rounds_correct += 1
                    awarded[player_id] = self.settings.points_per_correct
                state.round.points_awarded = awarded
                state.history.append(state.round.model_copy(deep=True))

            await self._publish(room, EventMessage(kind="round_ended", payload={
                "round": state.round.number if state.round else None,
                "target": state.round.target if state.round else None,
                "awarded": awarded,
            }))

    async def _finish_game(self, room: Room, reason: str = "rounds_complete") -> None:
        async with room.lock:
            room.state.phase = Phase.GAME_OVER
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
