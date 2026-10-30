"""Skipping a face: free, blitz-only, and not available until the face has been looked at.

The rule is **per face, not per skip**. Every face -- the first one, and every one that
replaces a passed, skipped or lapsed face -- has to be on screen for
`blitz_skip_after_seconds` before it can be waved away. A cooldown measured from the last
skip would let a player hammer through the sequence hunting for an easy face; this makes
them spend the same time on every one.
"""

import time
from datetime import datetime

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


# --- the per-face wait ------------------------------------------------------


def test_the_first_face_cannot_be_skipped_immediately(tmp_path):
    """The wait applies from the very first face, not only after a skip."""
    with blitz_client(
        tmp_path, processor="test-miss", blitz_face_seconds=60, blitz_skip_after_seconds=30
    ) as client:
        host = create_room(client)
        state = start_blitz(client, host["room_id"], host)
        assert run_of(state, host)["skip_ready_at"] is not None

        res = skip_face(client, host["room_id"], host)
        assert res.status_code == 429, res.text
        assert "Skip again in" in res.json()["detail"]
        assert run_of(state_of(client, host["room_id"]), host)["face_no"] == 1


def test_skip_unlocks_once_the_face_has_been_up_long_enough(tmp_path):
    with blitz_client(
        tmp_path, processor="test-miss", blitz_face_seconds=60, blitz_skip_after_seconds=1
    ) as client:
        host = create_room(client)
        start_blitz(client, host["room_id"], host)
        assert skip_face(client, host["room_id"], host).status_code == 429
        time.sleep(1.1)
        assert skip_face(client, host["room_id"], host).status_code == 200
        assert run_of(state_of(client, host["room_id"]), host)["face_no"] == 2


def test_skip_ready_at_is_measured_from_the_face_not_the_skip(tmp_path):
    """The timestamp the UI counts down to is `face_started_at` + the wait, exactly."""
    with blitz_client(
        tmp_path, processor="test-miss", blitz_face_seconds=60, blitz_skip_after_seconds=4
    ) as client:
        host = create_room(client)
        state = start_blitz(client, host["room_id"], host)
        run = run_of(state, host)
        started = datetime.fromisoformat(run["face_started_at"])
        ready = datetime.fromisoformat(run["skip_ready_at"])
        assert (ready - started).total_seconds() == 4


def test_every_new_face_re_arms_the_wait(tmp_path):
    """A skipped face hands you a fresh one, and that one has to be looked at too."""
    with blitz_client(
        tmp_path, processor="test-miss", blitz_face_seconds=60, blitz_skip_after_seconds=1
    ) as client:
        host = create_room(client)
        start_blitz(client, host["room_id"], host)

        for expected_face in (2, 3, 4):
            time.sleep(1.1)
            res = skip_face(client, host["room_id"], host)
            assert res.status_code == 200, res.text
            run = run_of(state_of(client, host["room_id"]), host)
            assert run["face_no"] == expected_face
            # Armed again, from the face that just opened.
            started = datetime.fromisoformat(run["face_started_at"])
            ready = datetime.fromisoformat(run["skip_ready_at"])
            assert (ready - started).total_seconds() == 1
            # ...and so not skippable again right now.
            assert skip_face(client, host["room_id"], host).status_code == 429


def test_a_lapsed_face_also_re_arms_the_wait(tmp_path):
    """Waiting one face out does not bank a skip for the next one.

    This is the case a per-skip cooldown gets wrong in the other direction: it would let
    a player sit out one face and then skip freely. The wait belongs to the face.
    """
    with blitz_client(
        tmp_path, processor="test-miss", blitz_face_seconds=1, blitz_skip_after_seconds=30
    ) as client:
        host = create_room(client)
        start_blitz(client, host["room_id"], host)
        state = wait_for(client, host["room_id"], lambda s: run_of(s, host)["expired"] >= 1)
        run = run_of(state, host)
        assert run["face_no"] >= 2
        started = datetime.fromisoformat(run["face_started_at"])
        ready = datetime.fromisoformat(run["skip_ready_at"])
        assert (ready - started).total_seconds() == 30
        assert skip_face(client, host["room_id"], host).status_code == 429


def test_a_passed_face_also_re_arms_the_wait(tmp_path):
    """Landing a face is not a licence to skip the next one either."""
    with blitz_client(
        tmp_path, processor="test-hit", blitz_face_seconds=60, blitz_skip_after_seconds=30
    ) as client:
        host = create_room(client)
        start_blitz(client, host["room_id"], host)
        state = push_faces(client, host["room_id"], host, TINY_JPEG, 1)
        run = run_of(state, host)
        assert run["face_no"] == 2
        started = datetime.fromisoformat(run["face_started_at"])
        ready = datetime.fromisoformat(run["skip_ready_at"])
        assert (ready - started).total_seconds() == 30
        assert skip_face(client, host["room_id"], host).status_code == 429


def test_a_face_shorter_than_the_wait_simply_expires(tmp_path):
    """A host can set a face limit below the skip wait; nothing breaks.

    The face rolls over on its own before its skip ever unlocks, which is harmless --
    a face that short is not one anybody needs to escape from.
    """
    with blitz_client(
        tmp_path, processor="test-miss", blitz_face_seconds=2, blitz_skip_after_seconds=30
    ) as client:
        host = create_room(client)
        start_blitz(client, host["room_id"], host)
        assert skip_face(client, host["room_id"], host).status_code == 429
        state = wait_for(client, host["room_id"], lambda s: run_of(s, host)["expired"] >= 1)
        assert run_of(state, host)["face_no"] >= 2
        assert state["players"][host["player_id"]]["points"] == 0


def test_zero_makes_skip_available_at_once(tmp_path):
    """The wait is a setting, and switching it off has to actually switch it off."""
    with blitz_client(
        tmp_path, processor="test-miss", blitz_face_seconds=60, blitz_skip_after_seconds=0
    ) as client:
        host = create_room(client)
        start_blitz(client, host["room_id"], host)
        for expected in (2, 3, 4):
            assert skip_face(client, host["room_id"], host).status_code == 200
            assert run_of(state_of(client, host["room_id"]), host)["face_no"] == expected


# --- guards -----------------------------------------------------------------


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
