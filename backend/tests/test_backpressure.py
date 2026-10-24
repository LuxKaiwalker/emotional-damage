"""What happens to a frame the server decides not to process.

A dropped frame is normal operation for a live camera, but the engine has already
registered a submission for it -- so every drop has to be settled, or the round ends with
a submission stuck on `pending` and the player silently loses whatever it was worth.
"""

from tests.conftest import create_room, frame_files, join_room, make_client, state_of, wait_for


def _upload(client, room_id: str, player: dict, jpeg: bytes):
    return client.post(
        f"/api/rooms/{room_id}/frames",
        data={"player_id": player["player_id"]},
        files=frame_files(jpeg),
    )


def test_a_frame_evicted_from_a_full_queue_is_settled_not_left_pending(tmp_path, jpeg):
    """One worker, one queue slot, a slow processor: the third frame evicts the second."""
    with make_client(
        tmp_path,
        processor="test-very-slow",
        worker_count=1,
        queue_maxsize=1,
        round_seconds=30,
        rounds_per_game=1,
    ) as client:
        host = create_room(client, "alice")
        second = join_room(client, host["room_id"], "bob")
        third = join_room(client, host["room_id"], "carol")
        room_id = host["room_id"]

        client.post(f"/api/rooms/{room_id}/start", params={"player_id": host["player_id"]})
        wait_for(client, room_id, lambda s: s["phase"] == "round")

        assert _upload(client, room_id, host, jpeg).status_code == 202  # taken by the worker
        assert _upload(client, room_id, second, jpeg).status_code == 202  # sits in the queue
        assert _upload(client, room_id, third, jpeg).status_code == 202  # evicts bob's

        state = wait_for(
            client,
            room_id,
            lambda s: s["round"]["submissions"][second["player_id"]]["status"] != "pending",
            timeout=5,
        )
        evicted = state["round"]["submissions"][second["player_id"]]
        assert evicted["status"] == "failed"
        assert evicted["error"] == "dropped_under_load"
        assert evicted["correct"] is None

        assert client.get("/api/health").json()["frames_dropped"] == 1


def test_an_evicted_frame_costs_its_player_the_round_but_nobody_else(tmp_path, jpeg):
    with make_client(
        tmp_path,
        processor="test-slow",
        worker_count=1,
        queue_maxsize=1,
        # Two surviving frames at one second each, inside a six second round.
        round_seconds=6,
        rounds_per_game=1,
    ) as client:
        host = create_room(client, "alice")
        second = join_room(client, host["room_id"], "bob")
        third = join_room(client, host["room_id"], "carol")
        room_id = host["room_id"]

        client.post(f"/api/rooms/{room_id}/start", params={"player_id": host["player_id"]})
        wait_for(client, room_id, lambda s: s["phase"] == "round")
        for player in (host, second, third):
            assert _upload(client, room_id, player, jpeg).status_code == 202

        state = wait_for(client, room_id, lambda s: s["phase"] == "game_over", timeout=20)
        players = state["players"]
        assert players[second["player_id"]]["points"] == 0, "bob's frame never got processed"
        # The slow processor always answers with the target, so whoever was processed scored.
        assert players[host["player_id"]]["points"] == 1
        assert players[third["player_id"]]["points"] == 1


def test_a_settled_drop_does_not_block_the_next_frame(tmp_path, jpeg):
    """Losing a frame must not take the player out of the round."""
    with make_client(
        tmp_path,
        processor="test-very-slow",
        worker_count=1,
        queue_maxsize=1,
        round_seconds=30,
        rounds_per_game=1,
    ) as client:
        host = create_room(client, "alice")
        second = join_room(client, host["room_id"], "bob")
        third = join_room(client, host["room_id"], "carol")
        room_id = host["room_id"]

        client.post(f"/api/rooms/{room_id}/start", params={"player_id": host["player_id"]})
        wait_for(client, room_id, lambda s: s["phase"] == "round")
        for player in (host, second, third):
            _upload(client, room_id, player, jpeg)

        wait_for(
            client,
            room_id,
            lambda s: s["round"]["submissions"][second["player_id"]]["status"] == "failed",
            timeout=5,
        )
        res = _upload(client, room_id, second, jpeg)
        assert res.status_code == 202
        state = state_of(client, room_id)
        again = state["round"]["submissions"][second["player_id"]]
        assert again["status"] == "pending" and again["error"] is None


def test_a_result_that_lands_after_the_round_is_not_marked_correct(tmp_path, jpeg):
    """The round is already paid out, so a late frame must not show a hit it won't score.

    A one second round against a three second processor puts the result firmly on the
    wrong side of the round boundary -- exactly what a slow real model does to the last
    frame of a round.
    """
    with make_client(
        tmp_path, processor="test-very-slow", round_seconds=1, rounds_per_game=1
    ) as client:
        host = create_room(client, "alice")
        room_id = host["room_id"]

        client.post(f"/api/rooms/{room_id}/start", params={"player_id": host["player_id"]})
        wait_for(client, room_id, lambda s: s["phase"] == "round")
        assert _upload(client, room_id, host, jpeg).status_code == 202

        # The round is over long before the processor is finished with the frame.
        wait_for(client, room_id, lambda s: s["phase"] == "game_over", timeout=10)
        state = wait_for(
            client,
            room_id,
            lambda s: s["round"]["submissions"][host["player_id"]]["status"] == "done",
            timeout=10,
        )
        late = state["round"]["submissions"][host["player_id"]]
        assert late["status"] == "done", "the read itself is still worth showing"
        assert late["result"]["label"] == state["round"]["target"]
        assert late["correct"] is None, "too late to be judged, so it claims nothing"
        assert state["players"][host["player_id"]]["points"] == 0
