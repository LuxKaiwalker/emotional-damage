from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Every field is overridable via env var or backend/.env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- game loop -------------------------------------------------------
    round_seconds: int = 20
    rounds_per_game: int = 3
    intermission_seconds: int = 4

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
