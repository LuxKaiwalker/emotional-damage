"""PROCESSOR=presage: the sidecar pushes expressions, frames are judged by the newest one.

Nothing here talks to Presage. The sidecar's half is a POST to /internal/presage/expressions,
so these tests stand in for it, and the processor is exercised against readings they put.
"""

import time

import pytest

from app.game.prompts import TARGET_LABELS
from app.processing import registry
from app.processing.base import RoundCtx
from app.processing.presage import (
    NO_FACE,
    PRESAGE_EXPRESSIONS,
    READINGS,
    ExpressionBoard,
    PresageProcessor,
    judge,
)
from tests.conftest import (
    TINY_JPEG,
    blitz_client,
    create_room,
    frame_files,
    make_client,
    run_of,
    start_blitz,
    state_of,
    wait_for,
)

TOKEN = "test-presage-token"


@pytest.fixture(autouse=True)
def _empty_board():
    READINGS.clear()
    yield
    READINGS.clear()


@pytest.fixture
def presage_client(tmp_path):
    with make_client(tmp_path, processor="presage", presage_ingest_token=TOKEN) as c:
        yield c


def push(client, room_id, player_id, scores, token=TOKEN):
    return client.post(
        "/internal/presage/expressions",
        json={"room_id": room_id, "player_id": player_id, "scores": scores, "stable": True},
        headers={"x-presage-token": token},
    )


def ctx(target: str, room_id="r", player_id="p") -> RoundCtx:
    return RoundCtx(room_id=room_id, player_id=player_id, round_no=1, prompt="", target=target)


def scores_for(top: str, value: float = 0.9) -> dict[str, float]:
    """One expression on top. `value` is the SDK's 0-100 scale, so 90.0 -> confidence 0.9."""
    return {name: (value if name == top else 0.0125) for name in PRESAGE_EXPRESSIONS}


def test_presage_is_selectable():
    assert "presage" in registry.known()


@pytest.mark.parametrize(
    "top,target,label",
    [
        ("happy", "happy", "happy"),
        ("fear", "scared", "scared"),
        ("disgust", "disgusted", "disgusted"),
        ("surprise", "surprised", "surprised"),
        ("neutral", "happy", NO_FACE),
        # Presage has no "disappointed"; sad stands in, but only when that is the ask.
        ("sad", "disappointed", "disappointed"),
        ("sad", "sad", "sad"),
    ],
)
def test_presage_expressions_map_onto_the_game_vocabulary(top, target, label):
    board = ExpressionBoard()
    board.put("r", "p", scores_for(top), stable=True)
    assert judge(board.latest("r", "p"), target) == (label, 0.9)


def test_every_target_is_reachable():
    board = ExpressionBoard()
    for target in TARGET_LABELS:
        reachable = False
        for top in PRESAGE_EXPRESSIONS:
            board.put("r", "p", scores_for(top), stable=True)
            reachable |= judge(board.latest("r", "p"), target)[0] == target
        assert reachable, target


async def test_no_reading_and_stale_reading_score_as_no_face():
    board = ExpressionBoard()
    processor = PresageProcessor(board=board, max_age_s=0.05)

    result = await processor.process(b"jpeg", ctx("happy"))
    assert (result.label, result.meta["reason"]) == (NO_FACE, "no_reading")

    board.put("r", "p", scores_for("happy"), stable=True)
    fresh = await processor.process(b"jpeg", ctx("happy"))
    assert (fresh.label, fresh.confidence) == ("happy", 0.9)

    time.sleep(0.06)
    stale = await processor.process(b"jpeg", ctx("happy"))
    assert (stale.label, stale.meta["reason"]) == (NO_FACE, "stale_reading")


def test_health_counts_only_readings_young_enough_to_score(tmp_path):
    with make_client(
        tmp_path, processor="presage", presage_ingest_token=TOKEN, presage_max_age_ms=50
    ) as client:
        host = create_room(client, "alice")
        assert push(client, host["room_id"], host["player_id"], {"happy": 90.0}).status_code == 202
        assert client.get("/api/health").json()["presage"]["players_reading"] == 1

        # Still on the board, but a frame now would score "none": the sidecar has gone quiet.
        time.sleep(0.06)
        assert client.get("/api/health").json()["presage"]["players_reading"] == 0


def test_ingest_needs_the_token(presage_client):
    host = create_room(presage_client, "alice")
    res = push(presage_client, host["room_id"], host["player_id"], {"happy": 90.0}, token="nope")
    assert res.status_code == 401
    assert len(READINGS) == 0


def test_ingest_is_off_without_a_token(client):
    host = create_room(client, "alice")
    res = push(client, host["room_id"], host["player_id"], {"happy": 90.0})
    assert res.status_code == 503


