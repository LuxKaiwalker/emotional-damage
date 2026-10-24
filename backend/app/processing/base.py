"""The seam between the game and whatever actually looks at a camera frame."""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from app.models import ProcessResult


@dataclass(frozen=True)
class RoundCtx:
    """Everything a processor is allowed to know about the frame it was handed."""

    room_id: str
    player_id: str
    round_no: int
    prompt: str
    # The label this round is asking for. A real processor can classify against it;
    # the engine compares it to the returned label to decide correctness either way.
    target: str


@runtime_checkable
class Processor(Protocol):
    name: str

    async def process(self, frame: bytes, ctx: RoundCtx) -> ProcessResult:
        """Score a single JPEG frame.

        Must not mutate game state -- return a result and let the engine apply it.
        If your implementation is CPU-bound and synchronous (most CV / torch models are),
        do NOT block here: hand it to a thread with
        `await asyncio.get_running_loop().run_in_executor(pool, fn, frame)`.
        """
        ...
