"""The per-face limit and the one global clock."""

from datetime import datetime

from app.game.engine import score_face
from tests.conftest import (
    TINY_JPEG,
    blitz_client,
    create_room,
    join_room,
    push_faces,
    run_of,
    start_blitz,
    state_of,
    wait_for,
)


def test_score_face_is_flat_plus_accuracy():
    assert score_face(0.0) == 100
    assert score_face(0.5) == 150
    assert score_face(1.0) == 200
    # Clamped, so a misbehaving processor cannot mint points.
    assert score_face(2.0) == 200
    assert score_face(-1.0) == 100


def test_a_face_rolls_over_on_its_own(tmp_path):
    """Nobody has to be sending frames: the driver's sweep moves a stalled player on."""
    with blitz_client(tmp_path, processor="test-miss", blitz_face_seconds=1) as client:
        host = create_room(client)
        state = start_blitz(client, host["room_id"], host)
        first = run_of(state, host)["prompt"]

        state = wait_for(client, host["room_id"], lambda s: run_of(s, host)["expired"] >= 1)
        run = run_of(state, host)
        assert run["face_no"] >= 2
        assert run["last_outcome"] == "expired"
        assert run["last_points"] == 0
        assert run["prompt"] != first
        assert state["players"][host["player_id"]]["points"] == 0


def test_several_faces_lapse_without_anyone_connected(tmp_path):
    with blitz_client(tmp_path, processor="test-miss", blitz_face_seconds=1) as client:
        host = create_room(client)
        start_blitz(client, host["room_id"], host)
        state = wait_for(
            client, host["room_id"], lambda s: run_of(s, host)["expired"] >= 3, timeout=15.0
        )
        assert run_of(state, host)["face_no"] >= 4


def test_a_face_deadline_never_outlives_the_game_clock(tmp_path):
    with blitz_client(tmp_path, processor="test-miss", blitz_seconds=4, blitz_face_seconds=60) as client:
        host = create_room(client)
        state = start_blitz(client, host["room_id"], host)
        assert run_of(state, host)["face_ends_at"] <= state["game_ends_at"]


def test_the_blitz_clock_is_blitz_seconds_not_game_seconds(tmp_path):
    """`game_seconds` is sized for a round schedule and means nothing here."""
    with blitz_client(tmp_path, processor="test-hit", blitz_seconds=120, game_seconds=600) as client:
        host = create_room(client)
        state = start_blitz(client, host["room_id"], host)
        span = (
            datetime.fromisoformat(state["game_ends_at"])
            - datetime.fromisoformat(state["game_started_at"])
        ).total_seconds()
        assert 119 <= span <= 121


def test_the_breakdown_records_every_outcome(tmp_path):
    with blitz_client(
        tmp_path, processor="test-hit", blitz_seconds=6, blitz_face_seconds=2
    ) as client:
        host = create_room(client)
        start_blitz(client, host["room_id"], host)
        push_faces(client, host["room_id"], host, TINY_JPEG, 1)
        client.post(f"/api/rooms/{host['room_id']}/skip", params={"player_id": host["player_id"]})

        state = wait_for(
            client, host["room_id"], lambda s: s["phase"] == "game_over", timeout=20.0
        )
        faces = run_of(state, host)["faces"]
        outcomes = [f["outcome"] for f in faces]
        assert outcomes[0] == "passed" and outcomes[1] == "skipped"
        assert "expired" in outcomes, "the rest of the clock should have lapsed faces"
        # Each entry carries enough to rebuild the round-by-round view.
        assert faces[0]["points"] == 200 and faces[0]["confidence"] == 1.0
        assert faces[1]["points"] == 0 and faces[1]["confidence"] is None
        assert all(f["prompt"] and f["target"] for f in faces)
        assert [f["index"] for f in faces] == list(range(len(faces)))


def test_leaving_drops_the_run(tmp_path):
    with blitz_client(tmp_path, processor="test-hit", blitz_face_seconds=60) as client:
        host = create_room(client)
        guest = join_room(client, host["room_id"], "guest")
        start_blitz(client, host["room_id"], host)

        res = client.post(
            f"/api/rooms/{host['room_id']}/leave", params={"player_id": guest["player_id"]}
        )
        assert res.status_code == 200, res.text
        state = state_of(client, host["room_id"])
        assert guest["player_id"] not in state["blitz"]["runs"]
        assert host["player_id"] in state["blitz"]["runs"]


# --- hall of fame -----------------------------------------------------------
#
# Classic picks a top three per round and the winner screen takes the best of those.
# A blitz has no rounds, so the server ranks across whole runs instead and publishes
# the result on BlitzState, once, at game over.


