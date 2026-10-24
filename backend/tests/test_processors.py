"""The processor seam: what is selectable, and how each one fails.

Nothing here calls Gemini. `PROCESSOR=gemini` is checked for selectability and for the two
things that must not depend on a network: that a missing key is caught at startup rather
than on every frame, and that the vision processor is never imported unless it is chosen.
"""

import pytest

from app.config import Settings
from app.game.prompts import TARGET_LABELS
from app.processing import registry
from app.processing.base import RoundCtx
from app.processing.dummy import DummyProcessor
from tests.conftest import create_room, frame_files, make_client, wait_for


def test_gemini_is_selectable(client):
    assert "gemini" in registry.known()
    assert "dummy" in registry.known()
    assert "custom" in registry.known()


def test_unknown_processor_names_the_known_ones():
    with pytest.raises(ValueError, match="unknown processor"):
        registry.get_processor("definitely-not-a-processor")


def test_gemini_without_a_key_fails_at_startup_not_per_frame(monkeypatch):
    """A config mistake should be one loud error, not 200 failed submissions.

    The settings object is substituted rather than the environment, so a developer who
    does have GEMINI_API_KEY in their own backend/.env still runs the same test.
    """
    import app.processing.gemini as gemini_module

    monkeypatch.setattr(
        gemini_module, "get_settings", lambda: Settings(gemini_api_key=None)
    )
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        registry.get_processor("gemini")


def test_gemini_builds_when_a_key_is_present(monkeypatch):
    """Construction is offline: it only builds the SDK client, it does not call out."""
    import app.processing.gemini as gemini_module

    monkeypatch.setattr(
        gemini_module, "get_settings", lambda: Settings(gemini_api_key="test-key")
    )
    processor = registry.get_processor("gemini")
    assert processor.name == "gemini"


def test_gemini_constrains_the_model_to_the_games_vocabulary():
    """Scoring is label == target, so an off-vocabulary label can never win a point."""
    from app.processing.gemini import NO_FACE, RESPONSE_SCHEMA

    allowed = RESPONSE_SCHEMA["properties"]["label"]["enum"]
    assert set(TARGET_LABELS).issubset(allowed)
    assert NO_FACE in allowed
    assert NO_FACE not in TARGET_LABELS


def test_selecting_dummy_never_imports_the_vision_processor(monkeypatch):
    """A stale virtualenv missing google-genai must not stop PROCESSOR=dummy."""
    import builtins

    real_import = builtins.__import__

    def explode_on_genai(name, *args, **kwargs):
        if name.startswith("google.genai") or name == "google":
            raise ImportError("google-genai is not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", explode_on_genai)
    # Registry entries are factories, so this touches nothing Gemini-related.
    assert registry.get_processor("dummy").name == "dummy"


@pytest.mark.parametrize("payload", [b"a", b"frame-bytes", bytes(range(256))])
def test_dummy_only_ever_emits_labels_the_game_can_score(payload):
    """A label outside the vocabulary could never match a target, so it must not happen."""
    import asyncio

    ctx = RoundCtx(
        room_id="r", player_id="p", round_no=1, prompt="look scared", target="scared"
    )
    result = asyncio.run(DummyProcessor(fake_latency_s=0).process(payload, ctx))
    assert result.label in TARGET_LABELS
    assert 0.0 <= result.confidence <= 1.0


def test_dummy_is_deterministic_on_frame_bytes():
    """Worth pinning: it is also exactly why dummy cannot be a real processor."""
    import asyncio

    ctx = RoundCtx(room_id="r", player_id="p", round_no=1, prompt="p", target="scared")
    proc = DummyProcessor(fake_latency_s=0)
    first = asyncio.run(proc.process(b"same-bytes", ctx))
    second = asyncio.run(proc.process(b"same-bytes", ctx))
    assert first.label == second.label
    assert first.score == second.score


def test_custom_stub_fails_the_submission_without_taking_the_server_down(tmp_path, jpeg):
    """The documented extension point is still a stub; it must degrade, not crash."""
    with make_client(tmp_path, processor="custom", rounds_per_game=1) as client:
        host = create_room(client, "alice")
        room_id = host["room_id"]
        client.post(f"/api/rooms/{room_id}/start", params={"player_id": host["player_id"]})
        wait_for(client, room_id, lambda s: s["phase"] == "round")

        res = client.post(
            f"/api/rooms/{room_id}/frames",
            data={"player_id": host["player_id"]},
            files=frame_files(jpeg),
        )
        assert res.status_code == 202

        # This submission never reaches "done" -- that is the behaviour under test.
        state = wait_for(
            client,
            room_id,
            lambda s: s["round"]
            and s["round"]["submissions"].get(host["player_id"], {}).get("status")
            == "failed",
        )
        submission = state["round"]["submissions"][host["player_id"]]
        assert submission["error"] == "processing_failed"
        assert submission["correct"] is None
        # Server is still answering.
        assert client.get("/api/health").json()["status"] == "ok"
