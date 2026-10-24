"""Restarting a room: same players, same join code, clean slate."""

from tests.conftest import create_room, join_room, make_client, play_one_round, state_of, wait_for


def _finished_game(client, jpeg, players):
    """Play a game to game_over and return the final state."""
    room_id = players[0]["room_id"]
    play_one_round(client, room_id, players, jpeg)
    return wait_for(client, room_id, lambda s: s["phase"] == "game_over")


def test_restart_clears_the_scores_and_returns_to_the_lobby(hit_client, jpeg):
    host = create_room(hit_client, "alice")
    room_id = host["room_id"]
    state = _finished_game(hit_client, jpeg, [host])
    assert state["players"][host["player_id"]]["points"] > 0

    res = hit_client.post(
        f"/api/rooms/{room_id}/restart", params={"player_id": host["player_id"]}
    )
    assert res.status_code == 200
    assert res.json() == {"status": "lobby"}

    state = state_of(hit_client, room_id)
    assert state["phase"] == "lobby"
    assert state["round"] is None
    assert state["game_no"] == 2
    assert state["game_started_at"] is None and state["game_ends_at"] is None
    assert all(p["points"] == 0 for p in state["players"].values())
    assert all(p["rounds_correct"] == 0 for p in state["players"].values())


def test_game_over_keeps_every_played_round_and_restart_clears_them(hit_client, jpeg):
    """The deep scan lists the rounds that were actually played, in order."""
    host = create_room(hit_client, "alice")
    room_id = host["room_id"]
    state = _finished_game(hit_client, jpeg, [host])

    history = state["history"]
    assert [r["number"] for r in history] == [1, 2]
    assert history[-1]["prompt"] == state["round"]["prompt"]
    assert len({r["prompt"] for r in history}) == len(history), "no prompt twice in a game"
    assert history[0]["submissions"][host["player_id"]]["correct"] is True
    assert history[0]["points_awarded"] == {host["player_id"]: 1}

    hit_client.post(f"/api/rooms/{room_id}/restart", params={"player_id": host["player_id"]})
    assert state_of(hit_client, room_id)["history"] == []


def test_the_room_keeps_its_identity_across_a_restart(hit_client, jpeg):
    """Same room id and join code: the players in the room do not have to do anything."""
    host = create_room(hit_client, "alice")
    guest = join_room(hit_client, host["room_id"], "bob")
    _finished_game(hit_client, jpeg, [host, guest])

    hit_client.post(
        f"/api/rooms/{host['room_id']}/restart", params={"player_id": host["player_id"]}
    )
    state = state_of(hit_client, host["join_code"])
    assert state["room_id"] == host["room_id"]
    assert state["join_code"] == host["join_code"]
    assert set(state["players"]) == {host["player_id"], guest["player_id"]}


def test_a_restarted_room_can_play_another_full_game(hit_client, jpeg):
    host = create_room(hit_client, "alice")
    room_id = host["room_id"]
    _finished_game(hit_client, jpeg, [host])
    hit_client.post(f"/api/rooms/{room_id}/restart", params={"player_id": host["player_id"]})

    state = _finished_game(hit_client, jpeg, [host])
    assert state["phase"] == "game_over"
    assert state["game_no"] == 2
    assert state["players"][host["player_id"]]["points"] > 0


def test_a_player_who_joined_between_games_plays_the_next_one(hit_client, jpeg):
    host = create_room(hit_client, "alice")
    room_id = host["room_id"]
    _finished_game(hit_client, jpeg, [host])
    hit_client.post(f"/api/rooms/{room_id}/restart", params={"player_id": host["player_id"]})

    latecomer = join_room(hit_client, room_id, "bob")
    state = _finished_game(hit_client, jpeg, [host, latecomer])
    assert state["players"][latecomer["player_id"]]["points"] > 0


def test_restart_is_refused_while_a_game_is_still_on(client):
    host = create_room(client, "alice")
    room_id = host["room_id"]

    denied = client.post(f"/api/rooms/{room_id}/restart", params={"player_id": host["player_id"]})
    assert denied.status_code == 409, "nothing to restart from the lobby"

    client.post(f"/api/rooms/{room_id}/start", params={"player_id": host["player_id"]})
    wait_for(client, room_id, lambda s: s["phase"] == "round")
    denied = client.post(f"/api/rooms/{room_id}/restart", params={"player_id": host["player_id"]})
    assert denied.status_code == 409


def test_only_the_host_can_restart(hit_client, jpeg):
    host = create_room(hit_client, "alice")
    guest = join_room(hit_client, host["room_id"], "bob")
    _finished_game(hit_client, jpeg, [host, guest])

    denied = hit_client.post(
        f"/api/rooms/{host['room_id']}/restart", params={"player_id": guest["player_id"]}
    )
    assert denied.status_code == 403


def test_starting_twice_without_a_restart_is_refused(tmp_path):
    """`game_over` is a terminal phase: the way back in is /restart, not /start."""
    with make_client(tmp_path, rounds_per_game=1, round_seconds=1) as client:
        host = create_room(client, "alice")
        room_id = host["room_id"]
        client.post(f"/api/rooms/{room_id}/start", params={"player_id": host["player_id"]})
        wait_for(client, room_id, lambda s: s["phase"] == "game_over")

        denied = client.post(f"/api/rooms/{room_id}/start", params={"player_id": host["player_id"]})
        assert denied.status_code == 409