def test_ingest_rejects_unknown_players_and_expressions(presage_client):
    host = create_room(presage_client, "alice")
    room_id = host["room_id"]
    assert push(presage_client, room_id, "p_nobody", {"happy": 90.0}).status_code == 404
    assert push(presage_client, "r_nowhere", host["player_id"], {"happy": 90.0}).status_code == 404
    assert push(presage_client, room_id, host["player_id"], {"smug": 90.0}).status_code == 422
    assert push(presage_client, room_id, host["player_id"], {"happy": 900.0}).status_code == 422


def test_presage_without_a_token_fails_at_startup(tmp_path):
    with pytest.raises(ValueError, match="PRESAGE_INGEST_TOKEN"):
        with make_client(tmp_path, processor="presage"):
            pass


def start_round(client) -> tuple[str, str, str]:
    host = create_room(client, "alice")
    room_id, player_id = host["room_id"], host["player_id"]
    res = client.post(f"/api/rooms/{room_id}/start", params={"player_id": player_id})
    assert res.status_code == 202, res.text
    state = wait_for(client, room_id, lambda s: s["phase"] == "round")
    return room_id, player_id, state["round"]["target"]


def test_a_hit_reading_passes_the_player_without_waiting_for_a_frame(presage_client):
    """The reading itself scores: no upload tick between the face and the point."""
    room_id, player_id, target = start_round(presage_client)
    top = next(name for name in PRESAGE_EXPRESSIONS if judge_label(name, target) == target)

    res = push(presage_client, room_id, player_id, {name: 0.0 for name in PRESAGE_EXPRESSIONS} | {top: 88.0})
    assert res.status_code == 202, res.text
    assert res.json()["scored"] is True

    state = wait_for(presage_client, room_id, lambda s: player_id in s["round"]["passed"])
    result = state["round"]["passed"][player_id]["result"]
    assert result["label"] == target
    assert result["confidence"] == 0.88
    assert result["meta"]["source"] == "reading"

    # Passed means passed: the next upload is turned away like any other.
    res = presage_client.post(
        f"/api/rooms/{room_id}/frames", data={"player_id": player_id}, files=frame_files(TINY_JPEG)
    )
    assert res.json() == {"skipped": True, "reason": "passed"}


def test_a_miss_reading_scores_nothing_until_a_frame_arrives(presage_client, jpeg):
    """Misses stay on the upload path, so readings do not broadcast state on their own."""
    room_id, player_id, target = start_round(presage_client)
    miss = next(name for name in PRESAGE_EXPRESSIONS if judge_label(name, target) != target)

    res = push(presage_client, room_id, player_id, {name: 0.0 for name in PRESAGE_EXPRESSIONS} | {miss: 90.0})
    assert res.json()["scored"] is False
    assert state_of(presage_client, room_id)["round"]["submissions"] == {}

    res = presage_client.post(
        f"/api/rooms/{room_id}/frames", data={"player_id": player_id}, files=frame_files(jpeg)
    )
    assert res.status_code == 202, res.text
    state = wait_for(
        presage_client,
        room_id,
        lambda s: s["round"]["submissions"].get(player_id, {}).get("status") == "done",
    )
    sub = state["round"]["submissions"][player_id]
    assert sub["correct"] is False
    assert sub["result"]["label"] == judge_label(miss, target)


def hit_for(target: str) -> dict[str, float]:
    top = next(name for name in PRESAGE_EXPRESSIONS if judge_label(name, target) == target)
    return {name: 0.0 for name in PRESAGE_EXPRESSIONS} | {top: 88.0}


def upload_and_settle(client, room_id, player_id, jpeg) -> None:
    res = client.post(f"/api/rooms/{room_id}/frames", data={"player_id": player_id}, files=frame_files(jpeg))
    assert res.status_code == 202, res.text
    wait_for(client, room_id, lambda s: s["round"]["submissions"].get(player_id, {}).get("status") == "done")


def test_a_reading_pass_shows_the_player_s_newest_frame(presage_client, jpeg):
    """A reading has no picture, so the hall of faces shows the upload it landed next to."""
    room_id, player_id, target = start_round(presage_client)
    upload_and_settle(presage_client, room_id, player_id, jpeg)

    assert push(presage_client, room_id, player_id, hit_for(target)).json()["scored"] is True
    passed = state_of(presage_client, room_id)["round"]["passed"][player_id]
    assert passed["result"]["meta"]["source"] == "reading"

    res = presage_client.get(f"/api/media/{passed['id']}")
    assert res.status_code == 200
    assert res.content == jpeg


def test_a_reading_pass_without_an_upload_has_no_picture(presage_client):
    room_id, player_id, target = start_round(presage_client)
    assert push(presage_client, room_id, player_id, hit_for(target)).json()["scored"] is True
    passed = state_of(presage_client, room_id)["round"]["passed"][player_id]
    assert presage_client.get(f"/api/media/{passed['id']}").status_code == 404


