"""The shared blitz order: `prompts.build_sequence`.

Pure properties only -- no engine, no HTTP. The end-to-end fairness check (two players at
different rates seeing the same prompt at the same face number) lives in test_blitz_flow.py,
because that one is about what reaches the wire.
"""

import random

from app.game.prompts import (
    INDISTINGUISHABLE,
    PROMPTS,
    TARGET_LABELS,
    build_sequence,
    family,
)


def test_length_is_exact():
    for length in (0, 1, 17, 18, 90, 200):
        assert len(build_sequence(length, random.Random(0))) == length


def test_no_two_neighbours_can_be_satisfied_by_one_face():
    """The load-bearing one: a held reading must never pass the next face for free.

    Compares *families*, not raw labels -- which is the whole point. `disappointed` is
    read off `sad` (presage.STAND_INS), so a sequence can satisfy "no repeated target"
    and still hand out a free pass by putting those two side by side. Many seeds,
    because this is a property of the construction, not of one lucky shuffle.
    """
    for seed in range(100):
        sequence = build_sequence(200, random.Random(seed))
        free = [
            (i, a.target, b.target)
            for i, (a, b) in enumerate(zip(sequence, sequence[1:]))
            if b.target in family(a.target)
        ]
        assert free == [], f"seed {seed} gives a free pass at {free}"


def test_the_stand_in_pair_really_is_a_hazard():
    """Guards the test above from being vacuous.

    If `sad` and `disappointed` stopped being one face, the family check would pass for
    a reason that has nothing to do with the rule it is meant to pin.
    """
    assert frozenset({"sad", "disappointed"}) in INDISTINGUISHABLE
    assert family("sad") == family("disappointed") == frozenset({"sad", "disappointed"})
    assert family("happy") == frozenset({"happy"}), "unrelated targets stay on their own"


def test_indistinguishable_targets_still_both_appear():
    """Collapsing them for adjacency must not drop either from the game."""
    sequence = build_sequence(200, random.Random(0))
    targets = {p.target for p in sequence}
    for group in INDISTINGUISHABLE:
        assert group <= targets, f"{group - targets} never gets asked for"


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
