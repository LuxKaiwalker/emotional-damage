"""Turn a game prompt into speech via ElevenLabs and hand back the generated audio file.

Pipeline:  pick_prompt() -> (optional) Gemini writes a tagged line -> ElevenLabs TTS -> mp3 on disk.
TEXT_SOURCE below switches between speaking the raw prompt and a Gemini-written line.

Run directly:  python app/game/voicegen.py   (from backend/)
Import from other modules:  from app.game.voicegen import generate_for_prompt
"""

import os
import sys
import uuid
from pathlib import Path

import httpx

# Make `app.*` importable when this file is run as a script from anywhere.
BACKEND_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_DIR))

from app.game import geminiprompts  # noqa: E402
from app.game.geminiprompts import load_env  # noqa: E402  (shared .env reader)
from app.game.prompts import pick_prompt  # noqa: E402

# --- constants: change these freely --------------------------------------
# "gemini": Gemini writes a funny, tagged line for the prompt's emotion. "prompts": speak prompts.py text as-is.
TEXT_SOURCE = "gemini"
ELEVENLABS_API_URL = "https://api.elevenlabs.io/v1/text-to-speech"
API_KEY_ENV_VAR = "ELEVENLABS_API_KEY"
# "Jessica": a female premade voice that sounds like a real, expressive young woman talking, not a narrator.
# Calmer alternative: "Rachel" = 21m00Tcm4TlvDq8ikWAM. Any female voice ID from your ElevenLabs account works.
VOICE_ID = "cgSgspJ2msm6clMCkdW9"
# Lower stability = more emotional range and intensity; eleven_v3 only takes 0.0 (Creative), 0.5 (Natural)
# or 1.0 (Robust). 0.0 is the most dramatic, 0.5 is safer if takes start sounding unstable or glitchy.
VOICE_STABILITY = 0.0
VOICE_SIMILARITY_BOOST = 0.8  # how closely to stick to the base voice's timbre
VOICE_STYLE = 0.6  # style exaggeration: more expressive delivery (ignored by models that don't support it)
VOICE_SPEAKER_BOOST = True  # extra clarity/presence for the voice (ignored by models that don't support it)
# Plain model: it would read [angry]-style tags out loud, so only use it for untagged text.
MODEL_ID = "eleven_multilingual_v2"  # used for TEXT_SOURCE = "prompts"
# Tag-aware model: interprets Gemini's [emotion] tags as delivery directions instead of speaking them.
TAGGED_MODEL_ID = "eleven_v3"  # used for TEXT_SOURCE = "gemini"
OUTPUT_FORMAT = "mp3_44100_128"
OUTPUT_EXT = "mp3"
OUTPUT_DIR = BACKEND_DIR / ".media" / "voice"
REQUEST_TIMEOUT_SECONDS = 30.0


def generate_voice(text: str, out_dir: Path = OUTPUT_DIR, model_id: str = MODEL_ID) -> Path:
    """Synthesize `text` with ElevenLabs and return the path of the saved audio file.

    `model_id` must be a tag-aware model (TAGGED_MODEL_ID) if `text` contains [emotion] tags.
    """
    load_env(BACKEND_DIR / ".env")  # real env vars win over .env values
    api_key = os.environ.get(API_KEY_ENV_VAR)
    if not api_key:
        raise RuntimeError(f"{API_KEY_ENV_VAR} is not set (expected in backend/.env)")

    resp = httpx.post(
        f"{ELEVENLABS_API_URL}/{VOICE_ID}",
        params={"output_format": OUTPUT_FORMAT},
        headers={"xi-api-key": api_key, "Accept": "audio/mpeg"},
        json={"text": text, "model_id": model_id, "voice_settings": {
                "stability": VOICE_STABILITY,
                "similarity_boost": VOICE_SIMILARITY_BOOST,
                "style": VOICE_STYLE,
                "use_speaker_boost": VOICE_SPEAKER_BOOST,
            },
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{uuid.uuid4().hex}.{OUTPUT_EXT}" # unique filename to avoid collisions
    out_path.write_bytes(resp.content)
    return out_path # returns the output path of the generated audio file.


def generate_for_prompt(round_no: int = 1, exclude: set[str] | None = None) -> tuple[str, Path]:
    """Pick a prompt, voice it (raw or Gemini-written per TEXT_SOURCE), and return (spoken_text, audio_path)."""
    prompt = pick_prompt(round_no, exclude)
    if TEXT_SOURCE == "gemini":
        # Gemini turns the prompt's emotion into a funny line with ElevenLabs tags, so use the tag-aware model.
        text = geminiprompts.generate_for_prompt(prompt)
        return text, generate_voice(text, model_id=TAGGED_MODEL_ID)
    if TEXT_SOURCE == "prompts":
        # No Gemini step: speak the prompt exactly as written in prompts.py.
        return prompt.text, generate_voice(prompt.text)
    raise ValueError(f"TEXT_SOURCE must be 'gemini' or 'prompts', got {TEXT_SOURCE!r}")


if __name__ == "__main__":
    prompt_text, audio_path = generate_for_prompt()
    print(f"text:   {prompt_text}")
    print(f"audio:  {audio_path}")
