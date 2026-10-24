import asyncio
import base64
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.models import ProcessResult
from app.processing import registry
from app.processing.base import RoundCtx

# A real 8x8 JPEG, generated once with PIL. The dummy processor only hashes bytes,
# but keeping the fixture a valid image means a real processor can be dropped in
# without touching the tests.
TINY_JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAoHBwgHBgoICAgLCgoLDhgQDg0NDh0VFhEYIx8l"
    "JCIfIiEmKzcvJik0KSEiMEExNDk7Pj4+JS5ESUM8SDc9Pjv/2wBDAQoLCw4NDhwQEBw7KCIo"
    "Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozv/wAAR"
    "CAAIAAgDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAA"
    "AgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkK"
    "FhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWG"
    "h4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl"
    "5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREA"
    "AgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYk"
    "NOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOE"
    "hYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk"
    "5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwCSiiivojxj/9k="
)


# --- deterministic processors -------------------------------------------------
# Scoring is "the processor's label equals the round's target", and the round target is
# picked at random, so asserting on points needs a processor whose verdict is known.


class HitProcessor:
    """Always answers with whatever the round asked for: every player is always correct."""

    name = "test-hit"

    async def process(self, frame: bytes, ctx: RoundCtx) -> ProcessResult:
        return ProcessResult(score=1.0, label=ctx.target, confidence=1.0, meta={})


class MissProcessor:
    """Never answers with a real label, so no answer can ever be correct."""

    name = "test-miss"

    async def process(self, frame: bytes, ctx: RoundCtx) -> ProcessResult:
        return ProcessResult(score=1.0, label="not-a-real-label", confidence=1.0, meta={})


class SlowProcessor:
    """Answers correctly, but slowly enough that the frame queue can fill up behind it.

    Short enough that a frame which does get through is still scored inside a short round.
    """

    name = "test-slow"
    latency_s = 1.0

    async def process(self, frame: bytes, ctx: RoundCtx) -> ProcessResult:
        await asyncio.sleep(self.latency_s)
        return ProcessResult(score=1.0, label=ctx.target, confidence=1.0, meta={})


class VerySlowProcessor(SlowProcessor):
    """Still working well after its round has ended, like a real model on a bad day.

    Used where a test needs a wide, load-independent window -- either to keep the queue
    full across several uploads, or to land a result on the far side of a round boundary.
    """

    name = "test-very-slow"
    latency_s = 3.0


registry.register(HitProcessor)
registry.register(MissProcessor)
registry.register(SlowProcessor)
registry.register(VerySlowProcessor)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        round_seconds=2,
        rounds_per_game=2,
        intermission_seconds=0,
        game_seconds=60,
        min_frame_interval_ms=0,
        media_dir=tmp_path / "media",
        processor="dummy",
        worker_count=2,
        queue_maxsize=8,
    )


def make_client(tmp_path: Path, **overrides) -> TestClient:
    """A client whose server is configured for one specific rule under test."""
    base = dict(
        round_seconds=2,
        rounds_per_game=2,
        intermission_seconds=0,
        game_seconds=60,
        min_frame_interval_ms=0,
        media_dir=tmp_path / "media",
        processor="dummy",
        worker_count=2,
        queue_maxsize=8,
    )
    return TestClient(create_app(Settings(**{**base, **overrides})))


@pytest.fixture
def hit_client(tmp_path: Path):
    """Every submitted frame is a correct answer."""
    with make_client(tmp_path, processor="test-hit") as c:
        yield c


@pytest.fixture
def miss_client(tmp_path: Path):
    """Every submitted frame is a wrong answer."""
    with make_client(tmp_path, processor="test-miss") as c:
        yield c


@pytest.fixture
def client(settings: Settings):
    with TestClient(create_app(settings)) as c:
        yield c


@pytest.fixture
def jpeg() -> bytes:
    return TINY_JPEG


def frame_files(data: bytes) -> dict:
    return {"file": ("frame.jpg", data, "image/jpeg")}


def create_room(client: TestClient, name: str = "host") -> dict:
    res = client.post("/api/rooms", json={"name": name})
    assert res.status_code == 201, res.text
    return res.json()


def join_room(client: TestClient, room_id: str, name: str) -> dict:
    res = client.post(f"/api/rooms/{room_id}/join", json={"name": name})
    assert res.status_code == 200, res.text
    return res.json()


def state_of(client: TestClient, room_id: str) -> dict:
    res = client.get(f"/api/rooms/{room_id}")
    assert res.status_code == 200, res.text
    return res.json()


def wait_for(client: TestClient, room_id: str, predicate, timeout: float = 10.0) -> dict:
    """Poll the authoritative state until it satisfies `predicate`.

    The phase machine runs on the server's own clock, so every assertion about a
    transition has to wait for the server to say it happened.
    """
    deadline = time.time() + timeout
    state = state_of(client, room_id)
    while time.time() < deadline:
        state = state_of(client, room_id)
        if predicate(state):
            return state
        time.sleep(0.02)
    raise AssertionError(f"timed out; last state: phase={state['phase']}")


def play_one_round(
    client: TestClient,
    room_id: str,
    submitters: list[dict],
    jpeg: bytes,
    host: dict | None = None,
) -> dict:
    """Start a game and upload one frame for each of `submitters` in round 1.

    Returns the state once every submission has been scored -- still inside the round,
    because points are only committed when the server ends it. `host` defaults to the
    first submitter; pass it when the player starting the game is not one of them.
    """
    host = host or submitters[0]
    res = client.post(f"/api/rooms/{room_id}/start", params={"player_id": host["player_id"]})
    assert res.status_code == 202, res.text
    wait_for(client, room_id, lambda s: s["phase"] == "round")

    for player in submitters:
        res = client.post(
            f"/api/rooms/{room_id}/frames",
            data={"player_id": player["player_id"]},
            files=frame_files(jpeg),
        )
        assert res.status_code == 202, res.text

    # Wait for the workers to settle every submission before the round can commit them.
    return wait_for(
        client,
        room_id,
        lambda s: s["round"] is not None
        and len(s["round"]["submissions"]) == len(submitters)
        and all(x["status"] == "done" for x in s["round"]["submissions"].values()),
    )
