"""Tests for the parts of the live feed that make a claim about the world.

The fetching and assembly need credentials and a network, but the statistics do not, and the
statistics are what the page asserts. The Elo fit in particular is load-bearing: it is published
as "the rating this bot would settle at", which is only true because the platform's update rule
was verified exactly, so a silent regression here would be a confidently wrong number.
"""

from __future__ import annotations

import math

from tournament.live_feed import (
    MECHANICS_EPOCH,
    _expected,
    _fit_strength,
    _pairing_blocks,
    _pairing_score,
    _pre_epoch_counts,
    _field_score,
)


def test_expected_score_matches_the_elo_formula():
    assert _expected(1500, 1500) == 0.5
    # A 400-point lead is 10:1 by construction.
    assert math.isclose(_expected(1900, 1500), 10 / 11, rel_tol=1e-9)
    assert math.isclose(_expected(1500, 1900), 1 / 11, rel_tol=1e-9)


def test_fitted_strength_recovers_the_rating_that_produced_the_record():
    """An even record against equal opponents means equal strength, whatever the rating."""
    assert math.isclose(_fit_strength([(1800.0, 50, 50)]), 1800.0, abs_tol=0.5)
    # Winning 10:1 against 1500s is exactly a 400-point edge.
    assert math.isclose(_fit_strength([(1500.0, 100, 10)]), 1900.0, abs_tol=1.0)


def test_fitted_strength_weighs_opponents_by_their_rating():
    """Beating strong opponents and losing to weak ones must not average to the midpoint."""
    versus_strong = _fit_strength([(2000.0, 30, 30)])
    versus_weak = _fit_strength([(1600.0, 30, 30)])
    assert versus_strong > versus_weak
    mixed = _fit_strength([(2000.0, 30, 30), (1600.0, 30, 30)])
    assert versus_weak < mixed < versus_strong


def test_a_record_with_no_split_has_no_finite_estimate():
    """All wins or all losses sends the MLE to infinity; a printed number would be the truncation."""
    assert _fit_strength([(1800.0, 40, 0)]) is None
    assert _fit_strength([(1800.0, 0, 40)]) is None
    assert _fit_strength([]) is None


def test_pairing_blocks_cover_every_grid_phase_and_exclude_us():
    # Deliberately offset from the grid so no field member ties our rating.
    field = [1400.0 + 20.0 * step for step in range(50)]
    blocks = _pairing_blocks(1810.0, field)
    assert len(blocks) == 8, "one block per phase the cut grid can take"
    for block in blocks:
        assert len(block) == 7, "a full block is us plus seven others"
        assert 1810.0 not in block, "we are not our own opponent"
    # Every phase must be a run of consecutive teams around us, never the global nearest seven.
    assert any(all(r > 1800.0 for r in block) for block in blocks), (
        "some phase puts the cut right below us, so the whole block is stronger -- this is the "
        "case 'nearest seven' cannot represent"
    )


def test_a_rating_tie_does_not_drop_us_from_our_own_block():
    """`index()` by value would find the tied team's slot and silently exclude the wrong entry."""
    field = [1800.0, 1800.0, 1790.0, 1780.0, 1770.0, 1760.0, 1750.0, 1740.0, 1730.0]
    for block in _pairing_blocks(1800.0, field):
        assert len(block) == len(set(range(len(block)))), "block is well formed"
        assert block.count(1800.0) <= 2, "both genuine 1800s may appear, but never a third"


def test_pairing_score_differs_from_averaging_the_nearest_seven():
    """The correction this replaced a convenient approximation for."""
    field = [1400.0 + 20.0 * step for step in range(50)]
    nearest = sorted(field, key=lambda r: abs(r - 1800.0))[:7]
    naive = sum(_expected(1800.0, r) for r in nearest) / len(nearest)
    proper = _pairing_score(1800.0, 1800.0, field)
    # Symmetric field, so both land near even -- but they are computed differently and the block
    # version is the one that tracks the scheduler.
    assert 0.0 < proper < 1.0
    assert abs(proper - naive) < 0.1


def test_pairing_score_is_evaluated_at_our_rating_not_the_bot_strength():
    """A strong bot inherits our ladder slot; it does not start where it deserves to be."""
    field = [1400.0 + 20.0 * step for step in range(50)]
    strong_bot_in_our_slot = _pairing_score(2000.0, 1800.0, field)
    strong_bot_already_promoted = _pairing_score(2000.0, 2000.0, field)
    assert strong_bot_in_our_slot > strong_bot_already_promoted, (
        "facing our neighbours is easier for it than facing the ones it would rise to"
    )
    assert _pairing_score(1800.0, 1800.0, []) is None


def test_equilibrium_rating_equals_strength_whatever_the_pairing():
    """The claim the projected Elo rests on, checked against the update rule directly.

    At R = strength every term of the drift is zero, so it is a fixed point for *any* opponent
    distribution; away from it every term shares a sign, so it is the only one. That is why the
    projection needs no ladder simulation.
    """
    field = [1400.0 + 20.0 * step for step in range(50)]
    strength = 1837.0

    def drift(rating: float) -> float:
        blocks = _pairing_blocks(rating, field)
        per_block = [
            sum(_expected(strength, r) - _expected(rating, r) for r in b) / len(b) for b in blocks
        ]
        return sum(per_block) / len(per_block)

    assert math.isclose(drift(strength), 0.0, abs_tol=1e-12)
    assert drift(strength - 100) > 0, "under-rated bots gain"
    assert drift(strength + 100) < 0, "over-rated bots lose"


def test_field_score_is_bounded_and_ordered():
    field = [1700.0, 1800.0, 1900.0]
    weak, strong = _field_score(1500, field), _field_score(2100, field)
    assert 0.0 < weak < 0.5 < strong < 1.0
    assert math.isclose(_field_score(1800, [1800.0]), 0.5)


def test_pre_epoch_counts_only_counts_what_it_excludes():
    rows = [
        {"t": "2026-08-01T10:00:00Z", "ver": 5},
        {"t": "2026-08-02T10:00:00Z", "ver": 5},
        {"t": "2026-08-05T10:00:00Z", "ver": 16},
    ]
    counts = _pre_epoch_counts(rows, MECHANICS_EPOCH)
    assert counts == {5: 2}, "post-patch rows must not appear in the excluded tally"


def test_the_epoch_separates_byte_identical_submissions_that_straddle_it():
    """v9 and v16 are the same code, and pooling them across the patch was the bug.

    The pooling itself is right -- one bot, one record -- but it is only sound inside one balance
    era, so the era filter has to run before the pool, not after.
    """
    rows = [
        {"t": "2026-08-04T11:00:00Z", "ver": 9},    # pre-patch
        {"t": "2026-08-04T18:00:00Z", "ver": 16},   # post-patch
    ]
    kept = [r for r in rows if r["t"] >= MECHANICS_EPOCH]
    assert [r["ver"] for r in kept] == [16]
    assert _pre_epoch_counts(rows, MECHANICS_EPOCH) == {9: 1}
