"""The host picks 5 or 10 rounds in the lobby, and the game plays exactly that many."""

from datetime import datetime

from tests.conftest import create_room, join_room, make_client, state_of, wait_for


def _set(client, room_id, player_id, rounds):
    return client.post(
        f"/api/rooms/{room_id}/rounds", params={"player_id": player_id, "rounds": rounds}
    )


def test_the_picked_round_count_is_played_in_full(tmp_path):
    # A 3s cap could not fit five rounds: the pick has to stretch the game timer.
    with make_client(tmp_path, round_seconds=1, intermission_seconds=0, game_seconds=3) as client:
        host = create_room(client, "alice")
        room_id = host["room_id"]
        assert _set(client, room_id, host["player_id"], 5).status_code == 200

        config = state_of(client, room_id)["config"]
        assert config["rounds_per_game"] == 5
        assert config["game_seconds"] >= 5

        client.post(f"/api/rooms/{room_id}/start", params={"player_id": host["player_id"]})
        state = wait_for(client, room_id, lambda s: s["phase"] == "game_over", timeout=20)
        assert [r["number"] for r in state["history"]] == [1, 2, 3, 4, 5]
        span = datetime.fromisoformat(state["game_ends_at"]) - datetime.fromisoformat(
            state["game_started_at"]
        )
        assert span.total_seconds() == config["game_seconds"]


def test_only_five_or_ten(tmp_path):
    with make_client(tmp_path) as client:
        host = create_room(client, "alice")
        assert _set(client, host["room_id"], host["player_id"], 7).status_code == 422
        assert _set(client, host["room_id"], host["player_id"], 10).status_code == 200
        assert state_of(client, host["room_id"])["config"]["rounds_per_game"] == 10


def test_only_the_host_in_the_lobby(tmp_path):
    with make_client(tmp_path) as client:
        host = create_room(client, "alice")
        guest = join_room(client, host["room_id"], "bob")
        assert _set(client, host["room_id"], guest["player_id"], 10).status_code == 403

        client.post(f"/api/rooms/{host['room_id']}/start", params={"player_id": host["player_id"]})
        assert _set(client, host["room_id"], host["player_id"], 10).status_code == 409
