"""Placeholder round prompts. Swap for whatever your game actually asks players to do."""

import random

PROMPTS = (
    "Look as offended as possible",
    "Fake a convincing smile",
    "Act like you just saw the bill",
    "Maximum disappointment",
    "Pretend you understood the joke",
    "Deadpan stare",
)


def pick_prompt(round_no: int, exclude: set[str] | None = None) -> str:
    pool = [p for p in PROMPTS if not exclude or p not in exclude] or list(PROMPTS)
    return random.choice(pool)
