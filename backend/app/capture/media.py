"""Where frame bytes live.

Local disk, keyed by submission id, with a TTL reaper -- enough to debug and replay a
round. Swap for S3/GCS by reimplementing write/read/path; nothing else depends on it.
"""

import asyncio
import logging
import os
import shutil
import time
from pathlib import Path

log = logging.getLogger(__name__)


class MediaStore:
    def __init__(self, root: Path, ttl_seconds: int) -> None:
        self.root = root
        self.ttl_seconds = ttl_seconds
        self.root.mkdir(parents=True, exist_ok=True)
        # (room_id, player_id) -> the player's newest frame and when it landed (monotonic).
        # Lets a submission that arrived without a frame borrow the one closest to it.
        self._latest: dict[tuple[str, str], tuple[Path, float]] = {}

    def path_for(self, room_id: str, submission_id: str) -> Path:
        return self.root / room_id / f"{submission_id}.jpg"

    async def write(
        self, room_id: str, submission_id: str, data: bytes, player_id: str | None = None
    ) -> Path:
        path = self.path_for(room_id, submission_id)
        # Disk I/O off the event loop: a slow FS must not stall state broadcasts.
        await asyncio.to_thread(self._write_sync, path, data)
        if player_id is not None:
            self._latest[(room_id, player_id)] = (path, time.monotonic())
        return path

    async def borrow_latest(
        self, room_id: str, player_id: str, submission_id: str, max_age_s: float
    ) -> Path | None:
        """Store the player's newest frame under `submission_id` too, if it is fresh enough.

        For a submission that was scored without a frame of its own -- the Presage fast
        path passes a player off a reading -- so it still has a picture to show. Nothing
        is borrowed when the newest frame is older than `max_age_s`: that frame may not
        show the face that was scored (it could even be from the round before).
        """
        latest = self._latest.get((room_id, player_id))
        if latest is None or time.monotonic() - latest[1] > max_age_s:
            return None
        target = self.path_for(room_id, submission_id)
        try:
            await asyncio.to_thread(self._link_sync, latest[0], target)
        except OSError:
            # Reaped in the meantime, or a full disk: the frame is a nicety, not a result.
            log.warning("could not borrow a frame for submission %s", submission_id)
            return None
        return target

    @staticmethod
    def _link_sync(source: Path, target: Path) -> None:
        # A hard link costs no space and expires with its source; copy where links fail.
        try:
            os.link(source, target)
        except OSError:
            shutil.copyfile(source, target)

    @staticmethod
    def _write_sync(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    async def read(self, path: Path) -> bytes:
        return await asyncio.to_thread(path.read_bytes)

    def find(self, submission_id: str) -> Path | None:
        matches = sorted(self.root.glob(f"*/{submission_id}.jpg"))
        return matches[0] if matches else None

    async def reap_forever(self, interval_seconds: int = 60) -> None:
        """Delete frames older than the TTL so a long session cannot fill the disk."""
        while True:
            try:
                await asyncio.sleep(interval_seconds)
                await asyncio.to_thread(self._reap_once)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("media reaper iteration failed")

    def _reap_once(self) -> None:
        cutoff = time.time() - self.ttl_seconds
        # Forget players whose newest frame is long gone (left, or their room was destroyed).
        stale = time.monotonic() - self.ttl_seconds
        for key, (_, at) in list(self._latest.items()):
            if at < stale:
                self._latest.pop(key, None)
        for path in self.root.rglob("*.jpg"):
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink(missing_ok=True)
            except OSError:
                continue
