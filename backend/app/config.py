from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Every field is overridable via env var or backend/.env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- game loop -------------------------------------------------------
    # Defaults for a new room; the host can change both from the lobby. Round 1 runs for
    # round_seconds and every round after it is round_decrement_seconds shorter.
    round_seconds: int = 20
    round_decrement_seconds: int = 0
    # The default for a new room; the host can switch it to 5 or 10 in the lobby.
    rounds_per_game: int = 5
    intermission_seconds: int = 4
    # Hard wall-clock cap on one game. The round driver stops starting rounds once this
    # is spent and truncates a round that would overrun it, so a game can never outlive
    # its timer no matter how ROUND_SECONDS and ROUNDS_PER_GAME are set.
    game_seconds: int = 130

    # --- blitz -----------------------------------------------------------
    # "classic" (shared rounds) or "blitz" (one clock, everyone async through a shared
    # sequence). The default for a new room; the host switches it in the lobby.
    game_mode: str = "classic"
    # The one global clock a blitz runs for. game_seconds is ignored in blitz.
    blitz_seconds: int = 150
    # How long one face may be worked on before it rolls over on its own.
    blitz_face_seconds: int = 12
    # Confidence a read needs to pass a face. Kept modest on purpose: `judge` reports the
    # top expression's confidence, and presage.STAND_INS maps `disappointed` onto `sad`,
    # so a high bar makes some targets feel unfair. Classic does not use this at all.
    blitz_pass_confidence: float = 0.35
    # Whether players see rivals' running totals mid-blitz. A UI preference, not a privacy
    # control: every snapshot carries every Player.points regardless. See app/game/hub.py.
    blitz_live_leaderboard: bool = True
    # Deliberately not lobby-exposed: a free skip on a cooldown is a rule, not a dial.
    blitz_skip_cooldown_seconds: int = 5
    # Floor on the generated sequence, so a short blitz still has plenty of faces.
    blitz_sequence_min_length: int = 90
    # How often the blitz driver sweeps for faces whose time ran out. It publishes only
    # when something changed, so an idle tick costs nothing on the wire.
    blitz_tick_ms: int = 250

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
    # PROCESSOR=presage: the SmartSpectra sidecar pushes each player's expression here,
    # authenticated with this shared token (set the same value in the sidecar's env).
    presage_ingest_token: str | None = None
    # A frame is judged by the player's newest reading only if it is at most this old;
    # older means the face left the frame or the sidecar stopped, and the frame misses.
    presage_max_age_ms: int = 1500

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
    # Each browser's best final score. Defaults to MEDIA_DIR/highscores.json, which the
    # media reapers leave alone (they only delete .jpg and .mp3).
    highscores_path: Path | None = None
    media_ttl_seconds: int = 900

    # --- http ------------------------------------------------------------
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
