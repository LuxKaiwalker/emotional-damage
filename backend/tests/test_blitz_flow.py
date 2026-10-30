"""Blitz end to end: the shared sequence, asynchronous cursors, and points per face."""

import json

from app.game.prompts import PROMPTS
from tests.conftest import (
    TINY_JPEG,
    blitz_client,
    create_room,
    join_room,
    push_faces,
    run_of,
    send_frame,
    start_blitz,
    state_of,
    wait_for,
)


def test_blitz_opens_runs_and_no_round(tmp_path):
    with blitz_client(tmp_path, processor="test-hit") as client:
        host = create_room(client)
        guest = join_room(client, host["room_id"], "guest")
        state = start_blitz(client, host["room_id"], host)

        # Exactly one of `round` / `blitz` is ever set.
        assert state["round"] is None
        assert state["config"]["mode"] == "blitz"
        assert set(state["blitz"]["runs"]) == {host["player_id"], guest["player_id"]}
        for player in (host, guest):
            run = run_of(state, player)
            assert run["cursor"] == 0 and run["face_no"] == 1
            assert run["passed"] == run["skipped"] == run["expired"] == 0
            assert run["prompt"] and run["target"]


def test_a_passed_face_pays_base_plus_accuracy_immediately(tmp_path):
    """test-hit answers with confidence 1.0, so a face is worth the full 200."""
    with blitz_client(tmp_path, processor="test-hit") as client:
        host = create_room(client)
        start_blitz(client, host["room_id"], host)

        state = push_faces(client, host["room_id"], host, TINY_JPEG, 1)
        run = run_of(state, host)
        assert run["passed"] == 1
        assert run["cursor"] == 1 and run["face_no"] == 2
        assert run["last_outcome"] == "passed"
        assert run["last_points"] == 200
        # Committed on the spot: blitz has no round boundary to defer to.
        assert state["players"][host["player_id"]]["points"] == 200
        assert state["players"][host["player_id"]]["rounds_correct"] == 1

        state = push_faces(client, host["room_id"], host, TINY_JPEG, 1)
        assert state["players"][host["player_id"]]["points"] == 400
        assert run_of(state, host)["face_no"] == 3


def test_a_weak_read_passes_a_label_only_blitz(tmp_path):
    with blitz_client(tmp_path, processor="test-weak", blitz_pass_confidence=0.0) as client:
        host = create_room(client)
        start_blitz(client, host["room_id"], host)
        state = push_faces(client, host["room_id"], host, TINY_JPEG, 1)
        # 100 flat + round(0.2 * 100).
        assert run_of(state, host)["last_points"] == 120


def test_a_miss_scores_nothing_and_does_not_advance(tmp_path):
    with blitz_client(tmp_path, processor="test-miss") as client:
        host = create_room(client)
        start_blitz(client, host["room_id"], host)

        res = send_frame(client, host["room_id"], host, TINY_JPEG)
        assert res.status_code == 202
        state = wait_for(
            client,
            host["room_id"],
            lambda s: (run_of(s, host)["submission"] or {}).get("status") == "done",
        )
        run = run_of(state, host)
        assert run["passed"] == 0
        assert run["face_no"] == 1, "a miss must not move the cursor"
        assert run["submission"]["correct"] is False
        assert state["players"][host["player_id"]]["points"] == 0


def test_frames_are_still_welcome_after_a_pass(tmp_path):
    """Blitz never raises AlreadyPassed: passing advances you, so there is always a face."""
    with blitz_client(tmp_path, processor="test-hit") as client:
        host = create_room(client)
        start_blitz(client, host["room_id"], host)
        push_faces(client, host["room_id"], host, TINY_JPEG, 1)

        res = send_frame(client, host["room_id"], host, TINY_JPEG)
        assert res.status_code == 202, res.text
        assert res.json()["skipped"] is False


