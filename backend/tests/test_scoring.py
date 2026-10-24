"""The point system: one point per round you got right, and nothing else scores."""

from tests.conftest import (
    create_room,
    frame_files,
    join_room,
    make_client,
    play_one_round,
    wait_for,
)


def test_a_correct_answer_is_worth_exactly_one_point(hit_client, jpeg):
    host = create_room(hit_client, "alice")
    guest = join_room(hit_client, host["room_id"], "bob")
    room_id = host["room_id"]

    state = play_one_round(hit_client, room_id, [host, guest], jpeg)
    assert all(s["correct"] is True for s in state["round"]["submissions"].values())
    # Points are committed by the server at the end of the round, not when a frame scores.
    assert all(p["points"] == 0 for p in state["players"].values())

    state = wait_for(hit_client, room_id, lambda s: s["phase"] != "round")
    for player in state["players"].values():
        assert player["points"] == 1
        assert player["rounds_correct"] == 1


def test_a_wrong_answer_scores_nothing(miss_client, jpeg):
    host = create_room(miss_client, "alice")
    room_id = host["room_id"]

    state = play_one_round(miss_client, room_id, [host], jpeg)
    assert all(s["correct"] is False for s in state["round"]["submissions"].values())

    state = wait_for(miss_client, room_id, lambda s: s["phase"] == "game_over")
    assert all(p["points"] == 0 for p in state["players"].values())
    assert all(p["rounds_correct"] == 0 for p in state["players"].values())


def test_points_accumulate_one_per_correct_round(hit_client, jpeg):
    """Two rounds in the fixture config, so a player who answers both ends on two."""
    host = create_room(hit_client, "alice")
    room_id = host["room_id"]

    hit_client.post(f"/api/rooms/{room_id}/start", params={"player_id": host["player_id"]})
    for round_no in (1, 2):
        wait_for(
            hit_client,
            room_id,
            lambda s, n=round_no: s["phase"] == "round" and s["round"]["number"] == n,
        )
        res = hit_client.post(
            f"/api/rooms/{room_id}/frames",
            data={"player_id": host["player_id"]},
            files=frame_files(jpeg),
        )
        assert res.status_code == 202, res.text
        wait_for(
            hit_client,
            room_id,
            lambda s, n=round_no: s["players"][host["player_id"]]["points"] == n,
        )

    state = wait_for(hit_client, room_id, lambda s: s["phase"] == "game_over")
    assert state["players"][host["player_id"]]["points"] == 2


def test_a_player_who_never_submits_stays_on_zero(hit_client, jpeg):
    host = create_room(hit_client, "alice")
    idle = join_room(hit_client, host["room_id"], "bob")
    room_id = host["room_id"]

    play_one_round(hit_client, room_id, [host], jpeg)
    state = wait_for(hit_client, room_id, lambda s: s["phase"] == "game_over")

    assert state["players"][host["player_id"]]["points"] > 0
    assert state["players"][idle["player_id"]]["points"] == 0


def test_round_records_its_target_and_what_it_awarded(tmp_path, jpeg):
    """One round only, so the committed round is still the one being inspected."""
    with make_client(tmp_path, processor="test-hit", rounds_per_game=1) as client:
        host = create_room(client, "alice")
        room_id = host["room_id"]

        state = play_one_round(client, room_id, [host], jpeg)
        assert state["round"]["target"], "a round must name the label it is asking for"

        state = wait_for(client, room_id, lambda s: s["phase"] == "game_over")
        assert state["round"]["points_awarded"] == {host["player_id"]: 1}


def test_ranking_puts_the_highest_points_first(hit_client, jpeg):
    """Ordering comes out of the game_over event, which is what a scoreboard reads."""
    host = create_room(hit_client, "alice")
    guest = join_room(hit_client, host["room_id"], "bob")
    room_id = host["room_id"]

    with hit_client.websocket_connect(
        f"/ws/rooms/{room_id}?player_id={host['player_id']}"
    ) as socket:
        play_one_round(hit_client, room_id, [guest], jpeg, host=host)

        ranking = None
        while ranking is None:
            msg = socket.receive_json()
            if msg["type"] == "event" and msg["kind"] == "game_over":
                ranking = msg["payload"]["ranking"]

    assert [r["player_id"] for r in ranking] == [guest["player_id"], host["player_id"]]
    assert ranking[0]["points"] > ranking[1]["points"]
