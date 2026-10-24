"""Round prompts and the label vocabulary they target.

A round asks for one thing and is scored on one thing: the processor hands back a `label`,
and the player is correct when that label equals the round's `target`. Keeping the prompt
and its target side by side in one table is what stops the two from drifting apart.

Swap the table for whatever your game actually asks players to do -- just make sure every
`target` is a label your processor can actually emit (`TARGET_LABELS` is the shared list).
"""

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class Prompt:
    """What the players are told, and what the processor has to say for them to be right."""

    target: str
    text: str


PROMPTS = (
    "Look Angry, like you just saw your ex with someone else",
    "look contempt",
    "look disgusted",
    "Look disappointed",
    "Look scared",
    "Look sad, like you just a massive hackathon because someone nuked the repo",
    "look surprised! like you just saw a ghost",

)

# Every label the game knows about. `app.processing.dummy` draws its fake reads from this
# list so that the placeholder processor can actually hit a target; a real processor should
# emit labels from here too, or no answer will ever be judged correct.
TARGET_LABELS = tuple(dict.fromkeys(p.target for p in PROMPTS))


def pick_prompt(round_no: int, exclude: set[str] | None = None) -> Prompt:
    """Pick a prompt, avoiding the given prompt texts when there is anything left to pick."""
    pool = [p for p in PROMPTS if not exclude or p.text not in exclude] or list(PROMPTS)
    return random.choice(pool)