def test_players_progress_independently(tmp_path):
    """The whole point of the mode: one player's cursor moves, the other's does not."""
    with blitz_client(tmp_path, processor="test-hit", blitz_face_seconds=60) as client:
        host = create_room(client)
        guest = join_room(client, host["room_id"], "guest")
        start_blitz(client, host["room_id"], host)

        state = push_faces(client, host["room_id"], host, TINY_JPEG, 3)
        assert run_of(state, host)["face_no"] == 4
        assert run_of(state, guest)["face_no"] == 1, "the guest sent nothing"
        assert state["players"][guest["player_id"]]["points"] == 0


def test_the_sequence_is_the_same_for_everyone(tmp_path):
    """The fairness guarantee, observed through the wire rather than from build_sequence.

    Two players driven at different rates must see the same prompt at the same face
    number -- that is what makes an asynchronous race fair.
    """
    with blitz_client(tmp_path, processor="test-hit", blitz_face_seconds=60) as client:
        host = create_room(client)
        guest = join_room(client, host["room_id"], "guest")
        start_blitz(client, host["room_id"], host)

        seen: dict[str, dict[int, tuple[str, str]]] = {"host": {}, "guest": {}}

        def record(state):
            for name, player in (("host", host), ("guest", guest)):
                run = run_of(state, player)
                seen[name][run["face_no"]] = (run["prompt"], run["target"])

        record(state_of(client, host["room_id"]))
        for _ in range(4):
            record(push_faces(client, host["room_id"], host, TINY_JPEG, 1))
        # Now walk the guest through the same faces, well behind the host.
        for _ in range(4):
            record(push_faces(client, host["room_id"], guest, TINY_JPEG, 1))

        shared = set(seen["host"]) & set(seen["guest"])
        assert len(shared) >= 4
        for face_no in sorted(shared):
            assert seen["host"][face_no] == seen["guest"][face_no], f"face {face_no} differed"


def test_the_sequence_never_reaches_the_client(tmp_path):
    """A client holding the order could pre-make the next face. It stays server-side."""
    with blitz_client(tmp_path, processor="test-hit") as client:
        host = create_room(client)
        state = start_blitz(client, host["room_id"], host)
        # Named exactly, so adding a field to BlitzState is a decision rather than a
        # drift: the one thing that must never appear here is the sequence itself.
        assert set(state["blitz"]) == {"sequence_length", "runs", "highlights"}
        # The real check, rather than a substring hunt (`sequence_length` would match
        # one): the only prompts on the wire are the ones players are looking at now.
        on_the_wire = {p.text for p in PROMPTS if p.text in json.dumps(state)}
        current = {r["prompt"] for r in state["blitz"]["runs"].values()}
        assert on_the_wire == current, "a prompt nobody is on leaked into the snapshot"
        assert state["blitz"]["sequence_length"] >= 60
        run = run_of(state, host)
        assert "next_prompt" not in run and "next_target" not in run
        # The per-face breakdown and the hall of fame are published once, at game over.
        assert run["faces"] == []
        assert state["blitz"]["highlights"] == []


def test_a_mid_blitz_joiner_gets_a_run_at_the_first_face(tmp_path):
    with blitz_client(tmp_path, processor="test-hit") as client:
        host = create_room(client)
        start_blitz(client, host["room_id"], host)
        push_faces(client, host["room_id"], host, TINY_JPEG, 2)

        guest = join_room(client, host["room_id"], "latecomer")
        state = wait_for(
            client,
            host["room_id"],
            lambda s: guest["player_id"] in s["blitz"]["runs"],
        )
        assert run_of(state, guest)["face_no"] == 1


def test_the_clock_ends_the_blitz_and_keeps_the_points(tmp_path):
    with blitz_client(tmp_path, processor="test-hit", blitz_seconds=4) as client:
        host = create_room(client)
        start_blitz(client, host["room_id"], host)
        push_faces(client, host["room_id"], host, TINY_JPEG, 1)

        # Shorten the wait: the driver ends the game off `game_ends_at`.
        state = wait_for(
            client, host["room_id"], lambda s: s["phase"] == "game_over", timeout=15.0
        )
        assert state["players"][host["player_id"]]["points"] == 200
        # The breakdown lands exactly once, now.
        faces = run_of(state, host)["faces"]
        assert faces and faces[0]["outcome"] == "passed"
        assert faces[0]["points"] == 200
