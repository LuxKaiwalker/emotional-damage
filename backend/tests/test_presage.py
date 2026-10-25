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
from tests.conftest import create_room, frame_files, make_client, wait_for

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


def scores_for(top: str) -> dict[str, float]:
    return {name: (0.9 if name == top else 0.0125) for name in PRESAGE_EXPRESSIONS}


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


def test_a_pushed_expression_wins_the_round(presage_client, jpeg):
    """End to end: the sidecar's reading, not the frame's bytes, decides the frame."""
    host = create_room(presage_client, "alice")
    room_id, player_id = host["room_id"], host["player_id"]

    res = presage_client.post(f"/api/rooms/{room_id}/start", params={"player_id": player_id})
    assert res.status_code == 202, res.text
    state = wait_for(presage_client, room_id, lambda s: s["phase"] == "round")
    target = state["round"]["target"]

    # What Presage would say for a face pulling exactly the asked-for expression.
    top = next(
        name for name in PRESAGE_EXPRESSIONS
        if judge_label(name, target) == target
    )
    res = push(presage_client, room_id, player_id, {name: 0.0 for name in PRESAGE_EXPRESSIONS} | {top: 88.0})
    assert res.status_code == 202, res.text

    res = presage_client.post(
        f"/api/rooms/{room_id}/frames", data={"player_id": player_id}, files=frame_files(jpeg)
    )
    assert res.status_code == 202, res.text

    state = wait_for(presage_client, room_id, lambda s: player_id in s["round"]["passed"])
    result = state["round"]["passed"][player_id]["result"]
    assert result["label"] == target
    assert result["confidence"] == 0.88
    assert result["meta"]["processor"] == "presage"


def judge_label(top: str, target: str) -> str:
    board = ExpressionBoard()
    board.put("r", "p", scores_for(top), stable=True)
    return judge(board.latest("r", "p"), target)[0]
