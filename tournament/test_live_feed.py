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
    PAIRING_KERNEL,
    _pairing_weights,
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


def test_pairing_weights_follow_the_measured_kernel():
    field = [1400.0 + 20.0 * step for step in range(50)]
    weights = _pairing_weights(1810.0, field)
    total = sum(w for _, w in weights)
    assert math.isclose(total, sum(PAIRING_KERNEL.values()), rel_tol=1e-9)
    assert 1810.0 not in [r for r, _ in weights], "we are not our own opponent"
    # Nearest neighbours must carry the most weight, matching the measured decay.
    byrating = dict(weights)
    assert byrating[1820.0] > byrating[1900.0] > byrating[1960.0]


def test_pairing_weight_is_not_lost_at_the_top_of_the_ladder():
    """We sit around fourth, so half of every offset falls off the table."""
    field = [2000.0 - 20.0 * step for step in range(40)]
    top = _pairing_weights(2100.0, field)          # above everyone
    assert math.isclose(sum(w for _, w in top), sum(PAIRING_KERNEL.values()), rel_tol=1e-9), (
        "missing side's weight must move to the side that exists, not vanish"
    )
    # And it really is drawn downward only.
    assert all(r < 2100.0 for r, _ in top)


def test_a_rating_tie_does_not_make_us_our_own_opponent():
    field = [1800.0, 1800.0, 1790.0, 1780.0, 1770.0, 1760.0, 1750.0, 1740.0, 1730.0]
    weights = _pairing_weights(1800.0, field)
    # Two genuine 1800s exist besides us; we must see at most those two, never a third.
    assert sum(1 for r, _ in weights if r == 1800.0) <= 2


def test_the_kernel_reaches_further_than_a_block_of_eight_could():
    """The observation that falsified the block model: a pairing eight ranks away."""
    assert max(PAIRING_KERNEL) == 11
    assert PAIRING_KERNEL[8] > 0, "we were drawn against a team eight places below us"


def test_equilibrium_rating_equals_strength_whatever_the_pairing():
    """The claim the projected Elo rests on, checked against the update rule directly.

    At R = strength every term of the drift is zero, so it is a fixed point for *any* opponent
    distribution; away from it every term shares a sign, so it is the only one. That is why the
    projection needs no ladder simulation.
    """
    field = [1400.0 + 20.0 * step for step in range(50)]
    strength = 1837.0

    def drift(rating: float) -> float:
        weights = _pairing_weights(rating, field)
        total = sum(w for _, w in weights)
        return sum(
            w * (_expected(strength, r) - _expected(rating, r)) for r, w in weights
        ) / total

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
