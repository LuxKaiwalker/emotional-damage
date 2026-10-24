"""Placeholder round prompts. Swap for whatever your game actually asks players to do."""

import random

PROMPTS = (
    "Look Angry, like you just saw your ex with someone else",
    "look contempt",
    "look disgusted",
    "Look disappointed",
    "Look scared",
    "Look sad, like you just a massive hackathon because someone nuked the repo",
    "look surprised! like you just saw a ghost",
)


def pick_prompt(round_no: int, exclude: set[str] | None = None) -> str:
    pool = [p for p in PROMPTS if not exclude or p not in exclude] or list(PROMPTS)
    return random.choice(pool)
