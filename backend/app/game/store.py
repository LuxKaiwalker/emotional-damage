"""In-process room storage.

Deliberately the narrowest possible surface, because this is the thing you replace first:
to run more than one backend process, back these methods with Redis (state as JSON, plus a
pub/sub channel per room so every process's ConnectionManager sees every broadcast).
"""

import asyncio
import secrets
import string
from dataclasses import dataclass, field

from app.models import GameState

_CODE_ALPHABET = string.ascii_uppercase + string.digits


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


class InMemoryRoomStore:
    def __init__(self) -> None:
        self._rooms: dict[str, Room] = {}
        self._by_code: dict[str, str] = {}

    def create(self, state: GameState) -> Room:
        room = Room(state=state)
        self._rooms[state.room_id] = room
        self._by_code[state.join_code] = state.room_id
        return room

    def get(self, room_id: str) -> Room | None:
        return self._rooms.get(room_id)

    def get_by_code(self, join_code: str) -> Room | None:
        room_id = self._by_code.get(join_code.upper())
        return self._rooms.get(room_id) if room_id else None

    def all(self) -> list[Room]:
        return list(self._rooms.values())

    def delete(self, room_id: str) -> None:
        room = self._rooms.pop(room_id, None)
        if room:
            self._by_code.pop(room.state.join_code, None)
