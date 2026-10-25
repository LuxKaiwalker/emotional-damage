"""The point system: pass by making the face, then score for speed and accuracy.

A round is worth at most 200 to one player: up to 100 for speed (share of the round left
when the passing frame was captured, times 1.0 / 0.95 / 0.90 ... by place) and up to 100
for accuracy (the processor's confidence). Only a pass scores.
"""

import time
from datetime import datetime, timedelta, timezone

from app.game.engine import pick_highlights, score_round
from app.models import ProcessResult, Round, Submission, SubmissionStatus
from tests.conftest import (
    MarkedProcessor,
    create_room,
    frame_files,
    join_room,
    make_client,
    play_one_round,
    state_of,
    wait_for,
)

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _pass(player_id: str, at_seconds: float, confidence: float) -> Submission:
    return Submission(
        id=f"s_{player_id}",
        player_id=player_id,
        round_no=1,
        received_at=T0 + timedelta(seconds=at_seconds),
        status=SubmissionStatus.DONE,
        result=ProcessResult(score=1.0, label="angry", confidence=confidence),
        correct=True,
    )


def _round(*passes: Submission, seconds: float = 20) -> Round:
    return Round(
        number=1,
        prompt="look angry",
        target="angry",
        started_at=T0,
        ends_at=T0 + timedelta(seconds=seconds),
        passed={p.player_id: p for p in passes},
    )


# --- the rule itself ---------------------------------------------------------


def test_speed_is_time_left_times_place_and_accuracy_is_confidence():
    # Listed out of order on purpose: place comes from capture time, not insertion order.
    scores = score_round(_round(
        _pass("ann", 3, confidence=0.9),
        _pass("bob", 1, confidence=1.0),
        _pass("cat", 10, confidence=0.5),
    ))

    bob, ann, cat = scores["bob"], scores["ann"], scores["cat"]
    assert (bob.place, ann.place, cat.place) == (1, 2, 3)
    # 19 of 20 seconds left, first place: 95 * 1.0.
    assert (bob.speed_points, bob.accuracy_points, bob.points) == (95, 100, 195)
    # 17 of 20 left, second place: 85 * 0.95 = 80.75.
    assert (ann.speed_points, ann.accuracy_points, ann.points) == (81, 90, 171)
    # 10 of 20 left, third place: 50 * 0.90 = 45.
    assert (cat.speed_points, cat.accuracy_points, cat.points) == (45, 50, 95)


def test_a_round_is_worth_at_most_200():
    scores = score_round(_round(_pass("ann", 0, confidence=1.0)))
    assert scores["ann"].points == 200


def test_the_placement_factor_bottoms_out_at_zero():
    """Twenty-first place keeps none of its speed points, but still earns accuracy."""
    passes = [_pass(f"p{i:02}", i * 0.01, confidence=0.5) for i in range(21)]
    last = score_round(_round(*passes))["p20"]
    assert last.place == 21
    assert last.speed_points == 0
    assert last.points == 50


def test_nobody_who_failed_to_pass_is_scored():
    assert score_round(_round()) == {}


# --- the highlight reel ------------------------------------------------------


def test_highlights_are_the_three_most_accurate_faces_best_first():
    rnd = _round(
        _pass("ann", 1, confidence=0.6),
        _pass("bob", 2, confidence=0.95),
        _pass("cat", 3, confidence=0.8),
        _pass("dan", 4, confidence=0.4),
    )
    highlights = pick_highlights(rnd, score_round(rnd))
    assert [h.player_id for h in highlights] == ["bob", "cat", "ann"]
    assert [h.accuracy_points for h in highlights] == [95, 80, 60]
    assert highlights[0].submission_id == "s_bob"
    assert highlights[0].label == "angry"
    assert highlights[0].place == 2


def test_an_earlier_pass_wins_a_tie_for_the_highlights():
    rnd = _round(_pass("ann", 5, confidence=0.9), _pass("bob", 1, confidence=0.9))
    assert [h.player_id for h in pick_highlights(rnd, score_round(rnd))] == ["bob", "ann"]


def test_a_round_nobody_passed_has_no_highlights():
    rnd = _round()
    assert pick_highlights(rnd, score_round(rnd)) == []


# --- through the game ----------------------------------------------------------


def test_a_correct_face_scores_speed_plus_accuracy_when_the_round_ends(tmp_path, jpeg):
    """One round only, so the committed round is still the one being inspected."""
    with make_client(tmp_path, processor="test-hit", rounds_per_game=1) as client:
        host = create_room(client, "alice")
        guest = join_room(client, host["room_id"], "bob")
        room_id = host["room_id"]

        state = play_one_round(client, room_id, [host, guest], jpeg)
        assert set(state["round"]["passed"]) == {host["player_id"], guest["player_id"]}
        # Points are committed by the server at the end of the round, not on a pass.
        assert all(p["points"] == 0 for p in state["players"].values())

        state = wait_for(client, room_id, lambda s: s["phase"] == "game_over")
    scores = state["round"]["scores"]
    assert sorted(s["place"] for s in scores.values()) == [1, 2]
    for player_id, player in state["players"].items():
        score = scores[player_id]
        # The hit processor is fully confident; speed depends on how fast the upload was.
        assert score["accuracy_points"] == 100
        assert 0 < score["speed_points"] <= 100
        assert score["points"] == score["speed_points"] + score["accuracy_points"] <= 200
        assert player["points"] == score["points"]
        assert player["rounds_correct"] == 1
    assert state["round"]["points_awarded"] == {pid: s["points"] for pid, s in scores.items()}
    # Both passing frames make the highlight reel, and it is kept with the round.
    highlights = state["round"]["highlights"]
    assert {h["player_id"] for h in highlights} == set(scores)
    assert [h["place"] for h in highlights] == [1, 2]
    assert state["history"][-1]["highlights"] == highlights
    for h in highlights:
        assert client.get(f"/api/media/{h['submission_id']}").status_code == 200


