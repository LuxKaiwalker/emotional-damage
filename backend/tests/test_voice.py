"""Round narration: generated off the round's critical path, and never able to break it.

Narration is decoration. These tests pin the three properties that matter: it lands on the
round it was written for, a slow or failing vendor cannot delay or crash a round, and
without API keys the whole feature stays quietly off.

No test here talks to Gemini or ElevenLabs -- `VoiceStudio.narrate` is replaced, so what
is under test is the engine's handling of it.
"""

import asyncio
import time

import pytest

from app.game.voice import Narration, VoiceStore, VoiceStudio
from tests.conftest import create_room, make_client, state_of, wait_for

# Any non-empty key makes the studio consider itself enabled; nothing calls the vendors.
FAKE_KEYS = {"gemini_api_key": "test-key", "elevenlabs_api_key": "test-key"}


def round_of(state: dict) -> dict | None:
    return state.get("round")


def test_narration_lands_on_the_round(tmp_path, monkeypatch):
    async def fake_narrate(self, prompt):
        return Narration(line=f"[gasps] {prompt.target} right now", audio_id="a_test")

    monkeypatch.setattr(VoiceStudio, "narrate", fake_narrate)

    with make_client(tmp_path, rounds_per_game=1, round_seconds=3, **FAKE_KEYS) as client:
        host = create_room(client, "alice")
        room_id = host["room_id"]
        client.post(f"/api/rooms/{room_id}/start", params={"player_id": host["player_id"]})

        state = wait_for(
            client, room_id, lambda s: round_of(s) and round_of(s)["voice_line"] is not None
        )
        rnd = state["round"]
        # The line is written for the prompt this round actually chose.
        assert rnd["target"] in rnd["voice_line"]
        assert rnd["audio_id"] == "a_test"


def test_narration_emits_a_voice_ready_event(tmp_path, monkeypatch):
    async def fake_narrate(self, prompt):
        return Narration(line="say something", audio_id="a_test")

    monkeypatch.setattr(VoiceStudio, "narrate", fake_narrate)

    with make_client(tmp_path, rounds_per_game=1, round_seconds=3, **FAKE_KEYS) as client:
        host = create_room(client, "alice")
        room_id = host["room_id"]

        with client.websocket_connect(
            f"/ws/rooms/{room_id}?player_id={host['player_id']}"
        ) as socket:
            socket.receive_json()  # opening snapshot
            client.post(
                f"/api/rooms/{room_id}/start", params={"player_id": host["player_id"]}
            )

            deadline = time.time() + 10
            while time.time() < deadline:
                msg = socket.receive_json()
                if msg["type"] == "event" and msg["kind"] == "voice_ready":
                    assert msg["payload"]["round"] == 1
                    assert msg["payload"]["line"] == "say something"
                    assert msg["payload"]["audio_id"] == "a_test"
                    return
            raise AssertionError("no voice_ready event arrived")


def test_slow_narration_does_not_delay_the_round(tmp_path, monkeypatch):
    """The vendor is slower than the whole game; the game still finishes on schedule."""

    async def slow_narrate(self, prompt):
        await asyncio.sleep(30)
        return Narration(line="too late", audio_id=None)

    monkeypatch.setattr(VoiceStudio, "narrate", slow_narrate)

    with make_client(
        tmp_path, rounds_per_game=1, round_seconds=1, intermission_seconds=0, **FAKE_KEYS
    ) as client:
        host = create_room(client, "alice")
        room_id = host["room_id"]

        started = time.time()
        client.post(f"/api/rooms/{room_id}/start", params={"player_id": host["player_id"]})
        wait_for(client, room_id, lambda s: s["phase"] == "game_over", timeout=10)
        elapsed = time.time() - started

        # A 1s round must not wait on a 30s narration.
        assert elapsed < 8, f"round was delayed by narration ({elapsed:.1f}s)"
        assert state_of(client, room_id)["round"]["voice_line"] is None


