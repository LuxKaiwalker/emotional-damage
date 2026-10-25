"""The per-face limit and the one global clock."""

from datetime import datetime

from app.game.engine import score_face
from tests.conftest import (
    TINY_JPEG,
    blitz_client,
    create_room,
    join_room,
    push_faces,
    run_of,
    start_blitz,
    state_of,
    wait_for,
)


def test_score_face_is_flat_plus_accuracy():
    assert score_face(0.0) == 100
    assert score_face(0.5) == 150
    assert score_face(1.0) == 200
    # Clamped, so a misbehaving processor cannot mint points.
    assert score_face(2.0) == 200
    assert score_face(-1.0) == 100


def test_a_face_rolls_over_on_its_own(tmp_path):
    """Nobody has to be sending frames: the driver's sweep moves a stalled player on."""
    with blitz_client(tmp_path, processor="test-miss", blitz_face_seconds=1) as client:
        host = create_room(client)
        state = start_blitz(client, host["room_id"], host)
        first = run_of(state, host)["prompt"]

        state = wait_for(client, host["room_id"], lambda s: run_of(s, host)["expired"] >= 1)
        run = run_of(state, host)
        assert run["face_no"] >= 2
        assert run["last_outcome"] == "expired"
        assert run["last_points"] == 0
        assert run["prompt"] != first
        assert state["players"][host["player_id"]]["points"] == 0


def test_several_faces_lapse_without_anyone_connected(tmp_path):
    with blitz_client(tmp_path, processor="test-miss", blitz_face_seconds=1) as client:
        host = create_room(client)
        start_blitz(client, host["room_id"], host)
        state = wait_for(
            client, host["room_id"], lambda s: run_of(s, host)["expired"] >= 3, timeout=15.0
        )
        assert run_of(state, host)["face_no"] >= 4


def test_a_face_deadline_never_outlives_the_game_clock(tmp_path):
    with blitz_client(tmp_path, processor="test-miss", blitz_seconds=4, blitz_face_seconds=60) as client:
        host = create_room(client)
        state = start_blitz(client, host["room_id"], host)
        assert run_of(state, host)["face_ends_at"] <= state["game_ends_at"]


def test_the_blitz_clock_is_blitz_seconds_not_game_seconds(tmp_path):
    """`game_seconds` is sized for a round schedule and means nothing here."""
    with blitz_client(tmp_path, processor="test-hit", blitz_seconds=120, game_seconds=600) as client:
        host = create_room(client)
        state = start_blitz(client, host["room_id"], host)
        span = (
            datetime.fromisoformat(state["game_ends_at"])
            - datetime.fromisoformat(state["game_started_at"])
        ).total_seconds()
        assert 119 <= span <= 121


def test_the_breakdown_records_every_outcome(tmp_path):
    with blitz_client(
        tmp_path, processor="test-hit", blitz_seconds=6, blitz_face_seconds=2
    ) as client:
        host = create_room(client)
        start_blitz(client, host["room_id"], host)
        push_faces(client, host["room_id"], host, TINY_JPEG, 1)
        client.post(f"/api/rooms/{host['room_id']}/skip", params={"player_id": host["player_id"]})

        state = wait_for(
            client, host["room_id"], lambda s: s["phase"] == "game_over", timeout=20.0
        )
        faces = run_of(state, host)["faces"]
        outcomes = [f["outcome"] for f in faces]
        assert outcomes[0] == "passed" and outcomes[1] == "skipped"
        assert "expired" in outcomes, "the rest of the clock should have lapsed faces"
        # Each entry carries enough to rebuild the round-by-round view.
        assert faces[0]["points"] == 200 and faces[0]["confidence"] == 1.0
        assert faces[1]["points"] == 0 and faces[1]["confidence"] is None
        assert all(f["prompt"] and f["target"] for f in faces)
        assert [f["index"] for f in faces] == list(range(len(faces)))


def test_leaving_drops_the_run(tmp_path):
    with blitz_client(tmp_path, processor="test-hit", blitz_face_seconds=60) as client:
        host = create_room(client)
        guest = join_room(client, host["room_id"], "guest")
        start_blitz(client, host["room_id"], host)

        res = client.post(
            f"/api/rooms/{host['room_id']}/leave", params={"player_id": guest["player_id"]}
        )
        assert res.status_code == 200, res.text
        state = state_of(client, host["room_id"])
        assert guest["player_id"] not in state["blitz"]["runs"]
        assert host["player_id"] in state["blitz"]["runs"]
