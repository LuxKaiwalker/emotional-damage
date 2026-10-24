"""The authoritative game. Nothing else is allowed to mutate GameState.

Invariants every public method upholds:
  1. Take the room lock.
  2. Mutate state, bump `seq`, refresh `server_time`.
  3. Broadcast the new snapshot (and any transient event) to the room.

Long sleeps happen *outside* the lock, so a running round never blocks frame ingestion.
"""

import asyncio
import logging
from datetime import timedelta

from app.config import Settings
from app.game.hub import ConnectionManager
from app.game.prompts import pick_prompt
from app.game.store import InMemoryRoomStore, Room, new_id, new_join_code
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


class GameError(Exception):
    """Caller did something the rules do not allow. Mapped to 4xx in the API layer."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class GameEngine:
    def __init__(
        self, store: InMemoryRoomStore, hub: ConnectionManager, settings: Settings
    ) -> None:
        self.store = store
        self.hub = hub
        self.settings = settings

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

    # --- mutations -------------------------------------------------------

    async def create_room(self, host_name: str) -> tuple[Room, str]:
        host = Player(id=new_id("p"), name=host_name)
        state = GameState(
            room_id=new_id("r"),
            join_code=new_join_code(),
            host_id=host.id,
            players={host.id: host},
            config=GameConfig(
                round_seconds=self.settings.round_seconds,
                rounds_per_game=self.settings.rounds_per_game,
                capture_interval_ms=self.settings.capture_interval_ms,
            ),
        )
        room = self.store.create(state)
        return room, host.id

    async def join(self, room_id: str, name: str) -> str:
        room = self.resolve(room_id)
        async with room.lock:
            if room.state.phase is Phase.GAME_OVER:
                raise GameError("game is over; create a new room", status_code=409)
            player = Player(id=new_id("p"), name=name)
            room.state.players[player.id] = player
            await self._publish(room, EventMessage(kind="player_joined", payload={
                "player_id": player.id, "name": player.name,
            }))
        return player.id

    async def set_connected(self, room_id: str, player_id: str, connected: bool) -> None:
        room = self.require_room(room_id)
        async with room.lock:
            player = room.state.players.get(player_id)
            if player is None or player.connected == connected:
                return
            player.connected = connected
            await self._publish(room)

    async def start_game(self, room_id: str, player_id: str) -> None:
        room = self.require_room(room_id)
        async with room.lock:
            if player_id != room.state.host_id:
                raise GameError("only the host can start the game", status_code=403)
            if room.state.phase is not Phase.LOBBY:
                raise GameError(f"cannot start from phase {room.state.phase.value}", 409)
            if room.task is not None and not room.task.done():
                raise GameError("game already running", status_code=409)

        room.task = asyncio.create_task(self._run_game(room), name=f"game:{room_id}")

    async def submit_frame(self, room_id: str, player_id: str, size: int) -> Submission:
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
            return submission

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
            else:
                submission.status = SubmissionStatus.DONE
                submission.result = result

            await self._publish(room, EventMessage(kind="submission_scored", payload={
                "player_id": submission.player_id,
                "submission_id": submission.id,
                "status": submission.status.value,
                "result": result.model_dump(mode="json") if result else None,
            }))

    # --- round driver ----------------------------------------------------

    async def _run_game(self, room: Room) -> None:
        """One task per active room: owns every phase transition and its timing."""
        try:
            for round_no in range(1, self.settings.rounds_per_game + 1):
                await self._begin_round(room, round_no)
                await asyncio.sleep(self.settings.round_seconds)
                await self._end_round(room)
                if round_no < self.settings.rounds_per_game:
                    await asyncio.sleep(self.settings.intermission_seconds)
            await self._finish_game(room)
        except asyncio.CancelledError:
            log.info("game task cancelled for room %s", room.state.room_id)
            raise
        except Exception:
            log.exception("game task crashed for room %s", room.state.room_id)
            await self._finish_game(room)

    async def _begin_round(self, room: Room, round_no: int) -> None:
        async with room.lock:
            now = utcnow()
            previous = {room.state.round.prompt} if room.state.round else set()
            room.state.phase = Phase.ROUND
            room.state.round = Round(
                number=round_no,
                prompt=pick_prompt(round_no, exclude=previous),
                started_at=now,
                ends_at=now + timedelta(seconds=self.settings.round_seconds),
            )
            await self._publish(room, EventMessage(kind="round_started", payload={
                "round": round_no, "prompt": room.state.round.prompt,
            }))

    async def _end_round(self, room: Room) -> None:
        """Commit the round: each player's last scored frame is added to their total."""
        async with room.lock:
            state = room.state
            state.phase = Phase.SCORING
            awarded: dict[str, float] = {}
            if state.round is not None:
                for player_id, submission in state.round.submissions.items():
                    player = state.players.get(player_id)
                    if player is None or submission.result is None:
                        continue
                    if submission.status is not SubmissionStatus.DONE:
                        continue
                    player.score = round(player.score + submission.result.score, 2)
                    awarded[player_id] = submission.result.score

            await self._publish(room, EventMessage(kind="round_ended", payload={
                "round": state.round.number if state.round else None,
                "awarded": awarded,
            }))

    async def _finish_game(self, room: Room) -> None:
        async with room.lock:
            room.state.phase = Phase.GAME_OVER
            ranking = sorted(
                room.state.players.values(), key=lambda p: p.score, reverse=True
            )
            await self._publish(room, EventMessage(kind="game_over", payload={
                "ranking": [{"player_id": p.id, "name": p.name, "score": p.score} for p in ranking],
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
        for room in self.store.all():
            if room.task is not None and not room.task.done():
                room.task.cancel()