def test_late_narration_is_discarded(tmp_path, monkeypatch):
    """A line that arrives after its round has moved on must not be shown on another one.

    Narrating round 1 over round 2 is worse than silence, so the engine drops it.
    """

    async def late_narrate(self, prompt):
        # Longer than round 1, shorter than the game: it resolves during round 2.
        await asyncio.sleep(2.5)
        return Narration(line=f"line for {prompt.target}", audio_id=None)

    monkeypatch.setattr(VoiceStudio, "narrate", late_narrate)

    with make_client(
        tmp_path, rounds_per_game=2, round_seconds=1, intermission_seconds=0, **FAKE_KEYS
    ) as client:
        host = create_room(client, "alice")
        room_id = host["room_id"]
        client.post(f"/api/rooms/{room_id}/start", params={"player_id": host["player_id"]})

        # Watch round 2 for the duration of round 1's in-flight narration.
        wait_for(client, room_id, lambda s: round_of(s) and round_of(s)["number"] == 2)
        deadline = time.time() + 3
        while time.time() < deadline:
            rnd = round_of(state_of(client, room_id))
            if rnd is not None and rnd["number"] == 2 and rnd["voice_line"] is not None:
                # Only acceptable if it is round 2's own line, never round 1's.
                assert rnd["target"] in rnd["voice_line"]
            time.sleep(0.05)


def test_narration_failure_does_not_disturb_the_round(tmp_path, monkeypatch):
    async def exploding_narrate(self, prompt):
        raise RuntimeError("vendor on fire")

    monkeypatch.setattr(VoiceStudio, "narrate", exploding_narrate)

    with make_client(
        tmp_path, rounds_per_game=1, round_seconds=1, intermission_seconds=0, **FAKE_KEYS
    ) as client:
        host = create_room(client, "alice")
        room_id = host["room_id"]
        client.post(f"/api/rooms/{room_id}/start", params={"player_id": host["player_id"]})

        final = wait_for(client, room_id, lambda s: s["phase"] == "game_over")
        assert final["round"]["voice_line"] is None


def test_voice_is_off_without_api_keys(tmp_path):
    """The default deployment has no keys, so rounds simply carry no narration."""
    with make_client(tmp_path, rounds_per_game=1, round_seconds=1) as client:
        assert client.get("/api/health").json()["voice"]["enabled"] is False

        host = create_room(client, "alice")
        room_id = host["room_id"]
        client.post(f"/api/rooms/{room_id}/start", params={"player_id": host["player_id"]})
        state = wait_for(client, room_id, lambda s: round_of(s) is not None)
        assert state["round"]["voice_line"] is None
        assert state["round"]["audio_id"] is None


def test_voice_can_be_switched_off_even_with_keys(tmp_path):
    with make_client(tmp_path, voice_enabled=False, **FAKE_KEYS) as client:
        assert client.get("/api/health").json()["voice"]["enabled"] is False


def test_health_reports_which_half_of_the_pipeline_is_live(tmp_path):
    """"Why is there no audio" should be answerable without reading the logs."""
    with make_client(tmp_path, gemini_api_key="k") as client:
        voice = client.get("/api/health").json()["voice"]
        assert voice == {"enabled": True, "writes_lines": True, "speaks": False}

    with make_client(tmp_path, elevenlabs_api_key="k") as client:
        voice = client.get("/api/health").json()["voice"]
        assert voice == {"enabled": True, "writes_lines": False, "speaks": True}


def test_unknown_audio_is_404(client):
    assert client.get("/api/voice/a_nope").status_code == 404


def test_generated_audio_is_served_as_mpeg(client):
    """The store is the seam the endpoint reads through, so write through it."""
    store: VoiceStore = client.app.state.voice_store
    asyncio.run(store.write("a_known", b"ID3fake-mp3-bytes"))

    res = client.get("/api/voice/a_known")
    assert res.status_code == 200
    assert res.headers["content-type"] == "audio/mpeg"
    assert res.content == b"ID3fake-mp3-bytes"


@pytest.mark.parametrize(
    "keys,expected",
    [
        ({}, False),
        ({"gemini_api_key": "k"}, True),
        ({"elevenlabs_api_key": "k"}, True),
        ({"gemini_api_key": "k", "elevenlabs_api_key": "k"}, True),
    ],
)
def test_studio_enabled_matrix(tmp_path, keys, expected):
    from app.config import Settings

    settings = Settings(media_dir=tmp_path / "m", **keys)
    studio = VoiceStudio(VoiceStore(tmp_path / "voice", 60), settings)
    assert studio.enabled is expected


def test_disabled_studio_narrates_nothing(tmp_path):
    """With no keys, narrate short-circuits before touching either vendor.

    Passing None for the prompt is the assertion: if it got as far as reading
    `prompt.text`, this would raise instead of returning None.
    """
    from app.config import Settings

    studio = VoiceStudio(
        VoiceStore(tmp_path / "voice", 60), Settings(media_dir=tmp_path / "m")
    )
    assert asyncio.run(studio.narrate(None)) is None


