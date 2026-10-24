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
    # Hard wall-clock cap on one game. The round driver stops starting rounds once this
    # is spent and truncates a round that would overrun it, so a game can never outlive
    # its timer no matter how ROUND_SECONDS and ROUNDS_PER_GAME are set.
    game_seconds: int = 120
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