def test_a_wrong_answer_scores_nothing(miss_client, jpeg):
    host = create_room(miss_client, "alice")
    room_id = host["room_id"]

    state = play_one_round(miss_client, room_id, [host], jpeg)
    assert all(s["correct"] is False for s in state["round"]["submissions"].values())
    assert state["round"]["passed"] == {}

    state = wait_for(miss_client, room_id, lambda s: s["phase"] == "game_over")
    assert all(p["points"] == 0 for p in state["players"].values())
    assert all(p["rounds_correct"] == 0 for p in state["players"].values())


def test_points_accumulate_across_rounds(hit_client, jpeg):
    """Two rounds in the fixture config, so a player who passes both banks both."""
    host = create_room(hit_client, "alice")
    room_id = host["room_id"]

    hit_client.post(f"/api/rooms/{room_id}/start", params={"player_id": host["player_id"]})
    banked = 0
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
        state = wait_for(
            hit_client,
            room_id,
            lambda s, b=banked: s["players"][host["player_id"]]["points"] > b,
        )
        banked = state["players"][host["player_id"]]["points"]

    state = wait_for(hit_client, room_id, lambda s: s["phase"] == "game_over")
    assert state["players"][host["player_id"]]["rounds_correct"] == 2
    assert 200 < state["players"][host["player_id"]]["points"] <= 400


def test_a_player_who_never_submits_stays_on_zero(hit_client, jpeg):
    host = create_room(hit_client, "alice")
    idle = join_room(hit_client, host["room_id"], "bob")
    room_id = host["room_id"]

    play_one_round(hit_client, room_id, [host], jpeg)
    state = wait_for(hit_client, room_id, lambda s: s["phase"] == "game_over")

    assert state["players"][host["player_id"]]["points"] > 0
    assert state["players"][idle["player_id"]]["points"] == 0


def test_a_passed_player_is_done_for_the_round(hit_client, jpeg):
    """Their slot stays on the passing frame, and further frames are skipped, not scored."""
    host = create_room(hit_client, "alice")
    room_id = host["room_id"]

    state = play_one_round(hit_client, room_id, [host], jpeg)
    passing = state["round"]["passed"][host["player_id"]]

    res = hit_client.post(
        f"/api/rooms/{room_id}/frames",
        data={"player_id": host["player_id"]},
        files=frame_files(jpeg),
    )
    assert res.status_code == 200
    assert res.json() == {"skipped": True, "reason": "passed"}
    assert state_of(hit_client, room_id)["round"]["submissions"][host["player_id"]]["id"] == (
        passing["id"]
    )


def test_a_correct_face_counts_even_after_a_newer_frame_replaced_it(tmp_path, jpeg):
    """The live camera keeps uploading while a slow model is still judging the good frame."""
    with make_client(
        tmp_path, processor="test-marked", round_seconds=10, rounds_per_game=1
    ) as client:
        host = create_room(client, "alice")
        room_id = host["room_id"]
        client.post(f"/api/rooms/{room_id}/start", params={"player_id": host["player_id"]})
        wait_for(client, room_id, lambda s: s["phase"] == "round")

        good = client.post(
            f"/api/rooms/{room_id}/frames",
            data={"player_id": host["player_id"]},
            files=frame_files(jpeg + MarkedProcessor.MARK),
        ).json()["submission_id"]
        client.post(
            f"/api/rooms/{room_id}/frames",
            data={"player_id": host["player_id"]},
            files=frame_files(jpeg),
        )

        state = wait_for(client, room_id, lambda s: host["player_id"] in s["round"]["passed"])
        assert state["round"]["passed"][host["player_id"]]["id"] == good
        assert state["round"]["submissions"][host["player_id"]]["id"] == good


def test_the_round_ends_early_once_every_connected_player_has_passed(tmp_path, jpeg):
    """A player with no socket open (bob) is not waited for."""
    with make_client(
        tmp_path, processor="test-hit", round_seconds=30, rounds_per_game=1
    ) as client:
        host = create_room(client, "alice")
        join_room(client, host["room_id"], "bob")
        room_id = host["room_id"]

        with client.websocket_connect(f"/ws/rooms/{room_id}?player_id={host['player_id']}"):
            wait_for(client, room_id, lambda s: s["players"][host["player_id"]]["connected"])
            client.post(f"/api/rooms/{room_id}/start", params={"player_id": host["player_id"]})
            wait_for(client, room_id, lambda s: s["phase"] == "round")
            started = time.time()
            client.post(
                f"/api/rooms/{room_id}/frames",
                data={"player_id": host["player_id"]},
                files=frame_files(jpeg),
            )
            state = wait_for(client, room_id, lambda s: s["phase"] == "game_over", timeout=10)

        assert time.time() - started < 5, "the 30s round should have ended on the pass"
        assert state["players"][host["player_id"]]["points"] > 0


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
