"""Skipping a face: free, cooldown-limited, and blitz-only."""

import time

from tests.conftest import (
    TINY_JPEG,
    blitz_client,
    create_room,
    make_client,
    push_faces,
    run_of,
    skip_face,
    start_blitz,
    state_of,
    wait_for,
)


def test_skip_advances_the_cursor_and_pays_nothing(tmp_path):
    with blitz_client(tmp_path, processor="test-miss", blitz_face_seconds=60) as client:
        host = create_room(client)
        state = start_blitz(client, host["room_id"], host)
        first = run_of(state, host)["prompt"]

        res = skip_face(client, host["room_id"], host)
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["status"] == "skipped"
        assert body["face_no"] == 2
        assert body["skip_ready_at"]

        state = state_of(client, host["room_id"])
        run = run_of(state, host)
        assert run["face_no"] == 2
        assert run["skipped"] == 1
        assert run["last_outcome"] == "skipped"
        assert run["last_points"] == 0
        assert run["prompt"] != first
        assert state["players"][host["player_id"]]["points"] == 0


def test_a_second_skip_inside_the_cooldown_is_refused(tmp_path):
    with blitz_client(
        tmp_path, processor="test-miss", blitz_face_seconds=60, blitz_skip_cooldown_seconds=30
    ) as client:
        host = create_room(client)
        start_blitz(client, host["room_id"], host)
        assert skip_face(client, host["room_id"], host).status_code == 200

        res = skip_face(client, host["room_id"], host)
        assert res.status_code == 429, res.text
        assert "Skip again in" in res.json()["detail"]
        # And it really did not move.
        assert run_of(state_of(client, host["room_id"]), host)["face_no"] == 2


def test_the_cooldown_expires(tmp_path):
    with blitz_client(
        tmp_path, processor="test-miss", blitz_face_seconds=60, blitz_skip_cooldown_seconds=1
    ) as client:
        host = create_room(client)
        start_blitz(client, host["room_id"], host)
        assert skip_face(client, host["room_id"], host).status_code == 200
        time.sleep(1.1)
        assert skip_face(client, host["room_id"], host).status_code == 200
        assert run_of(state_of(client, host["room_id"]), host)["face_no"] == 3


def test_waiting_a_face_out_does_not_buy_a_skip(tmp_path):
    """An expiry must not reset the cooldown, or skipping would be free on a timer."""
    with blitz_client(
        tmp_path, processor="test-miss", blitz_face_seconds=1, blitz_skip_cooldown_seconds=30
    ) as client:
        host = create_room(client)
        start_blitz(client, host["room_id"], host)
        assert skip_face(client, host["room_id"], host).status_code == 200
        # Let a face lapse on its own, then try again.
        wait_for(client, host["room_id"], lambda s: run_of(s, host)["expired"] >= 1)
        assert skip_face(client, host["room_id"], host).status_code == 429


def test_a_passed_face_does_not_reset_the_cooldown_either(tmp_path):
    with blitz_client(
        tmp_path, processor="test-hit", blitz_face_seconds=60, blitz_skip_cooldown_seconds=30
    ) as client:
        host = create_room(client)
        start_blitz(client, host["room_id"], host)
        assert skip_face(client, host["room_id"], host).status_code == 200
        push_faces(client, host["room_id"], host, TINY_JPEG, 1)
        assert skip_face(client, host["room_id"], host).status_code == 429


def test_skip_is_refused_outside_blitz(tmp_path):
    with make_client(tmp_path, processor="test-hit") as client:
        host = create_room(client)
        res = skip_face(client, host["room_id"], host)
        assert res.status_code == 409
        assert "plays in rounds" in res.json()["detail"]


def test_skip_is_refused_in_the_lobby_and_after_the_game(tmp_path):
    with blitz_client(tmp_path, processor="test-hit", blitz_seconds=4) as client:
        host = create_room(client)
        assert skip_face(client, host["room_id"], host).status_code == 409

        start_blitz(client, host["room_id"], host)
        wait_for(client, host["room_id"], lambda s: s["phase"] == "game_over", timeout=15.0)
        assert skip_face(client, host["room_id"], host).status_code == 409


def test_a_stranger_cannot_skip(tmp_path):
    with blitz_client(tmp_path, processor="test-hit") as client:
        host = create_room(client)
        start_blitz(client, host["room_id"], host)
        res = client.post(
            f"/api/rooms/{host['room_id']}/skip", params={"player_id": "p_nobody"}
        )
        assert res.status_code == 404
