"""The shared blitz order: `prompts.build_sequence`.

Pure properties only -- no engine, no HTTP. The end-to-end fairness check (two players at
different rates seeing the same prompt at the same face number) lives in test_blitz_flow.py,
because that one is about what reaches the wire.
"""

import random

from app.game.prompts import PROMPTS, TARGET_LABELS, build_sequence


def test_length_is_exact():
    for length in (0, 1, 17, 18, 90, 200):
        assert len(build_sequence(length, random.Random(0))) == length


def test_no_two_neighbours_share_a_target():
    """The load-bearing one: a held Presage reading must never pass the next face for free.

    See build_sequence's docstring. Several seeds, because this is a property of the
    construction and not of one lucky shuffle.
    """
    for seed in range(50):
        sequence = build_sequence(200, random.Random(seed))
        repeats = [
            (i, a.target) for i, (a, b) in enumerate(zip(sequence, sequence[1:])) if a.target == b.target
        ]
        assert repeats == [], f"seed {seed} repeated a target at {repeats}"


def test_whole_table_is_asked_before_anything_repeats():
    sequence = build_sequence(len(PROMPTS), random.Random(3))
    assert {p.text for p in sequence} == {p.text for p in PROMPTS}


def test_a_seed_is_reproducible():
    """Everyone gets the same order because it is generated once -- but a seeded build has
    to be stable too, or the tests below it could never assert on a specific sequence."""
    first = build_sequence(40, random.Random(11))
    second = build_sequence(40, random.Random(11))
    assert [p.text for p in first] == [p.text for p in second]


def test_different_seeds_differ():
    a = build_sequence(40, random.Random(1))
    b = build_sequence(40, random.Random(2))
    assert [p.text for p in a] != [p.text for p in b]


def test_every_target_is_reachable():
    """A sequence a processor cannot score is worthless: every target has to be in the
    shared vocabulary `TARGET_LABELS`, which `processing.presage` asserts it can emit."""
    sequence = build_sequence(100, random.Random(5))
    assert {p.target for p in sequence} <= set(TARGET_LABELS)