def test_pick_blitz_highlights_ranks_by_accuracy_then_earliest_face():
    from app.game.engine import pick_blitz_highlights
    from app.models import BlitzFace

    def face(i, conf, outcome="passed", sub="s"):
        return BlitzFace(
            index=i, prompt="p", target="happy", outcome=outcome,
            points=100, confidence=conf, submission_id=sub,
        )

    done = {
        "alice": [face(0, 0.90, sub="a0"), face(5, 1.00, sub="a5")],
        "bob": [face(1, 0.90, sub="b1"), face(2, 0.40, sub="b2")],
    }
    picked = pick_blitz_highlights(done)
    assert [(h.player_id, h.accuracy_points, h.face_no) for h in picked] == [
        ("alice", 100, 6),   # the most accurate face wins outright
        ("alice", 90, 1),    # a tie on accuracy goes to the earlier face
        ("bob", 90, 2),
    ]
    assert [h.place for h in picked] == [1, 2, 3]
    assert [h.submission_id for h in picked] == ["a5", "a0", "b1"]


def test_pick_blitz_highlights_keeps_only_pinnable_faces():
    """A skipped or lapsed face has no read to rank, and no photo to pin up."""
    from app.game.engine import pick_blitz_highlights
    from app.models import BlitzFace

    done = {
        "alice": [
            BlitzFace(index=0, prompt="p", target="sad", outcome="skipped", points=0),
            BlitzFace(index=1, prompt="p", target="sad", outcome="expired", points=0),
            # Passed, but its frame was never kept: nothing to show.
            BlitzFace(index=2, prompt="p", target="sad", outcome="passed", points=150,
                      confidence=0.5, submission_id=None),
            BlitzFace(index=3, prompt="p", target="sad", outcome="passed", points=180,
                      confidence=0.8, submission_id="ok"),
        ]
    }
    picked = pick_blitz_highlights(done)
    assert [h.submission_id for h in picked] == ["ok"]


def test_pick_blitz_highlights_is_empty_when_nothing_landed():
    from app.game.engine import pick_blitz_highlights
    from app.models import BlitzFace

    done = {"alice": [BlitzFace(index=0, prompt="p", target="sad", outcome="expired", points=0)]}
    assert pick_blitz_highlights(done) == []
    assert pick_blitz_highlights({}) == []


def test_a_finished_blitz_publishes_its_best_faces(tmp_path):
    """End to end: the wall is empty all game and filled in once, at game over."""
    with blitz_client(
        tmp_path, processor="test-hit", blitz_seconds=5, blitz_face_seconds=60
    ) as client:
        host = create_room(client)
        guest = join_room(client, host["room_id"], "guest")
        start_blitz(client, host["room_id"], host)

        push_faces(client, host["room_id"], host, TINY_JPEG, 2)
        push_faces(client, host["room_id"], guest, TINY_JPEG, 1)

        mid = state_of(client, host["room_id"])
        assert mid["blitz"]["highlights"] == [], "the wall is only hung at the end"

        state = wait_for(
            client, host["room_id"], lambda s: s["phase"] == "game_over", timeout=20.0
        )
        highlights = state["blitz"]["highlights"]
        assert len(highlights) == 3, "three faces landed, so three go up"
        for h in highlights:
            # Everything the gallery needs without reaching for anything else.
            assert h["submission_id"]
            assert h["player_id"] in state["players"]
            assert h["accuracy_points"] == 100, "test-hit answers with confidence 1.0"
            assert h["label"]
            assert h["face_no"] >= 1
        assert [h["place"] for h in highlights] == [1, 2, 3]
        # Ties on accuracy fall to the earliest face, so face 1s come before face 2.
        assert [h["face_no"] for h in highlights] == [1, 1, 2]


def test_a_passed_blitz_face_remembers_its_frame(tmp_path):
    """The hall needs a submission id on the face, or it has nothing to ask /api/media for."""
    with blitz_client(
        tmp_path, processor="test-hit", blitz_seconds=4, blitz_face_seconds=60
    ) as client:
        host = create_room(client)
        start_blitz(client, host["room_id"], host)
        push_faces(client, host["room_id"], host, TINY_JPEG, 1)
        client.post(f"/api/rooms/{host['room_id']}/skip", params={"player_id": host["player_id"]})

        state = wait_for(
            client, host["room_id"], lambda s: s["phase"] == "game_over", timeout=20.0
        )
        faces = run_of(state, host)["faces"]
        passed = [f for f in faces if f["outcome"] == "passed"]
        assert passed and all(f["submission_id"] for f in passed)
        assert all(f["submission_id"] is None for f in faces if f["outcome"] != "passed")


def test_classic_highlights_are_untouched(tmp_path):
    """The blitz picker is a sibling, not a replacement."""
    from tests.conftest import make_client, play_one_round

    with make_client(tmp_path, processor="test-hit") as client:
        host = create_room(client)
        play_one_round(client, host["room_id"], [host], TINY_JPEG)
        state = wait_for(
            client, host["room_id"], lambda s: s["phase"] == "game_over", timeout=30.0
        )
        assert state["blitz"] is None
        rounds_with_faces = [r for r in state["history"] if r["highlights"]]
        assert rounds_with_faces, "classic still hangs a top three per round"
        for h in rounds_with_faces[0]["highlights"]:
            assert h["face_no"] is None, "a classic highlight takes its number from its round"
