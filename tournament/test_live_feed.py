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
    MIN_GAMES_PER_CONTEXT,
    _expected,
    _fit_selection_bonus,
    _shrink_towards_the_field,
    _fit_strength,
    PAIRING_KERNEL,
    _equilibrium,
    _overdispersion,
    _pairing_weights,
    _pairing_score,
    _pre_epoch_counts,
    _field_score,
)


def _games(kind, opponent_rating, wins, losses, build=1):
    """One match row per game, which is what `_fit_selection_bonus` consumes."""
    return (
        [{"kind": kind, "opp_rating": opponent_rating, "gf": 1, "ga": 0, "ver": build}] * wins
        + [{"kind": kind, "opp_rating": opponent_rating, "gf": 0, "ga": 1, "ver": build}] * losses
    )


def _estimate(elo, half_width):
    return {"estimate": {"elo": elo, "elo_lo": elo - half_width, "elo_hi": elo + half_width}}


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


def test_a_per_row_bonus_is_credited_to_the_row_and_not_to_the_bot():
    """A row fitted with +100 of help must leave the bot 100 weaker than the same row without it."""
    plain = _fit_strength([(1800.0, 75, 25)])
    helped = _fit_strength([(1800.0, 75, 25, 100.0)])
    assert math.isclose(helped, plain - 100.0, abs_tol=0.5)
    # Three-tuples keep meaning exactly what they meant before the field existed.
    assert _fit_strength([(1800.0, 50, 50, 0.0)]) == _fit_strength([(1800.0, 50, 50)])


