"""In-process room storage.

Deliberately the narrowest possible surface, because this is the thing you replace first:
to run more than one backend process, back these methods with Redis (state as JSON, plus a
pub/sub channel per room so every process's ConnectionManager sees every broadcast).
"""

import asyncio
import secrets
import string
from dataclasses import dataclass, field
from datetime import datetime

from app.models import GameState

# Letters only: a join code gets read out loud across a room, and digits invite the
# classic 0/O and 1/I mix-ups. 26**4 is ~457k codes, which is plenty of headroom for
# the collision check in `allocate_join_code` to stay a formality.
_CODE_ALPHABET = string.ascii_uppercase


class CodeExhausted(RuntimeError):
    """Every sampled join code was taken. Either raise JOIN_CODE_LENGTH or reap rooms."""


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(8)}"


def new_join_code(length: int = 4) -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(length))


@dataclass
class Room:
    state: GameState
    # Held for the whole duration of any state mutation: the engine is the only writer,
    # and this lock is what makes "the server holds the truth" true under concurrency.
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    # The per-room round driver (see GameEngine._run_game).
    task: asyncio.Task | None = None
    # When the room last had nobody connected, or None while someone is. The reaper
    # destroys a room that has been empty longer than EMPTY_ROOM_GRACE_SECONDS.
    empty_since: datetime | None = None


class InMemoryRoomStore:
    def __init__(self) -> None:
        self._rooms: dict[str, Room] = {}
        self._by_code: dict[str, str] = {}

    def allocate_join_code(self, length: int = 4, attempts: int = 64) -> str:
        """A code no live room is using. Codes are reusable once a room is destroyed."""
        for _ in range(attempts):
            code = new_join_code(length)
            if code not in self._by_code:
                return code
        raise CodeExhausted(f"no free {length}-letter join code after {attempts} tries")

    def create(self, state: GameState) -> Room:
        if state.room_id in self._rooms:
            raise ValueError(f"room {state.room_id} already exists")
        if state.join_code in self._by_code:
            raise ValueError(f"join code {state.join_code} already in use")
        room = Room(state=state)
        self._rooms[state.room_id] = room
        self._by_code[state.join_code] = state.room_id
        return room

    def get(self, room_id: str) -> Room | None:
        return self._rooms.get(room_id)

    def get_by_code(self, join_code: str) -> Room | None:
        room_id = self._by_code.get(join_code.strip().upper())
        return self._rooms.get(room_id) if room_id else None

    def all(self) -> list[Room]:
        return list(self._rooms.values())

    def count(self) -> int:
        return len(self._rooms)

    def delete(self, room_id: str) -> None:
        room = self._rooms.pop(room_id, None)
        if room:
            self._by_code.pop(room.state.join_code, None)
