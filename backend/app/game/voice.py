"""Uncle Damage's voice, as something the game loop can actually call.

`geminiprompts.py` and `voicegen.py` are runnable scripts: they pick their own prompt and
block while they call out to Gemini and ElevenLabs. Neither is importable from the round
driver as-is -- `voicegen.generate_for_prompt` would narrate a *different* prompt than the
round the players are playing, and its synchronous `httpx.post` would stall the event loop
and every state broadcast with it.

This wraps them for the engine:
  * narrates the prompt the round actually chose,
  * never blocks the loop (Gemini goes to a thread, ElevenLabs over async httpx),
  * degrades one step at a time -- no Gemini key means the prompt text is spoken as
    written, no ElevenLabs key means the line is published as text with no audio.

Generation takes seconds, so the engine starts it as a background task and patches the
round when it lands. A round is never delayed waiting for audio.

Both vendor modules are imported lazily, inside the methods that call them: the game
server itself must start and run with no AI SDK installed at all.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.config import Settings
from app.game.prompts import Prompt
from app.game.store import new_id

log = logging.getLogger(__name__)

# Mirrors voicegen.OUTPUT_EXT. Duplicated rather than imported because importing voicegen
# at module scope would drag in google-genai (see the module docstring).
AUDIO_EXT = "mp3"


@dataclass(frozen=True)
class Narration:
    """What the round gets to show. `audio_id` is None when TTS is unavailable."""

    line: str
    audio_id: str | None


class VoiceStore:
    """Generated audio on local disk, keyed by id, with a TTL reaper.

    Same shape as `capture.media.MediaStore` on purpose: swap both for object storage by
    reimplementing write/read/find.
    """

    def __init__(self, root: Path, ttl_seconds: int) -> None:
        self.root = root
        self.ttl_seconds = ttl_seconds
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, audio_id: str) -> Path:
        return self.root / f"{audio_id}.{AUDIO_EXT}"

    async def write(self, audio_id: str, data: bytes) -> Path:
        path = self.path_for(audio_id)
        await asyncio.to_thread(path.write_bytes, data)
        return path

    async def read(self, path: Path) -> bytes:
        return await asyncio.to_thread(path.read_bytes)

    def find(self, audio_id: str) -> Path | None:
        path = self.path_for(audio_id)
        return path if path.is_file() else None

    async def reap_forever(self, interval_seconds: int = 120) -> None:
        while True:
            try:
                await asyncio.sleep(interval_seconds)
                await asyncio.to_thread(self._reap_once)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("voice reaper iteration failed")

    def _reap_once(self) -> None:
        cutoff = time.time() - self.ttl_seconds
        for path in self.root.glob(f"*.{AUDIO_EXT}"):
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink(missing_ok=True)
            except OSError:
                continue


class VoiceStudio:
    def __init__(self, store: VoiceStore, settings: Settings) -> None:
        self.store = store
        self.settings = settings

    @property
    def writes_lines(self) -> bool:
        """Gemini writes the spoken line instead of reading prompts.py verbatim."""
        return bool(self.settings.gemini_api_key)

    @property
    def speaks(self) -> bool:
        return bool(self.settings.elevenlabs_api_key)

    @property
    def enabled(self) -> bool:
        """False when there is nothing to add: no keys at all, or switched off."""
        return self.settings.voice_enabled and (self.writes_lines or self.speaks)

    async def narrate(self, prompt: Prompt) -> Narration | None:
        """Write and voice the line for `prompt`. Never raises; returns None when off."""
        if not self.enabled:
            return None

        line = prompt.text
        tagged = False
        if self.writes_lines:
            try:
                from app.game import geminiprompts

                # Synchronous SDK call: to a thread, so the round driver and every state
                # broadcast keep running while Gemini thinks.
                line = await asyncio.to_thread(geminiprompts.generate_for_prompt, prompt)
                tagged = True  # the line carries [emotion] tags, so it needs the v3 model
            except Exception:
                log.warning(
                    "gemini voice line failed, falling back to the prompt text", exc_info=True
                )
                line, tagged = prompt.text, False

        if not self.speaks:
            # Text-only narration is still worth publishing.
            return Narration(line=line, audio_id=None)

        try:
            audio = await self._synthesize(line, tagged)
        except Exception:
            log.warning("elevenlabs synthesis failed; publishing the line as text", exc_info=True)
            return Narration(line=line, audio_id=None)

        audio_id = new_id("a")
        await self.store.write(audio_id, audio)
        return Narration(line=line, audio_id=audio_id)

    async def _synthesize(self, text: str, tagged: bool) -> bytes:
        """`tagged` picks the tag-aware model, needed when the line carries [emotion] tags."""
        from app.game import voicegen

        async with httpx.AsyncClient(timeout=voicegen.REQUEST_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                # Asked for per line, so each round gets a different announcer.
                f"{voicegen.ELEVENLABS_API_URL}/{voicegen.pick_voice_id()}",
                params={"output_format": voicegen.OUTPUT_FORMAT},
                headers={
                    "xi-api-key": self.settings.elevenlabs_api_key or "",
                    "Accept": "audio/mpeg",
                },
                json={
                    "text": text,
                    "model_id": voicegen.TAGGED_MODEL_ID if tagged else voicegen.MODEL_ID,
                    "voice_settings": {
                        "stability": voicegen.VOICE_STABILITY,
                        "similarity_boost": voicegen.VOICE_SIMILARITY_BOOST,
                        "style": voicegen.VOICE_STYLE,
                        "use_speaker_boost": voicegen.VOICE_SPEAKER_BOOST,
                    },
                },
            )
            resp.raise_for_status()
            return resp.content