def test_choosing_easier_opponents_is_charged_to_the_choice_not_the_bot():
    """The whole point: a bot that only outperforms where it picked the fixture is not stronger.

    Same opponent rating throughout, so rating cannot explain the split. The bot scores 75% in
    games it chose and 50% in games it was given; the honest reading is a 1800 bot with a large
    selection bonus, not a 1990 bot.
    """
    n = MIN_GAMES_PER_CONTEXT * 4          # both contexts must clear the per-build threshold
    rows = _games("unrated", 1800.0, int(n * 0.75), int(n * 0.25)) + _games("ladder", 1800.0, n // 2, n // 2)
    bonus = _fit_selection_bonus(rows)
    assert bonus > 100.0
    corrected = _fit_strength(
        [(1800.0, int(n * 0.75), int(n * 0.25), bonus), (1800.0, n // 2, n // 2, 0.0)]
    )
    assert math.isclose(corrected, 1800.0, abs_tol=15.0)


def test_no_selection_advantage_leaves_the_estimate_where_it_was():
    """Identical performance in both contexts must price the choice at nothing."""
    n = MIN_GAMES_PER_CONTEXT
    rows = _games("unrated", 1800.0, n // 2, n // 2) + _games("ladder", 1800.0, n // 2, n // 2)
    assert abs(_fit_selection_bonus(rows)) < 15.0


def test_the_bonus_is_not_guessed_from_a_thin_sample():
    """Below the threshold, or with one context missing, the old one-parameter answer stands."""
    assert _fit_selection_bonus(_games("unrated", 1800.0, 8, 4) + _games("ladder", 1800.0, 8, 4)) == 0.0
    assert _fit_selection_bonus(_games("unrated", 1800.0, 500, 200)) == 0.0
    assert _fit_selection_bonus([]) == 0.0


def test_the_bonus_is_identified_within_a_build_not_across_builds():
    """Two builds of different strength, neither favoured by its own fixture mix, price at nothing.

    This is the confound that made the pooled fit read +46 Elo. A weak build farmed heavily and a
    strong build mostly drawn by the scheduler will, under a single shared strength, look exactly
    like a team that overperforms in the games it picks. Fixed effects must not be fooled by it.
    """
    n = MIN_GAMES_PER_CONTEXT
    weak = (_games("unrated", 1800.0, int(n * 0.3), int(n * 0.7), build=1) * 3
            + _games("ladder", 1800.0, int(n * 0.3), int(n * 0.7), build=1))
    strong = (_games("unrated", 1800.0, int(n * 0.7), int(n * 0.3), build=2)
              + _games("ladder", 1800.0, int(n * 0.7), int(n * 0.3), build=2) * 3)
    assert abs(_fit_selection_bonus(weak + strong)) < 20.0


def test_a_context_that_cannot_be_told_apart_does_not_run_to_the_boundary():
    """An all-win chosen record would send the bonus to infinity; it must decline instead."""
    n = MIN_GAMES_PER_CONTEXT
    rows = _games("unrated", 1800.0, n, 0) + _games("ladder", 1800.0, n // 2, n // 2)
    assert _fit_selection_bonus(rows) == 0.0


def test_a_lone_high_estimate_is_pulled_towards_the_rest():
    """The winner's curse correction: an outlier on thin evidence is mostly noise."""
    bots = [_estimate(1800.0, 20.0) for _ in range(4)] + [_estimate(2000.0, 120.0)]
    _shrink_towards_the_field(bots)
    outlier = bots[-1]["estimate"]
    # `elo` is untouched: the farm ranks on it and must keep seeing the raw fit.
    assert outlier["elo"] == 2000.0
    assert outlier["elo_settled"] < 1950.0
    assert outlier["shrinkage"] > 0.25
    # The interval travels with the point estimate; it is the same width of evidence.
    assert math.isclose(outlier["elo_settled_hi"] - outlier["elo_settled_lo"], 240.0, abs_tol=1e-6)
    assert math.isclose(outlier["elo_settled"] - outlier["elo_settled_lo"], 120.0, abs_tol=1e-6)


def test_a_precise_estimate_barely_moves():
    """Shrinkage is proportional to a build's own uncertainty, not applied as a flat haircut."""
    bots = [_estimate(1700.0, 15.0), _estimate(1800.0, 15.0),
            _estimate(1900.0, 15.0), _estimate(2000.0, 15.0)]
    _shrink_towards_the_field(bots)
    assert all(b["estimate"]["shrinkage"] < 0.1 for b in bots)
    assert math.isclose(bots[-1]["estimate"]["elo_settled"], 2000.0, abs_tol=15.0)


def test_builds_that_differ_by_no_more_than_their_error_bars_collapse_to_the_mean():
    """No real spread left after removing sampling noise means no build is distinguishable."""
    bots = [_estimate(elo, 200.0) for elo in (1750.0, 1800.0, 1820.0, 1850.0)]
    _shrink_towards_the_field(bots)
    assert all(math.isclose(b["estimate"]["elo_settled"], 1805.0, abs_tol=1.0) for b in bots)
    assert all(b["estimate"]["shrinkage"] == 1.0 for b in bots)
    # Ranking is untouched, so the farm can still tell its candidates apart.
    assert [b["estimate"]["elo"] for b in bots] == [1750.0, 1800.0, 1820.0, 1850.0]


def test_too_few_estimates_to_separate_spread_from_noise_are_left_alone():
    bots = [_estimate(1800.0, 20.0), _estimate(2000.0, 20.0)]
    _shrink_towards_the_field(bots)
    assert bots[-1]["estimate"]["elo"] == 2000.0
    assert "elo_settled" not in bots[-1]["estimate"]


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


def test_a_hard_counter_inside_the_pairing_range_drags_the_equilibrium_down():
    """The objection that broke the one-parameter story.

    A bot can have a perfectly respectable overall strength and still be dragged below it by one
    opponent it never beats, provided the ladder keeps drawing them together. Under the
    single-parameter model that is impossible by construction, which is exactly what was wrong
    with it.
    """
    field = [1900.0, 1880.0, 1860.0, 1840.0, 1820.0, 1800.0, 1780.0, 1760.0, 1740.0, 1720.0]
    even = [(r, 25, 25) for r in field[:5]]
    fair = _equilibrium(even, 1840.0, field)

    cursed = even + [(1860.0, 0, 40)]      # a near neighbour we simply cannot beat
    haunted = _equilibrium(cursed, 1840.0, field)
    assert haunted < fair - 5, "losing every game to a team we keep drawing must cost rating"


def test_no_matchup_structure_collapses_to_the_one_parameter_answer():
    """When results are pure Elo, the fixed point must reproduce plain strength."""
    field = [1900.0, 1880.0, 1860.0, 1840.0, 1820.0, 1800.0, 1780.0, 1760.0]
    strength = 1850.0
    # Records generated to match the Elo prediction exactly, so dispersion is ~0.
    cells = []
    for r in field[:6]:
        n = 100
        wins = round(n * _expected(strength, r))
        cells.append((r, wins, n - wins))
    assert _overdispersion(cells, strength) < 0.5
    assert math.isclose(_equilibrium(cells, strength, field), strength, abs_tol=12.0)


def test_overdispersion_detects_matchup_structure():
    field = [1900.0, 1850.0, 1800.0, 1750.0]
    clean = [(r, round(40 * _expected(1830.0, r)), 40 - round(40 * _expected(1830.0, r)))
             for r in field]
    lumpy = [(1900.0, 40, 0), (1850.0, 0, 40), (1800.0, 40, 0), (1750.0, 0, 40)]
    assert _overdispersion(clean, 1830.0) < _overdispersion(lumpy, 1830.0)


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
