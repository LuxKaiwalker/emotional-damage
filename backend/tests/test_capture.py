"""The rejection matrix for frame upload. A refused frame must never corrupt state."""

import time

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.conftest import create_room, frame_files, join_room


def _start_round(client: TestClient, room_id: str, player_id: str) -> dict:
    client.post(f"/api/rooms/{room_id}/start", params={"player_id": player_id})
    deadline = time.time() + 5
    while time.time() < deadline:
        state = client.get(f"/api/rooms/{room_id}").json()
        if state["phase"] == "round":
            return state
    raise AssertionError("round never started")


def test_rejects_non_jpeg(client, jpeg):
    host = create_room(client)
    _start_round(client, host["room_id"], host["player_id"])

    res = client.post(
        f"/api/rooms/{host['room_id']}/frames",
        data={"player_id": host["player_id"]},
        files={"file": ("frame.png", jpeg, "image/png")},
    )
    assert res.status_code == 415


def test_rejects_empty_frame(client):
    host = create_room(client)
    _start_round(client, host["room_id"], host["player_id"])

    res = client.post(
        f"/api/rooms/{host['room_id']}/frames",
        data={"player_id": host["player_id"]},
        files=frame_files(b""),
    )
    assert res.status_code == 400


def test_rejects_oversized_frame(client, jpeg):
    host = create_room(client)
    _start_round(client, host["room_id"], host["player_id"])

    oversized = jpeg + b"\x00" * (2 * 1024 * 1024)
    res = client.post(
        f"/api/rooms/{host['room_id']}/frames",
        data={"player_id": host["player_id"]},
        files=frame_files(oversized),
    )
    assert res.status_code == 413


def test_rejects_unknown_player(client, jpeg):
    host = create_room(client)
    _start_round(client, host["room_id"], host["player_id"])

    res = client.post(
        f"/api/rooms/{host['room_id']}/frames",
        data={"player_id": "p_nope"},
        files=frame_files(jpeg),
    )
    assert res.status_code == 404


def test_rejects_frames_outside_a_round(client, jpeg):
    """Still in the lobby: the server, not the client, decides when capture counts."""
    host = create_room(client)
    res = client.post(
        f"/api/rooms/{host['room_id']}/frames",
        data={"player_id": host["player_id"]},
        files=frame_files(jpeg),
    )
    assert res.status_code == 409


def test_unknown_room_is_404(client, jpeg):
    res = client.post(
        "/api/rooms/r_missing/frames",
        data={"player_id": "p_x"},
        files=frame_files(jpeg),
    )
    assert res.status_code == 404


@pytest.fixture
def throttled_client(tmp_path):
    settings = Settings(
        round_seconds=5,
        rounds_per_game=1,
        intermission_seconds=0,
        min_frame_interval_ms=10_000,  # effectively one frame per round
        media_dir=tmp_path / "media",
        processor="dummy",
    )
    with TestClient(create_app(settings)) as c:
        yield c


def test_rate_limited_frame_is_skipped_not_an_error(throttled_client, jpeg):
    """Dropping a too-fast frame is normal operation, so the client sees 200 + skipped."""
    host = create_room(throttled_client)
    _start_round(throttled_client, host["room_id"], host["player_id"])

    first = throttled_client.post(
        f"/api/rooms/{host['room_id']}/frames",
        data={"player_id": host["player_id"]},
        files=frame_files(jpeg),
    )
    assert first.status_code == 202
    assert first.json()["skipped"] is False

    second = throttled_client.post(
        f"/api/rooms/{host['room_id']}/frames",
        data={"player_id": host["player_id"]},
        files=frame_files(jpeg),
    )
    assert second.status_code == 200
    assert second.json() == {"skipped": True, "reason": "rate_limited"}


def test_newest_frame_supersedes_the_previous_one(client, jpeg):
    """One submission slot per player per round: live capture wants the latest frame."""
    host = create_room(client)
    guest = join_room(client, host["room_id"], "bob")
    room_id = host["room_id"]
    _start_round(client, room_id, host["player_id"])

    ids = []
    for _ in range(3):
        res = client.post(
            f"/api/rooms/{room_id}/frames",
            data={"player_id": host["player_id"]},
            files=frame_files(jpeg),
        )
        ids.append(res.json()["submission_id"])

    state = client.get(f"/api/rooms/{room_id}").json()
    submissions = state["round"]["submissions"]
    assert list(submissions) == [host["player_id"]]
    assert submissions[host["player_id"]]["id"] == ids[-1]
    assert guest["player_id"] not in submissions
