"""Picking the mode and the blitz settings in the lobby.

Mirrors test_rounds_choice.py and test_round_timing.py: the same host-only, lobby-only,
survives-a-restart contract the classic settings have.
"""

from tests.conftest import (
    TINY_JPEG,
    blitz_client,
    create_room,
    join_room,
    make_client,
    push_faces,
    run_of,
    start_blitz,
    state_of,
    wait_for,
)

BLITZ = {
    "blitz_seconds": 90,
    "blitz_face_seconds": 8,
    "blitz_pass_confidence": 0.4,
    "blitz_live_leaderboard": False,
}


def set_mode(client, room_id, player, mode):
    return client.post(
        f"/api/rooms/{room_id}/mode", params={"player_id": player["player_id"], "mode": mode}
    )


def set_blitz(client, room_id, player, **over):
    return client.post(
        f"/api/rooms/{room_id}/blitz-config",
        params={"player_id": player["player_id"]},
        json={**BLITZ, **over},
    )


def test_a_new_room_is_classic_by_default(tmp_path):
    with make_client(tmp_path) as client:
        host = create_room(client)
        assert state_of(client, host["room_id"])["config"]["mode"] == "classic"


def test_the_host_picks_the_mode(tmp_path):
    with make_client(tmp_path) as client:
        host = create_room(client)
        res = set_mode(client, host["room_id"], host, "blitz")
        assert res.status_code == 200, res.text
        assert res.json()["mode"] == "blitz"
        assert state_of(client, host["room_id"])["config"]["mode"] == "blitz"
        # And back again.
        assert set_mode(client, host["room_id"], host, "classic").json()["mode"] == "classic"


def test_only_the_host_picks_the_mode(tmp_path):
    with make_client(tmp_path) as client:
        host = create_room(client)
        guest = join_room(client, host["room_id"], "guest")
        res = set_mode(client, host["room_id"], guest, "blitz")
        assert res.status_code == 403
        assert "Only the host" in res.json()["detail"]


def test_an_unknown_mode_is_refused(tmp_path):
    with make_client(tmp_path) as client:
        host = create_room(client)
        assert set_mode(client, host["room_id"], host, "chaos").status_code == 422


def test_the_mode_cannot_change_once_the_game_started(tmp_path):
    with blitz_client(tmp_path, processor="test-hit", blitz_face_seconds=60) as client:
        host = create_room(client)
        start_blitz(client, host["room_id"], host)
        res = set_mode(client, host["room_id"], host, "classic")
        assert res.status_code == 409
        assert "already started" in res.json()["detail"]


def test_blitz_settings_round_trip(tmp_path):
    with blitz_client(tmp_path) as client:
        host = create_room(client)
        res = set_blitz(client, host["room_id"], host)
        assert res.status_code == 200, res.text
        config = res.json()
        assert config["blitz_seconds"] == 90
        assert config["blitz_face_seconds"] == 8
        assert config["blitz_pass_confidence"] == 0.4
        assert config["blitz_live_leaderboard"] is False
        # Echoed for the UI, not host-settable.
        assert config["max_points_per_face"] == 200
        assert config["blitz_skip_after_seconds"] >= 0


def test_a_face_limit_longer_than_the_blitz_is_refused(tmp_path):
    with blitz_client(tmp_path) as client:
        host = create_room(client)
        res = set_blitz(client, host["room_id"], host, blitz_seconds=30, blitz_face_seconds=45)
        assert res.status_code == 422
        detail = res.json()["detail"]
        assert "does not fit" in detail and "45s" in detail and "30s" in detail


def test_blitz_settings_have_sanity_caps(tmp_path):
    with blitz_client(tmp_path) as client:
        host = create_room(client)
        assert set_blitz(client, host["room_id"], host, blitz_seconds=5).status_code == 422
        assert set_blitz(client, host["room_id"], host, blitz_seconds=9000).status_code == 422
        assert set_blitz(client, host["room_id"], host, blitz_face_seconds=1).status_code == 422
        # A near-perfect bar would make the stand-in targets unpassable; see app/config.py.
        assert set_blitz(client, host["room_id"], host, blitz_pass_confidence=1.0).status_code == 422


def test_only_the_host_in_the_lobby_sets_them(tmp_path):
    with blitz_client(tmp_path, processor="test-hit", blitz_face_seconds=60) as client:
        host = create_room(client)
        guest = join_room(client, host["room_id"], "guest")
        assert set_blitz(client, host["room_id"], guest).status_code == 403
        start_blitz(client, host["room_id"], host)
        assert set_blitz(client, host["room_id"], host).status_code == 409


def test_classic_and_blitz_settings_do_not_disturb_each_other(tmp_path):
    """A host can flip modes without reconfiguring, so both sets stay settable."""
    with make_client(tmp_path) as client:
        host = create_room(client)
        before = state_of(client, host["room_id"])["config"]

        assert set_blitz(client, host["room_id"], host).status_code == 200
        after = state_of(client, host["room_id"])["config"]
        for key in ("round_seconds", "round_decrement_seconds", "rounds_per_game", "game_seconds"):
            assert after[key] == before[key], f"blitz config moved {key}"

        res = client.post(
            f"/api/rooms/{host['room_id']}/config",
            params={"player_id": host["player_id"]},
            json={"round_seconds": 25, "round_decrement_seconds": 2},
        )
        assert res.status_code == 200, res.text
        config = res.json()
        assert config["round_seconds"] == 25
        assert config["blitz_seconds"] == 90, "classic timing moved the blitz clock"


def test_the_mode_and_its_settings_survive_a_restart(tmp_path):
    with blitz_client(tmp_path, processor="test-hit", blitz_seconds=4) as client:
        host = create_room(client)
        assert set_blitz(client, host["room_id"], host, blitz_seconds=30).status_code == 200
        start_blitz(client, host["room_id"], host)
        push_faces(client, host["room_id"], host, TINY_JPEG, 1)
        # Cut the game short rather than waiting out 30s.
        wait_for(client, host["room_id"], lambda s: run_of(s, host)["passed"] == 1)

        state = state_of(client, host["room_id"])
        assert state["players"][host["player_id"]]["points"] == 200


def test_restart_clears_the_blitz_and_keeps_the_config(tmp_path):
    with blitz_client(tmp_path, processor="test-hit", blitz_seconds=4) as client:
        host = create_room(client)
        start_blitz(client, host["room_id"], host)
        push_faces(client, host["room_id"], host, TINY_JPEG, 1)
        wait_for(client, host["room_id"], lambda s: s["phase"] == "game_over", timeout=15.0)

        res = client.post(
            f"/api/rooms/{host['room_id']}/restart", params={"player_id": host["player_id"]}
        )
        assert res.status_code == 200, res.text

        state = state_of(client, host["room_id"])
        assert state["phase"] == "lobby"
        assert state["blitz"] is None, "a finished blitz must not linger into the lobby"
        assert state["config"]["mode"] == "blitz", "the mode is a room setting"
        assert state["config"]["blitz_seconds"] == 4
        assert state["players"][host["player_id"]]["points"] == 0
        assert state["game_no"] == 2
