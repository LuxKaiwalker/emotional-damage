"""Where frame bytes live.

Local disk, keyed by submission id, with a TTL reaper -- enough to debug and replay a
round. Swap for S3/GCS by reimplementing write/read/path; nothing else depends on it.
"""

import asyncio
import logging
import time
from pathlib import Path

log = logging.getLogger(__name__)


class MediaStore:
    def __init__(self, root: Path, ttl_seconds: int) -> None:
        self.root = root
        self.ttl_seconds = ttl_seconds
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, room_id: str, submission_id: str) -> Path:
        return self.root / room_id / f"{submission_id}.jpg"

    async def write(self, room_id: str, submission_id: str, data: bytes) -> Path:
        path = self.path_for(room_id, submission_id)
        # Disk I/O off the event loop: a slow FS must not stall state broadcasts.
        await asyncio.to_thread(self._write_sync, path, data)
        return path

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
        for path in self.root.rglob("*.jpg"):
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink(missing_ok=True)
            except OSError:
                continue
