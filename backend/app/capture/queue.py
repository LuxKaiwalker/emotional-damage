"""Frame ingestion backpressure.

Uploads land on a bounded queue; a small pool of workers drains it, calls the processor,
and hands results to the engine. Bounded on purpose: when players out-produce the
processor, the right move for a live camera game is to throw away *stale* frames, not to
grow an unbounded backlog or to block the HTTP handler.
"""

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

from app.capture.media import MediaStore
from app.game.engine import GameEngine
from app.processing.base import Processor, RoundCtx

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class FrameJob:
    room_id: str
    player_id: str
    submission_id: str
    round_no: int
    prompt: str
    target: str
    path: Path


class FrameQueue:
    def __init__(
        self,
        engine: GameEngine,
        media: MediaStore,
        processor: Processor,
        maxsize: int,
        worker_count: int,
    ) -> None:
        self._queue: asyncio.Queue[FrameJob] = asyncio.Queue(maxsize=maxsize)
        self._engine = engine
        self._media = media
        self._processor = processor
        self._worker_count = worker_count
        self._workers: list[asyncio.Task] = []
        self.dropped = 0

    def start(self) -> None:
        self._workers = [
            asyncio.create_task(self._worker(i), name=f"frame-worker-{i}")
            for i in range(self._worker_count)
        ]

    async def stop(self) -> None:
        for task in self._workers:
            task.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()

    async def submit(self, job: FrameJob) -> bool:
        """Enqueue a frame, evicting the oldest queued one if the queue is full.

        Never blocks on the queue. Every frame this throws away is reported back to the
        engine, because the engine has already registered a submission for it: a frame
        that is dropped silently leaves that submission pending for the rest of the
        round, which reads as "still scoring" forever and quietly costs the player
        whatever that round was worth.
        """
        try:
            self._queue.put_nowait(job)
            return True
        except asyncio.QueueFull:
            pass

        try:
            stale = self._queue.get_nowait()
        except asyncio.QueueEmpty:
            # A queue that is both full and empty has no capacity at all, so the frame
            # that goes is this one.
            self.dropped += 1
            await self._abandon(job, "overloaded")
            return False

        # Newest data is worth more than oldest. No await between the get and the put,
        # so the slot just freed cannot be taken by anyone else.
        self._queue.task_done()
        self._queue.put_nowait(job)
        self.dropped += 1
        log.warning("frame queue full, dropped stale frame %s", stale.submission_id)
        await self._abandon(stale, "dropped_under_load")
        return True

    async def _abandon(self, job: FrameJob, reason: str) -> None:
        """Settle the submission of a frame that will never reach a processor."""
        await self._engine.apply_result(job.room_id, job.submission_id, None, error=reason)

    @property
    def depth(self) -> int:
        return self._queue.qsize()

    async def _worker(self, index: int) -> None:
        while True:
            job = await self._queue.get()
            try:
                await self._handle(job)
            except asyncio.CancelledError:
                raise
            except Exception:
                # A broken processor must never take down the worker pool.
                log.exception("worker %s failed on submission %s", index, job.submission_id)
                await self._engine.apply_result(
                    job.room_id, job.submission_id, None, error="processing_failed"
                )
            finally:
                self._queue.task_done()

    async def _handle(self, job: FrameJob) -> None:
        frame = await self._media.read(job.path)
        ctx = RoundCtx(
            room_id=job.room_id,
            player_id=job.player_id,
            round_no=job.round_no,
            prompt=job.prompt,
            target=job.target,
        )
        result = await self._processor.process(frame, ctx)
        await self._engine.apply_result(job.room_id, job.submission_id, result)

    async def drain(self) -> None:
        """Test helper: wait until every queued frame has been processed."""
        await self._queue.join()
