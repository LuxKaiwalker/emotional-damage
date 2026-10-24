"""The game timer. Rounds have their own deadline; the game timer is the hard cap."""

from datetime import datetime

from tests.conftest import create_room, make_client, state_of, wait_for


def _at(iso: str) -> datetime:
    return datetime.fromisoformat(iso)


def test_starting_a_game_publishes_its_deadline(tmp_path):
    with make_client(tmp_path, game_seconds=30) as client:
        host = create_room(client, "alice")
        room_id = host["room_id"]

        lobby = state_of(client, room_id)
        assert lobby["game_started_at"] is None and lobby["game_ends_at"] is None
        assert lobby["config"]["game_seconds"] == 30

        client.post(f"/api/rooms/{room_id}/start", params={"player_id": host["player_id"]})
        state = wait_for(client, room_id, lambda s: s["game_ends_at"] is not None)

        span = _at(state["game_ends_at"]) - _at(state["game_started_at"])
        assert span.total_seconds() == 30


def test_the_game_timer_ends_the_game_early(tmp_path):
    """Ten rounds of two seconds would run for twenty; a three second game cannot.

    The game stops once too little time is left to be worth another round, so it can
    finish a little before its own deadline -- never after it.
    """
    with make_client(
        tmp_path, rounds_per_game=10, round_seconds=2, intermission_seconds=0, game_seconds=3
    ) as client:
        host = create_room(client, "alice")
        room_id = host["room_id"]
        client.post(f"/api/rooms/{room_id}/start", params={"player_id": host["player_id"]})

        state = wait_for(client, room_id, lambda s: s["phase"] == "game_over", timeout=10)
        assert state["round"]["number"] < 10, "the game timer, not the round count, ended it"
        unused = (_at(state["game_ends_at"]) - _at(state["server_time"])).total_seconds()
        assert unused < 2, f"{unused:.1f}s left over: that was room for another round"


def test_a_round_is_truncated_rather_than_overrunning_the_game(tmp_path):
    """A 20s round inside a 3s game ends when the game does, not 17s later."""
    with make_client(tmp_path, rounds_per_game=5, round_seconds=20, game_seconds=3) as client:
        host = create_room(client, "alice")
        room_id = host["room_id"]
        client.post(f"/api/rooms/{room_id}/start", params={"player_id": host["player_id"]})

        state = wait_for(client, room_id, lambda s: s["phase"] == "round")
        round_ends = _at(state["round"]["ends_at"])
        assert round_ends <= _at(state["game_ends_at"])
        # The client anchors its countdown to ends_at, so a truncated round must say so.
        assert (round_ends - _at(state["round"]["started_at"])).total_seconds() <= 3


def test_the_game_ends_on_the_round_count_when_time_is_ample(tmp_path):
    with make_client(
        tmp_path, rounds_per_game=2, round_seconds=1, intermission_seconds=0, game_seconds=60
    ) as client:
        host = create_room(client, "alice")
        room_id = host["room_id"]
        client.post(f"/api/rooms/{room_id}/start", params={"player_id": host["player_id"]})

        state = wait_for(client, room_id, lambda s: s["phase"] == "game_over", timeout=10)
        assert state["round"]["number"] == 2
        assert _at(state["server_time"]) < _at(state["game_ends_at"])


def test_game_over_says_why_the_game_ended(tmp_path):
    with make_client(
        tmp_path, rounds_per_game=10, round_seconds=1, intermission_seconds=0, game_seconds=2
    ) as client:
        host = create_room(client, "alice")
        room_id = host["room_id"]

        with client.websocket_connect(
            f"/ws/rooms/{room_id}?player_id={host['player_id']}"
        ) as socket:
            client.post(f"/api/rooms/{room_id}/start", params={"player_id": host["player_id"]})
            payload = None
            while payload is None:
                msg = socket.receive_json()
                if msg["type"] == "event" and msg["kind"] == "game_over":
                    payload = msg["payload"]

        assert payload["reason"] == "time_up"
        assert payload["game_no"] == 1


def test_frames_are_refused_once_the_game_timer_is_up(tmp_path, jpeg):
    from tests.conftest import frame_files

    with make_client(tmp_path, rounds_per_game=10, round_seconds=1, game_seconds=2) as client:
        host = create_room(client, "alice")
        room_id = host["room_id"]
        client.post(f"/api/rooms/{room_id}/start", params={"player_id": host["player_id"]})
        wait_for(client, room_id, lambda s: s["phase"] == "game_over", timeout=10)

        res = client.post(
            f"/api/rooms/{room_id}/frames",
            data={"player_id": host["player_id"]},
            files=frame_files(jpeg),
        )
        assert res.status_code == 409
