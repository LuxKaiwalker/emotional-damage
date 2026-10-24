"""Host-set round timing: round 1's length, and how much shorter each later round gets."""

from datetime import datetime

from tests.conftest import create_room, join_room, make_client, state_of, wait_for


def _at(iso: str) -> datetime:
    return datetime.fromisoformat(iso)


def _set_timing(client, room_id: str, player_id: str, start: int, decrement: int):
    return client.post(
        f"/api/rooms/{room_id}/config",
        params={"player_id": player_id},
        json={"round_seconds": start, "round_decrement_seconds": decrement},
    )


def _round_span(state: dict) -> float:
    rnd = state["round"]
    return (_at(rnd["ends_at"]) - _at(rnd["started_at"])).total_seconds()


def test_a_new_room_starts_from_the_server_defaults(tmp_path):
    with make_client(tmp_path, round_seconds=20, round_decrement_seconds=2) as client:
        host = create_room(client, "alice")
        config = state_of(client, host["room_id"])["config"]
        assert config["round_seconds"] == 20
        assert config["round_decrement_seconds"] == 2


def test_the_host_sets_the_timing_and_everyone_sees_it(client):
    host = create_room(client, "alice")
    room_id = host["room_id"]

    res = _set_timing(client, room_id, host["player_id"], 10, 3)
    assert res.status_code == 200, res.text
    assert res.json()["round_seconds"] == 10
    assert res.json()["round_decrement_seconds"] == 3

    config = state_of(client, room_id)["config"]
    assert (config["round_seconds"], config["round_decrement_seconds"]) == (10, 3)


def test_each_round_is_shorter_by_the_decrement(tmp_path):
    with make_client(
        tmp_path, rounds_per_game=3, intermission_seconds=0, game_seconds=60
    ) as client:
        host = create_room(client, "alice")
        room_id = host["room_id"]
        assert _set_timing(client, room_id, host["player_id"], 5, 1).status_code == 200

        client.post(f"/api/rooms/{room_id}/start", params={"player_id": host["player_id"]})
        spans = {}
        for n in (1, 2, 3):
            state = wait_for(
                client, room_id,
                lambda s, n=n: s["phase"] == "round" and s["round"]["number"] == n,
                timeout=15,
            )
            spans[n] = _round_span(state)

        assert abs(spans[1] - 5) < 0.2
        assert abs(spans[2] - 4) < 0.2
        assert abs(spans[3] - 3) < 0.2


def test_only_the_host_can_change_the_timing(client):
    host = create_room(client, "alice")
    guest = join_room(client, host["room_id"], "bob")

    res = _set_timing(client, host["room_id"], guest["player_id"], 10, 0)
    assert res.status_code == 403
    assert state_of(client, host["room_id"])["config"]["round_seconds"] == 2


def test_the_timing_is_locked_once_the_game_starts(client):
    host = create_room(client, "alice")
    room_id = host["room_id"]
    client.post(f"/api/rooms/{room_id}/start", params={"player_id": host["player_id"]})
    wait_for(client, room_id, lambda s: s["phase"] == "round")

    assert _set_timing(client, room_id, host["player_id"], 10, 0).status_code == 409


def test_a_decrement_that_starves_the_last_round_is_refused(tmp_path):
    """10s, 5s, 0s: the third round would not exist."""
    with make_client(tmp_path, rounds_per_game=3, game_seconds=60) as client:
        host = create_room(client, "alice")
        res = _set_timing(client, host["room_id"], host["player_id"], 10, 5)
        assert res.status_code == 422
        assert "round 3" in res.json()["detail"]
        assert state_of(client, host["room_id"])["config"]["round_seconds"] == 2


def test_the_game_timer_grows_to_fit_a_longer_schedule(tmp_path):
    """Three 30s rounds plus two 4s breaks is 98s; a 60s cap would cut the game short."""
    with make_client(
        tmp_path, rounds_per_game=3, intermission_seconds=4, game_seconds=60
    ) as client:
        host = create_room(client, "alice")
        res = _set_timing(client, host["room_id"], host["player_id"], 30, 0)
        assert res.status_code == 200, res.text
        assert res.json()["game_seconds"] >= 98


def test_the_game_timer_never_shrinks_below_the_server_floor(tmp_path):
    with make_client(tmp_path, rounds_per_game=3, game_seconds=60) as client:
        host = create_room(client, "alice")
        res = _set_timing(client, host["room_id"], host["player_id"], 3, 0)
        assert res.json()["game_seconds"] == 60


def test_picking_more_rounds_cannot_starve_the_last_one(tmp_path):
    """20s shrinking by 2s is fine over five rounds, but round ten would be 2s."""
    with make_client(tmp_path, round_seconds=20, rounds_per_game=5, game_seconds=60) as client:
        host = create_room(client, "alice")
        room_id = host["room_id"]
        assert _set_timing(client, room_id, host["player_id"], 20, 2).status_code == 200

        res = client.post(
            f"/api/rooms/{room_id}/rounds", params={"player_id": host["player_id"], "rounds": 10}
        )
        assert res.status_code == 422
        assert "round 10" in res.json()["detail"]
        assert state_of(client, room_id)["config"]["rounds_per_game"] == 5


def test_the_timing_survives_a_restart(tmp_path):
    with make_client(
        tmp_path, rounds_per_game=1, intermission_seconds=0, game_seconds=60
    ) as client:
        host = create_room(client, "alice")
        room_id = host["room_id"]
        assert _set_timing(client, room_id, host["player_id"], 3, 0).status_code == 200

        client.post(f"/api/rooms/{room_id}/start", params={"player_id": host["player_id"]})
        wait_for(client, room_id, lambda s: s["phase"] == "game_over", timeout=10)
        client.post(f"/api/rooms/{room_id}/restart", params={"player_id": host["player_id"]})

        assert state_of(client, room_id)["config"]["round_seconds"] == 3