# --- the ElevenLabs seam ---------------------------------------------------
#
# `voice.py` reaches into `voicegen` for the voice, the model and the knobs. Nothing else
# couples them, so a rename on one side fails silently on the other: the synthesis call
# raises, `narrate` catches it, and the round is published with its line as text and no
# audio. The game looks fine and simply never speaks. These pin that seam.


def test_voicegen_exposes_everything_voice_py_reaches_for():
    """The names `VoiceStudio._synthesize` uses, checked without an API key in sight."""
    from app.game import voicegen

    for attr in (
        "ELEVENLABS_API_URL",
        "OUTPUT_FORMAT",
        "MODEL_ID",
        "TAGGED_MODEL_ID",
        "VOICE_STABILITY",
        "VOICE_SIMILARITY_BOOST",
        "VOICE_STYLE",
        "VOICE_SPEAKER_BOOST",
        "REQUEST_TIMEOUT_SECONDS",
        "pick_voice_id",
    ):
        assert hasattr(voicegen, attr), f"voice.py reads voicegen.{attr}, which is gone"


def test_pick_voice_id_returns_a_configured_voice():
    from app.game import voicegen

    ids = set(voicegen.VOICE_IDS.values())
    assert ids, "no voices configured"
    for _ in range(50):
        assert voicegen.pick_voice_id() in ids


def test_pick_voice_id_never_repeats_immediately():
    """Several voices exist so the announcer changes; twice in a row reads as a bug."""
    from app.game import voicegen

    picks = [voicegen.pick_voice_id() for _ in range(60)]
    repeats = [(i, a) for i, (a, b) in enumerate(zip(picks, picks[1:])) if a == b]
    assert repeats == [], f"same voice twice running at {repeats}"
    assert len(set(picks)) > 1, "it should actually vary"


def test_pick_voice_id_survives_a_single_configured_voice(monkeypatch):
    """Excluding the last one must not leave nothing to choose from."""
    from app.game import voicegen

    monkeypatch.setattr(voicegen, "VOICE_IDS", {"Only": "solo-voice"})
    monkeypatch.setattr(voicegen, "_last_voice_id", "solo-voice")
    assert voicegen.pick_voice_id() == "solo-voice"


async def test_synthesis_asks_elevenlabs_for_a_real_voice(tmp_path, monkeypatch):
    """End to end through `VoiceStudio._synthesize`, with the HTTP call captured.

    The URL has to end in an id from VOICE_IDS. When `voicegen.VOICE_ID` was deleted this
    raised AttributeError instead, and every round went out silent.
    """
    import httpx

    from app.config import Settings
    from app.game import voicegen
    from app.game.voice import VoiceStudio

    seen = {}

    class FakeResponse:
        content = b"ID3audio"

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, **kw):
            seen["url"] = url
            seen["model_id"] = kw["json"]["model_id"]
            seen["text"] = kw["json"]["text"]
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    settings = Settings(media_dir=tmp_path / "media", elevenlabs_api_key="k")
    studio = VoiceStudio(settings=settings, store=_VoiceStoreStub())

    audio = await studio._synthesize("Look angry.", tagged=False)
    assert audio == b"ID3audio"
    assert seen["text"] == "Look angry."
    assert seen["model_id"] == voicegen.MODEL_ID
    assert seen["url"].rsplit("/", 1)[-1] in set(voicegen.VOICE_IDS.values())


def test_the_prompts_source_speaks_the_prompt_itself(monkeypatch):
    """`TEXT_SOURCE = "prompts"` means "say the prompt", not "say something about it".

    This read `f"... prompt.text"` for a while, which asked ElevenLabs to pronounce the
    literal words "prompt dot text" while the screen showed the real line.
    """
    from app.game import voicegen

    spoken = {}

    def fake_generate_voice(text, **kw):
        spoken["text"] = text
        return tmp_file()

    def tmp_file():
        from pathlib import Path

        return Path("/dev/null")

    monkeypatch.setattr(voicegen, "TEXT_SOURCE", "prompts")
    monkeypatch.setattr(voicegen, "generate_voice", fake_generate_voice)

    text, _ = voicegen.generate_for_prompt()
    assert spoken["text"] == text, "the spoken line must be the prompt that was returned"
    assert "prompt.text" not in spoken["text"]
    assert "[" not in spoken["text"], "MODEL_ID is not tag-aware; tags would be read aloud"


class _VoiceStoreStub:
    async def write(self, audio_id, data):
        return None
