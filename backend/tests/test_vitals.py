"""Client-reported vitals: stored, broadcast, and deliberately never scored.

The last property is the point of these tests. Vitals are produced in the player's own
browser from their own camera, so the server cannot verify them; if they ever started
paying out points, the leaderboard would be forgeable by anyone willing to edit a
websocket frame. `test_vitals_never_affect_scoring` is what stops that becoming true by
accident later.
"""

import time

from tests.conftest import (
    create_room,
    join_room,
    make_client,
    play_one_round,
    state_of,
    wait_for,
)


def report(client, room_id: str, player_id: str, metrics: dict):
    return client.post(
        f"/api/rooms/{room_id}/vitals", json={"player_id": player_id, "metrics": metrics}
    )


def test_vitals_are_recorded_on_the_player(client):
    host = create_room(client, "alice")
    room_id = host["room_id"]

    res = report(client, room_id, host["player_id"], {"pulse": 112.0, "breathing": 24.0})
    assert res.status_code == 202, res.text
    assert res.json() == {"status": "recorded", "scored": False}

    player = state_of(client, room_id)["players"][host["player_id"]]
    assert player["vitals"] == {"pulse": 112.0, "breathing": 24.0}
    assert player["vitals_at"] is not None


def test_vitals_are_broadcast_to_the_whole_room(client):
    """Everyone sees everyone's read: that is the only reason the endpoint exists."""
    host = create_room(client, "alice")
    room_id = host["room_id"]
    guest = join_room(client, room_id, "bob")

    with client.websocket_connect(
        f"/ws/rooms/{room_id}?player_id={host['player_id']}"
    ) as socket:
        socket.receive_json()  # opening snapshot
        report(client, room_id, guest["player_id"], {"pulse": 99.0})

        deadline = time.time() + 10
        while time.time() < deadline:
            msg = socket.receive_json()
            if msg["type"] != "state":
                continue
            vitals = msg["state"]["players"][guest["player_id"]]["vitals"]
            if vitals == {"pulse": 99.0}:
                return
        raise AssertionError("guest's vitals never reached the host's socket")


def test_vitals_replace_the_previous_sample(client):
    """Latest read wins; samples are a current value, not a history."""
    host = create_room(client, "alice")
    room_id = host["room_id"]

    report(client, room_id, host["player_id"], {"pulse": 80.0})
    report(client, room_id, host["player_id"], {"pulse": 140.0})

    player = state_of(client, room_id)["players"][host["player_id"]]
    assert player["vitals"] == {"pulse": 140.0}


def test_vitals_never_affect_scoring(tmp_path, jpeg):
    """A player with perfect vitals and a wrong face still scores nothing.

    `test-miss` never returns a real label, so the only thing that could possibly award a
    point here is the vitals report. Nothing does.
    """
    with make_client(tmp_path, processor="test-miss", rounds_per_game=1) as client:
        host = create_room(client, "alice")
        room_id = host["room_id"]

        state = play_one_round(client, room_id, [host], jpeg)
        assert state["round"]["submissions"][host["player_id"]]["correct"] is False

        # Pile on vitals while the round is live and after it has been committed.
        report(client, room_id, host["player_id"], {"pulse": 180.0, "breathing": 40.0})
        final = wait_for(client, room_id, lambda s: s["phase"] == "game_over")
        report(client, room_id, host["player_id"], {"pulse": 190.0})

        player = state_of(client, room_id)["players"][host["player_id"]]
        assert player["points"] == 0
        assert player["rounds_correct"] == 0
        assert final["players"][host["player_id"]]["points"] == 0
        # Still recorded, just not worth anything.
        assert player["vitals"] == {"pulse": 190.0}


def test_vitals_for_unknown_player_is_404(client):
    host = create_room(client, "alice")
    res = report(client, host["room_id"], "p_nobody", {"pulse": 100.0})
    assert res.status_code == 404


def test_vitals_for_unknown_room_is_404(client):
    res = report(client, "r_nope", "p_nobody", {"pulse": 100.0})
    assert res.status_code == 404


def test_oversized_vitals_report_is_rejected(tmp_path):
    """Untrusted input that lands in every snapshot has to stay bounded."""
    with make_client(tmp_path, max_vitals_fields=3) as client:
        host = create_room(client, "alice")
        res = report(
            client,
            host["room_id"],
            host["player_id"],
            {f"m{i}": float(i) for i in range(4)},
        )
        assert res.status_code == 413

        ok = report(client, host["room_id"], host["player_id"], {"a": 1.0, "b": 2.0})
        assert ok.status_code == 202


def test_non_numeric_vitals_are_rejected(client):
    """Flat numbers only: nested vendor payloads would grow the snapshot without bound."""
    host = create_room(client, "alice")
    res = report(
        client, host["room_id"], host["player_id"], {"pulse": {"nested": "object"}}
    )
    assert res.status_code == 422


def test_vitals_can_be_switched_off(tmp_path):
    with make_client(tmp_path, vitals_enabled=False) as client:
        host = create_room(client, "alice")
        res = report(client, host["room_id"], host["player_id"], {"pulse": 100.0})
        assert res.status_code == 503


def test_players_start_with_no_vitals(client):
    host = create_room(client, "alice")
    player = state_of(client, host["room_id"])["players"][host["player_id"]]
    assert player["vitals"] is None
    assert player["vitals_at"] is None
