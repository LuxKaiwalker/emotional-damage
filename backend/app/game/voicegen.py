"""Turn a game prompt into speech via ElevenLabs and hand back the generated audio file.

Run directly:  python app/game/voice-gen.py   (from backend/)
The filename has a hyphen, so other modules can't `import` it; load it with importlib
or call generate_voice() through whatever wrapper the API layer ends up using.
"""

import os
import sys
import uuid
from pathlib import Path

import httpx

# Make `app.*` importable when this file is run as a script from anywhere.
BACKEND_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_DIR))

from app.game.prompts import pick_prompt  # noqa: E402

# --- constants: change these freely --------------------------------------
ELEVENLABS_API_URL = "https://api.elevenlabs.io/v1/text-to-speech"
API_KEY_ENV_VAR = "ELEVENLABS_API_KEY"
VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # "Rachel", ElevenLabs' stock generic voice
MODEL_ID = "eleven_multilingual_v2"
OUTPUT_FORMAT = "mp3_44100_128"
OUTPUT_EXT = "mp3"
OUTPUT_DIR = BACKEND_DIR / ".media" / "voice"
REQUEST_TIMEOUT_SECONDS = 30.0


def _load_env(path: Path) -> None:
    """Minimal .env reader so we don't need python-dotenv. Real env vars win."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.split(" #")[0].strip().strip("\"'"))


def generate_voice(text: str, out_dir: Path = OUTPUT_DIR) -> Path:
    """Synthesize `text` with ElevenLabs and return the path of the saved audio file."""
    _load_env(BACKEND_DIR / ".env")
    api_key = os.environ.get(API_KEY_ENV_VAR)
    if not api_key:
        raise RuntimeError(f"{API_KEY_ENV_VAR} is not set (expected in backend/.env)")

    resp = httpx.post(
        f"{ELEVENLABS_API_URL}/{VOICE_ID}",
        params={"output_format": OUTPUT_FORMAT},
        headers={"xi-api-key": api_key, "Accept": "audio/mpeg"},
        json={"text": text, "model_id": MODEL_ID, "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{uuid.uuid4().hex}.{OUTPUT_EXT}" # unique filename to avoid collisions
    out_path.write_bytes(resp.content)
    return out_path # returns the output path of the generated audio file.


def generate_for_prompt(round_no: int = 1, exclude: set[str] | None = None) -> tuple[str, Path]:
    """Pick a prompt from prompts.py, voice it, and return (prompt_text, audio_path)."""
    prompt = pick_prompt(round_no, exclude).text
    return prompt, generate_voice(prompt)


if __name__ == "__main__":
    prompt_text, audio_path = generate_for_prompt()
    print(f"prompt: {prompt_text}")
    print(f"audio:  {audio_path}")