def test_a_reading_pass_does_not_borrow_a_stale_frame(tmp_path, jpeg):
    """A frame older than a reading may be need not show the face that scored."""
    with make_client(
        tmp_path, processor="presage", presage_ingest_token=TOKEN, presage_max_age_ms=200, round_seconds=5
    ) as client:
        room_id, player_id, target = start_round(client)
        upload_and_settle(client, room_id, player_id, jpeg)
        time.sleep(0.3)

        assert push(client, room_id, player_id, hit_for(target)).json()["scored"] is True
        passed = state_of(client, room_id)["round"]["passed"][player_id]
        assert client.get(f"/api/media/{passed['id']}").status_code == 404


def judge_label(top: str, target: str) -> str:
    board = ExpressionBoard()
    board.put("r", "p", scores_for(top), stable=True)
    return judge(board.latest("r", "p"), target)[0]

# --- blitz ----------------------------------------------------------------
#
# The reading path is what makes blitz feel fast: a face counts the instant Presage sees
# it, instead of waiting out a CAPTURE_INTERVAL_MS upload tick per face.


@pytest.fixture
def presage_blitz(tmp_path):
    with blitz_client(
        tmp_path,
        processor="presage",
        presage_ingest_token=TOKEN,
        blitz_face_seconds=60,
    ) as c:
        yield c


def test_a_reading_passes_the_player_s_own_face_in_blitz(presage_blitz):
    host = create_room(presage_blitz)
    room_id, player_id = host["room_id"], host["player_id"]
    state = start_blitz(presage_blitz, room_id, host)
    target = run_of(state, host)["target"]
    top = next(name for name in PRESAGE_EXPRESSIONS if judge_label(name, target) == target)

    res = push(presage_blitz, room_id, player_id, scores_for(top, 90.0))
    assert res.status_code == 202, res.text
    assert res.json()["scored"] is True

    state = wait_for(presage_blitz, room_id, lambda s: run_of(s, host)["passed"] == 1)
    run = run_of(state, host)
    assert run["face_no"] == 2, "a hit advances the cursor"
    assert run["last_points"] == 190, "100 flat plus round(0.9 * 100)"
    assert state["players"][player_id]["points"] == 190


def test_a_sub_threshold_reading_does_not_spend_the_rate_limit(presage_blitz):
    """A read that cannot pass must not consume the player's min_frame_interval_ms slot.

    Without the pre-check in `_score_if_hit` it would submit, fail, and leave the player
    unable to send a real frame for another interval -- which in blitz costs them faces.
    """
    host = create_room(presage_blitz)
    room_id, player_id = host["room_id"], host["player_id"]
    engine = presage_blitz.app.state.engine
    room = engine.require_room(room_id)
    room.state.config = room.state.config.model_copy(update={"blitz_pass_confidence": 0.8})

    state = start_blitz(presage_blitz, room_id, host)
    target = run_of(state, host)["target"]
    top = next(name for name in PRESAGE_EXPRESSIONS if judge_label(name, target) == target)

    res = push(presage_blitz, room_id, player_id, scores_for(top, 30.0))
    assert res.json()["scored"] is False
    state = state_of(presage_blitz, room_id)
    run = run_of(state, host)
    assert run["passed"] == 0
    assert run["face_no"] == 1
    assert run["submission"] is None, "no submission should have been registered at all"


def test_a_reading_for_a_face_the_player_left_pays_nothing(presage_blitz):
    """Skipping mid-flight must not pay for the face that was abandoned.

    Asserts on the *expression* rather than the target: `disappointed` is read off `sad`,
    so "the next target is a different string" is not enough to know the held face cannot
    satisfy it. `build_sequence` guarantees the stronger condition -- see
    test_blitz_sequence.test_no_two_neighbours_can_be_satisfied_by_one_face -- and this
    checks the behaviour that rule exists to produce.
    """
    host = create_room(presage_blitz)
    room_id, player_id = host["room_id"], host["player_id"]
    state = start_blitz(presage_blitz, room_id, host)
    first = run_of(state, host)["target"]

    res = presage_blitz.post(f"/api/rooms/{room_id}/skip", params={"player_id": player_id})
    assert res.status_code == 200, res.text

    # The expression that satisfied the face just abandoned...
    top = next(name for name in PRESAGE_EXPRESSIONS if judge_label(name, first) == first)
    # ...cannot satisfy the one that replaced it. That is the invariant, not a coincidence.
    nxt = run_of(state_of(presage_blitz, room_id), host)["target"]
    assert judge_label(top, nxt) != nxt, f"{top!r} satisfies both {first!r} and {nxt!r}"

    res = push(presage_blitz, room_id, player_id, scores_for(top, 95.0))
    assert res.json()["scored"] is False
    assert state_of(presage_blitz, room_id)["players"][player_id]["points"] == 0

