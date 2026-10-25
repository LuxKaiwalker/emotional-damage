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
    Prompt("angry", "Look angry, like you just saw your ex with someone else."),
    Prompt("angry", "Look angry, like someone started slandering a close friend."),
    Prompt("contempt", "Look contemptful, like someone just shot down your brilliant idea."),
    Prompt("contempt", "Look contemptful, like someone just suggested the dumbest idea."),
    Prompt("disgusted", "Look disgusted, like you've just seen some rotten fish."),
    Prompt("disgusted", "Look disgusted, like you've just seen the worst movie of your life."),
    Prompt("disappointed", "Look disappointed, like an Asian parent seeing their child fail an exam."),
    Prompt("disappointed", "Look disappointed, like you just got rejected from a job that you really wanted."),
    Prompt("scared", "Look scared, like you just saw an accident happened."),
    Prompt("scared", "Look scared, like you just saw an accident."),
    Prompt("sad", "Look sad, like you just lost a massive hackathon because someone nuked the repo."),
    Prompt("sad", "Look sad, like you just heard some terrible news."),
    Prompt("surprised", "Look surprised, like you just saw a ghost!"),
    Prompt("surprised", "Look surprised, like you just heard that someone you know did something unexpected."),
    Prompt("happy", "Look happy, like you just got a promotion at work!"),
    Prompt("happy", "Look happy, like you just got a job you really wanted!"),
    Prompt("happy", "Look happy, like you just found out that you got a first class for your degree!"),
)

# Every label the game knows about. `app.processing.dummy` draws its fake reads from this
# list so that the placeholder processor can actually hit a target; a real processor should
# emit labels from here too, or no answer will ever be judged correct.
TARGET_LABELS = tuple(dict.fromkeys(p.target for p in PROMPTS))


# Targets no processor can tell apart, so the blitz sequence must never put two of them
# next to each other. `processing.presage` has no `disappointed` class and reads it off
# `sad` (its STAND_INS), which means one held sad face satisfies both targets -- and in
# blitz, where passing advances the cursor at once and a reading stays valid for
# PRESAGE_MAX_AGE_MS, that is two faces for the price of one.
#
# Declared here rather than in the processor because the sequence is built from this
# table and `processing` imports this module, not the other way round. `presage.py`
# asserts at import that its own stand-ins are covered by this list.
INDISTINGUISHABLE: tuple[frozenset[str], ...] = (frozenset({"sad", "disappointed"}),)


def family(target: str) -> frozenset[str]:
    """The set of targets a processor would read the same way as `target`, itself included."""
    for group in INDISTINGUISHABLE:
        if target in group:
            return group
    return frozenset({target})


def pick_prompt(round_no: int, exclude: set[str] | None = None) -> Prompt:
    """Pick a prompt, avoiding the given prompt texts when there is anything left to pick."""
    pool = [p for p in PROMPTS if not exclude or p.text not in exclude] or list(PROMPTS)
    return random.choice(pool)

def grab_all_prompts() -> list[Prompt]:
    """Return a list of all prompts."""
    return list(PROMPTS)

def build_sequence(length: int, rng: random.Random | None = None) -> list[Prompt]:
    """The fixed order every player in a blitz walks, built once at game start.

    Drawn from repeatedly shuffled copies of the whole table, so no prompt is asked twice
    until all of them have been -- and player 7's twelfth face is player 1's twelfth face,
    which is the only thing making an asynchronous race fair.

    One invariant beyond variety: **no two consecutive entries can be satisfied by the
    same face**. A Presage reading stays valid for PRESAGE_MAX_AGE_MS after it lands, and
    passing a face advances the cursor immediately, so a neighbour the held expression
    also satisfies would pass for free. Note that is a weaker condition than "a different
    `target`": see INDISTINGUISHABLE, where `sad` and `disappointed` are one face as far
    as any processor is concerned. `rng` is for the tests; production uses the
    module-level `random`.
    """
    picker = rng or random
    pool: list[Prompt] = []
    sequence: list[Prompt] = []
    while len(sequence) < length:
        previous = family(sequence[-1].target) if sequence else frozenset()
        index = next((i for i, p in enumerate(pool) if p.target not in previous), None)
        if index is None:
            # Empty, or everything left reads as the last face. Refill and let the
            # leftovers wait their turn: a fresh block always holds another family.
            block = list(PROMPTS)
            picker.shuffle(block)
            pool.extend(block)
            continue
        sequence.append(pool.pop(index))
    return sequence
