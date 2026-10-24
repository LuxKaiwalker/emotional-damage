from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Every field is overridable via env var or backend/.env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- game loop -------------------------------------------------------
    round_seconds: int = 20
    # The default for a new room; the host can switch it to 5 or 10 in the lobby.
    rounds_per_game: int = 5
    intermission_seconds: int = 4
    # Hard wall-clock cap on one game. The round driver stops starting rounds once this
    # is spent and truncates a round that would overrun it, so a game can never outlive
    # its timer no matter how ROUND_SECONDS and ROUNDS_PER_GAME are set.
    game_seconds: int = 130
    # What one correct answer is worth. The rule is one point per correct round.
    points_per_correct: int = 1

    # --- rooms -----------------------------------------------------------
    # Join codes are letters only, so they survive being read out loud.
    join_code_length: int = 4
    max_players_per_room: int = 12
    # A room nobody is connected to is destroyed once it has been empty this long.
    # The grace period is what lets a player reload the page without losing the room.
    empty_room_grace_seconds: int = 60
    room_reap_interval_seconds: int = 5

    # --- capture / upload ------------------------------------------------
    # Advisory tick pushed to clients in the state snapshot.
    capture_interval_ms: int = 500
    # Enforced server-side. Frames arriving faster than this per player are skipped.
    min_frame_interval_ms: int = 250
    max_frame_bytes: int = 2 * 1024 * 1024

    # --- processing ------------------------------------------------------
    processor: str = "dummy"
    worker_count: int = 2
    queue_maxsize: int = 64
    # Vision model for PROCESSOR=gemini. Needs GEMINI_API_KEY.
    gemini_vision_model: str = "gemini-2.5-flash"

    # --- client-reported vitals ------------------------------------------
    # Accepted, stored and broadcast, but never an input to scoring: they come from the
    # player's own browser and nothing can verify them. See app/api/vitals.py.
    vitals_enabled: bool = True
    # Cap on one report, so a client cannot grow the snapshot without bound.
    max_vitals_fields: int = 24

    # --- voice narration --------------------------------------------------
    # Uncle Damage: Gemini writes the round's line, ElevenLabs speaks it. Both steps are
    # optional -- without GEMINI_API_KEY the prompt text is spoken as written, and without
    # ELEVENLABS_API_KEY the line is published as text with no audio.
    voice_enabled: bool = True
    voice_ttl_seconds: int = 1800

    # --- third-party keys -------------------------------------------------
    # Read from the environment or backend/.env. Absent keys disable the feature that
    # needs them rather than failing the request.
    gemini_api_key: str | None = None
    elevenlabs_api_key: str | None = None

    # --- media -----------------------------------------------------------
    media_dir: Path = Path(".media")
    media_ttl_seconds: int = 900

    # --- http ------------------------------------------------------------
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
