"""The blitz pass threshold, and the proof it did not leak into classic.

`test-weak` answers with the right label at confidence 0.2, which is the only way to tell
a label-only rule from a confidence rule apart -- `test-hit` passes everything.
"""

from app.game.engine import GameEngine
from app.models import GameMode, ProcessResult
from tests.conftest import (
    TINY_JPEG,
    blitz_client,
    create_room,
    make_client,
    play_one_round,
    run_of,
    send_frame,
    start_blitz,
    wait_for,
)


def _read(confidence: float, label: str = "happy") -> ProcessResult:
    return ProcessResult(score=1.0, label=label, confidence=confidence)


def test_is_correct_defaults_to_label_only():
    """Classic callers pass no threshold, so they must get exactly the old rule."""
    assert GameEngine._is_correct(_read(0.0), "happy") is True
    assert GameEngine._is_correct(_read(1.0), "sad") is False
    assert GameEngine._is_correct(None, "happy") is False


def test_is_correct_honours_a_threshold():
    assert GameEngine._is_correct(_read(0.5), "happy", 0.4) is True
    assert GameEngine._is_correct(_read(0.5), "happy", 0.5) is True, "the bar is inclusive"
    assert GameEngine._is_correct(_read(0.5), "happy", 0.6) is False
    # The right label is still required, however confident the read.
    assert GameEngine._is_correct(_read(1.0), "sad", 0.1) is False


def test_a_weak_read_fails_a_raised_bar(tmp_path):
    with blitz_client(
        tmp_path, processor="test-weak", blitz_pass_confidence=0.5, blitz_face_seconds=60
    ) as client:
        host = create_room(client)
        start_blitz(client, host["room_id"], host)

        assert send_frame(client, host["room_id"], host, TINY_JPEG).status_code == 202
        state = wait_for(
            client,
            host["room_id"],
            lambda s: (run_of(s, host)["submission"] or {}).get("status") == "done",
        )
        run = run_of(state, host)
        assert run["submission"]["correct"] is False
        assert run["passed"] == 0
        assert run["face_no"] == 1, "a sub-threshold read must not advance the face"
        assert state["players"][host["player_id"]]["points"] == 0


def test_the_same_weak_read_passes_a_lower_bar(tmp_path):
    with blitz_client(
        tmp_path, processor="test-weak", blitz_pass_confidence=0.2, blitz_face_seconds=60
    ) as client:
        host = create_room(client)
        start_blitz(client, host["room_id"], host)
        assert send_frame(client, host["room_id"], host, TINY_JPEG).status_code == 202
        state = wait_for(client, host["room_id"], lambda s: run_of(s, host)["passed"] == 1)
        assert state["players"][host["player_id"]]["points"] == 120


def test_classic_still_ignores_confidence(tmp_path):
    """The threshold is a blitz rule. A weak read has always won a classic round."""
    with make_client(tmp_path, processor="test-weak", blitz_pass_confidence=0.9) as client:
        host = create_room(client)
        state = play_one_round(client, host["room_id"], [host], TINY_JPEG)
        assert host["player_id"] in state["round"]["passed"]
        assert state["round"]["submissions"][host["player_id"]]["correct"] is True


def test_pass_threshold_is_zero_outside_blitz(tmp_path):
    with make_client(tmp_path, blitz_pass_confidence=0.9) as client:
        host = create_room(client)
        engine = client.app.state.engine
        room = engine.require_room(host["room_id"])
        assert room.state.config.mode is GameMode.CLASSIC
        assert engine.pass_threshold(room) == 0.0
