import time

from tests.conftest import create_room, frame_files, join_room, wait_for


def test_create_and_join_shares_one_authoritative_state(client):
    host = create_room(client, "alice")
    guest = join_room(client, host["room_id"], "bob")

    assert guest["room_id"] == host["room_id"]
    state = client.get(f"/api/rooms/{host['room_id']}").json()
    assert set(state["players"]) == {host["player_id"], guest["player_id"]}
    assert state["phase"] == "lobby"
    assert state["host_id"] == host["player_id"]


def test_join_by_code(client):
    host = create_room(client)
    guest = join_room(client, host["join_code"], "bob")
    assert guest["room_id"] == host["room_id"]


def test_only_host_can_start(client):
    host = create_room(client)
    guest = join_room(client, host["room_id"], "bob")

    denied = client.post(
        f"/api/rooms/{host['room_id']}/start", params={"player_id": guest["player_id"]}
    )
    assert denied.status_code == 403

    ok = client.post(
        f"/api/rooms/{host['room_id']}/start", params={"player_id": host["player_id"]}
    )
    assert ok.status_code == 202


def test_websocket_receives_snapshots_with_increasing_seq(client):
    host = create_room(client, "alice")
    room_id = host["room_id"]

    with client.websocket_connect(
        f"/ws/rooms/{room_id}?player_id={host['player_id']}"
    ) as socket:
        first = socket.receive_json()
        assert first["type"] == "state"
        assert first["state"]["phase"] == "lobby"

        join_room(client, room_id, "bob")

        seqs, phases, kinds = [first["seq"]], set(), set()
        deadline = time.time() + 10
        while time.time() < deadline:
            msg = socket.receive_json()
            if msg["type"] == "state":
                seqs.append(msg["seq"])
                phases.add(msg["state"]["phase"])
            else:
                kinds.add(msg["kind"])
            if "player_joined" in kinds and len(seqs) > 2:
                break

        assert "player_joined" in kinds
        assert seqs == sorted(seqs), "snapshot seq must be monotonic"
        assert len(set(seqs)) == len(seqs), "seq must be unique per snapshot"


def test_full_round_scores_every_player(client, jpeg):
    """End to end with the real dummy processor: every frame gets judged against the
    round's target. Whether the verdict is *correct* is the dummy's business -- the
    deterministic point arithmetic lives in test_scoring.py."""
    host = create_room(client, "alice")
    guest = join_room(client, host["room_id"], "bob")
    room_id = host["room_id"]

    client.post(f"/api/rooms/{room_id}/start", params={"player_id": host["player_id"]})

    # The round driver flips to ROUND asynchronously; wait for the server to say so.
    deadline = time.time() + 5
    while time.time() < deadline:
        state = client.get(f"/api/rooms/{room_id}").json()
        if state["phase"] == "round":
            break
    assert state["phase"] == "round"
    assert state["round"]["prompt"]

    for player in (host, guest):
        res = client.post(
            f"/api/rooms/{room_id}/frames",
            data={"player_id": player["player_id"]},
            files=frame_files(jpeg),
        )
        assert res.status_code == 202, res.text
        assert res.json()["skipped"] is False

    # Workers process off the request path, so poll until both submissions settle.
    deadline = time.time() + 5
    while time.time() < deadline:
        state = client.get(f"/api/rooms/{room_id}").json()
        subs = state.get("round", {}).get("submissions", {}) if state.get("round") else {}
        if len(subs) == 2 and all(s["status"] == "done" for s in subs.values()):
            break
    assert len(subs) == 2
    target = state["round"]["target"]
    for sub in subs.values():
        assert sub["status"] == "done"
        assert sub["result"]["label"]
        assert sub["result"]["meta"]["processor"] == "dummy"
        assert sub["correct"] is (sub["result"]["label"] == target)

    # Points are committed when the server ends the round, not when a frame is scored.
    state = wait_for(client, room_id, lambda s: s["phase"] == "game_over", timeout=15)
    for player in state["players"].values():
        # Only a pass scores, and a round is worth at most 200.
        assert (player["points"] > 0) == (player["rounds_correct"] > 0)
        assert player["points"] <= 200 * player["rounds_correct"]


def test_game_reaches_game_over(client):
    host = create_room(client)
    room_id = host["room_id"]
    client.post(f"/api/rooms/{room_id}/start", params={"player_id": host["player_id"]})

    # 2 rounds x 2s with no intermission (see the settings fixture).
    deadline = time.time() + 15
    while time.time() < deadline:
        state = client.get(f"/api/rooms/{room_id}").json()
        if state["phase"] == "game_over":
            break
    assert state["phase"] == "game_over"


def test_stored_frame_is_retrievable(client, jpeg):
    host = create_room(client)
    room_id = host["room_id"]
    client.post(f"/api/rooms/{room_id}/start", params={"player_id": host["player_id"]})

    deadline = time.time() + 5
    while time.time() < deadline:
        if client.get(f"/api/rooms/{room_id}").json()["phase"] == "round":
            break

    res = client.post(
        f"/api/rooms/{room_id}/frames",
        data={"player_id": host["player_id"]},
        files=frame_files(jpeg),
    )
    submission_id = res.json()["submission_id"]

    media = client.get(f"/api/media/{submission_id}")
    assert media.status_code == 200
    assert media.headers["content-type"] == "image/jpeg"
    assert media.content == jpeg
