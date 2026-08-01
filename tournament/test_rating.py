"""Validate the rating code against the worked examples in articles/1806.02643v2.pdf.

Every expected value here is stated in the paper, not derived from our implementation. That is the
point: it makes these tests a check on the maths rather than a snapshot of current behaviour.
"""

from __future__ import annotations

import numpy as np
import pytest

from tournament.rating import (
    div,
    evaluate,
    fit_melo,
    grad,
    logit_matrix,
    maxent_nash,
    maxent_rectangular_nash,
    melo_online_update,
    nash_average,
    omega,
    predict,
    rot,
    tally,
    tally_map_tasks,
    win_probability,
)

# Paper, Example 1 (p.6): rock-paper-scissors, where 4.6 = logit(0.99).
RPS = 4.6 * np.array([[0.0, 1.0, -1.0], [-1.0, 0.0, 1.0], [1.0, -1.0, 0.0]])

# Paper, Example 2 (p.7).
CYCLE = np.array([[0.0, 1.0, -1.0], [-1.0, 0.0, 1.0], [1.0, -1.0, 0.0]])
TRANSITIVE = np.array([[0.0, 1.0, 2.0], [-1.0, 0.0, 1.0], [-2.0, -1.0, 0.0]])


def duplicate_last(matrix: np.ndarray) -> np.ndarray:
    """Paper, Definition 3 (p.14): append a redundant copy of the last agent.

        A' = [[A,       a_n],
              [-a_n^T,  0  ]]
    """
    column = matrix[:, -1]
    n = matrix.shape[0]
    grown = np.zeros((n + 1, n + 1))
    grown[:n, :n] = matrix
    grown[:n, n] = column
    grown[n, :n] = -column
    return grown


# --------------------------------------------------------------------------------------------
# Hodge decomposition
# --------------------------------------------------------------------------------------------


def test_rps_is_purely_cyclic():
    """div(A) = 0 for rock-paper-scissors: no agent is better than any other (Theorem 1, P3i)."""
    assert np.allclose(div(RPS), 0.0)
    assert np.allclose(rot(RPS), RPS)


def test_transitive_field_has_no_cyclic_part():
    """A = grad(r) must decompose back to exactly r, with zero residual (Theorem, part i/iii)."""
    rating = np.array([1.5, 0.25, -0.75, -1.0])
    rating -= rating.mean()
    matrix = grad(rating)
    assert np.allclose(div(matrix), rating)
    assert np.allclose(rot(matrix), 0.0, atol=1e-12)


def test_decomposition_is_orthogonal():
    """grad(div(A)) and rot(A) are orthogonal under <A,B> = sum_ij A_ij B_ij (Theorem, part iv)."""
    rng = np.random.default_rng(0)
    raw = rng.normal(size=(6, 6))
    matrix = raw - raw.T
    assert np.isclose(np.sum(grad(div(matrix)) * rot(matrix)), 0.0, atol=1e-10)


# --------------------------------------------------------------------------------------------
# Nash averaging: the paper's worked examples
# --------------------------------------------------------------------------------------------


def test_rps_nash_is_uniform():
    """Paper, Example 1: p* = (1/3, 1/3, 1/3) and n_A = 0."""
    equilibrium = maxent_nash(RPS)
    assert np.allclose(equilibrium, 1 / 3, atol=1e-6)
    assert np.allclose(nash_average(RPS, equilibrium), 0.0, atol=1e-6)


def test_nash_is_invariant_to_a_duplicate_agent():
    """Paper, Example 1: duplicating C gives p* = (1/3, 1/3, 1/6, 1/6) and n = 0.

    This is property P1, and the whole reason the project uses Nash averaging: the roster is full
    of near-duplicate ancestors.
    """
    grown = duplicate_last(RPS)
    equilibrium = maxent_nash(grown)
    assert np.allclose(equilibrium, [1 / 3, 1 / 3, 1 / 6, 1 / 6], atol=1e-5)
    assert np.allclose(nash_average(grown, equilibrium), 0.0, atol=1e-5)


def test_uniform_average_is_not_invariant_to_a_duplicate_agent():
    """The counterpart: div(A') = (-1.15, 1.15, 0, 0), "falsely suggesting agent B is superior".

    So the transitive mElo component -- our primary ranking key -- is knowingly vulnerable here.
    That is precisely what report.py's rank_delta column surfaces.
    """
    grown = duplicate_last(RPS)
    assert np.allclose(div(RPS), 0.0)
    assert np.allclose(div(grown), [-1.15, 1.15, 0.0, 0.0], atol=1e-6)


@pytest.mark.parametrize("epsilon", [0.0, 0.1, 0.3, 0.5])
def test_example_2_below_the_discontinuity(epsilon):
    """Paper, Example 2: for 0 <= eps <= 1/2, p* = ((1+e)/3, (1-2e)/3, (1+e)/3) and n = 0."""
    matrix = CYCLE + epsilon * TRANSITIVE
    equilibrium = maxent_nash(matrix)
    expected = np.array([(1 + epsilon) / 3, (1 - 2 * epsilon) / 3, (1 + epsilon) / 3])
    assert np.allclose(equilibrium, expected, atol=1e-5)
    assert np.allclose(nash_average(matrix, equilibrium), 0.0, atol=1e-5)


@pytest.mark.parametrize("epsilon", [0.6, 0.8, 1.0])
def test_example_2_above_the_discontinuity(epsilon):
    """Paper, Example 2: for eps > 1/2, Nash jumps to p* = (1,0,0) and n = (0, -1-e, 1-2e)."""
    matrix = CYCLE + epsilon * TRANSITIVE
    equilibrium = maxent_nash(matrix)
    assert np.allclose(equilibrium, [1.0, 0.0, 0.0], atol=1e-5)
    expected = np.array([0.0, -1.0 - epsilon, 1.0 - 2 * epsilon])
    assert np.allclose(nash_average(matrix, equilibrium), expected, atol=1e-5)


def test_transitive_field_puts_all_nash_mass_on_the_best():
    """Theorem 1, P3ii: if A = grad(r), maxent Nash is uniform on the highest-rated player(s)."""
    rating = np.array([2.0, 0.5, -0.5, -2.0])
    equilibrium = maxent_nash(grad(rating))
    assert np.allclose(equilibrium, [1.0, 0.0, 0.0, 0.0], atol=1e-5)


def test_nash_support_members_tie_at_zero():
    """Indifference principle: strategies in the support have equal payoff, which here is 0."""
    matrix = CYCLE + 0.3 * TRANSITIVE
    equilibrium = maxent_nash(matrix)
    averages = nash_average(matrix, equilibrium)
    assert np.allclose(averages[equilibrium > 0], 0.0, atol=1e-5)
    assert np.all(averages <= 1e-6)


def test_nash_is_a_probability_distribution():
    rng = np.random.default_rng(7)
    raw = rng.normal(size=(9, 9))
    equilibrium = maxent_nash(raw - raw.T)
    assert np.isclose(equilibrium.sum(), 1.0)
    assert np.all(equilibrium >= 0.0)


def test_rectangular_nash_rates_agents_against_tasks():
    score = np.array([[1.0, 2.0], [-1.0, 0.0]])
    agents, tasks, value = maxent_rectangular_nash(score)
    assert np.allclose(agents, [1.0, 0.0], atol=1e-5)
    assert np.allclose(tasks, [1.0, 0.0], atol=1e-5)
    assert np.isclose(value, 1.0, atol=1e-6)


def test_map_tasks_balance_the_two_player_orders():
    rows = [
        {"status": "ok", "winner": "a", "bot_a": "a", "bot_b": "b", "map": "duel", "score_a": 1},
        {"status": "ok", "winner": "a", "bot_a": "b", "bot_b": "a", "map": "duel", "score_a": 1},
    ]
    bots, tasks, games, wins = tally_map_tasks(rows)
    assert tasks == [("a", "duel"), ("b", "duel")]
    a = bots.index("a")
    against_b = tasks.index(("b", "duel"))
    assert games[a, against_b] == 2
    assert wins[a, against_b] == 1


# --------------------------------------------------------------------------------------------
# mElo
# --------------------------------------------------------------------------------------------


def test_omega_is_antisymmetric_with_the_right_blocks():
    """Paper, section 3.1: Omega = sum_i (e_{2i-1}e_{2i}^T - e_{2i}e_{2i-1}^T)."""
    matrix = omega(2)
    assert np.allclose(matrix, -matrix.T)
    assert np.allclose(matrix[:2, :2], [[0, 1], [-1, 0]])
    assert np.allclose(matrix[2:, 2:], [[0, 1], [-1, 0]])
    assert np.allclose(matrix[:2, 2:], 0.0)


def test_melo_predictions_always_sum_to_one():
    """Because Omega is antisymmetric, p_ij + p_ji = 1 holds for any r and C."""
    rng = np.random.default_rng(3)
    rating = rng.normal(size=5)
    cyclic = rng.normal(size=(5, 2))
    predicted = predict(rating, cyclic, 1)
    assert np.allclose(predicted + predicted.T, 1.0)


def test_melo_recovers_a_transitive_field():
    """On a pure Elo field, r must be recovered exactly and C must be empty of signal."""
    truth = np.array([1.0, 0.35, -0.35, -1.0])
    truth -= truth.mean()
    rating, cyclic = fit_melo(grad(truth), k=1)
    assert np.allclose(rating, truth)
    assert np.allclose(cyclic, 0.0, atol=1e-9)


def test_melo_reconstructs_rock_paper_scissors_exactly():
    """A 3-agent cycle is rank 2, so mElo_2 must reproduce it with zero error.

    Elo cannot: div(RPS) = 0 forces every rating to 0 and every prediction to 0.5.
    """
    rating, cyclic = fit_melo(RPS, k=1)
    assert np.allclose(rating, 0.0, atol=1e-9)
    assert np.allclose(cyclic @ omega(1) @ cyclic.T, RPS, atol=1e-8)

    probability = 1.0 / (1.0 + np.exp(-RPS))
    assert np.allclose(predict(rating, cyclic, 1), probability, atol=1e-8)
    assert np.allclose(predict(*fit_melo(RPS, k=0), 0), 0.5)  # Elo is helpless here


def test_melo_beats_elo_on_a_mixed_field():
    """The paper's central claim, on a field with both a pecking order and a cycle."""
    matrix = grad(np.array([0.9, 0.0, -0.9])) + RPS
    probability = 1.0 / (1.0 + np.exp(-matrix))
    games = np.full((3, 3), 100.0)
    np.fill_diagonal(games, 0.0)

    melo_error = np.linalg.norm(probability - predict(*fit_melo(matrix, k=1), 1))
    elo_error = np.linalg.norm(probability - predict(*fit_melo(matrix, k=0), 0))
    assert melo_error < elo_error
    assert melo_error < 1e-8  # a 3-agent field is fully captured at 2k = 2


def test_melo_truncation_keeps_the_largest_cyclic_component():
    """With more cycles than 2k can hold, the retained block must be the dominant one."""
    rng = np.random.default_rng(5)
    raw = rng.normal(size=(8, 8))
    matrix = raw - raw.T
    residual = rot(matrix)

    _, cyclic = fit_melo(matrix, k=1)
    approximation = cyclic @ omega(1) @ cyclic.T
    # The rank-2 truncation must beat any lower-rank option, i.e. capture real energy...
    assert np.linalg.norm(residual - approximation) < np.linalg.norm(residual)
    # ...and match the two largest singular values of the residual (Eckart-Young for the
    # antisymmetric case: singular values come in equal pairs).
    singular = np.linalg.svd(residual, compute_uv=False)
    captured = np.linalg.norm(residual) ** 2 - np.linalg.norm(residual - approximation) ** 2
    assert captured == pytest.approx(singular[0] ** 2 + singular[1] ** 2, rel=1e-6)


def test_melo_cyclic_vectors_are_orthogonal_to_ones_and_each_other():
    """C's columns come from an orthogonal Schur basis and lie in the null space of 1."""
    rng = np.random.default_rng(11)
    raw = rng.normal(size=(7, 7))
    matrix = raw - raw.T
    _, cyclic = fit_melo(matrix, k=1)
    assert np.allclose(np.ones(7) @ cyclic, 0.0, atol=1e-8)
    assert np.isclose(cyclic[:, 0] @ cyclic[:, 1], 0.0, atol=1e-8)


def test_melo_cyclic_term_carries_no_transitive_content():
    """The substantive requirement: the 2k term must not smuggle in a pecking order.

    The paper words its constraint as "rows of C orthogonal ... to r", which is a sufficient
    condition for this. What actually matters -- and what the Schur construction guarantees
    exactly -- is that C^T Omega C has zero divergence, so it lives in im(rot) and is orthogonal
    to every grad(s) under <A,B> = sum_ij A_ij B_ij. See the note in fit_melo.
    """
    rng = np.random.default_rng(13)
    raw = rng.normal(size=(9, 9))
    matrix = raw - raw.T
    _, cyclic = fit_melo(matrix, k=2)
    interaction = cyclic @ omega(2) @ cyclic.T

    assert np.allclose(div(interaction), 0.0, atol=1e-9)
    for _ in range(5):
        arbitrary = rng.normal(size=9)
        assert np.isclose(np.sum(interaction * grad(arbitrary)), 0.0, atol=1e-8)


def test_melo_rating_is_unchanged_by_k():
    """r = div(A) is computed before any truncation, so the ranking key cannot depend on 2k."""
    rng = np.random.default_rng(17)
    raw = rng.normal(size=(6, 6))
    matrix = raw - raw.T
    ratings = [fit_melo(matrix, k=k)[0] for k in (0, 1, 2)]
    assert np.allclose(ratings[0], ratings[1])
    assert np.allclose(ratings[0], ratings[2])
    assert np.allclose(ratings[0], div(matrix))


def test_melo_online_update_matches_the_papers_listing():
    """Appendix E, transcribed literally, must agree with our vectorised form."""
    rating = np.array([0.3, -0.2])
    cyclic = np.array([[0.5, 0.1], [-0.4, 0.7]])
    observed, eta_r, eta_c = 1.0, 0.5, 0.25

    expected_r = rating.copy()
    expected_c = cyclic.copy()
    p_hat = 1 / (
        1
        + np.exp(-(rating[0] - rating[1] + cyclic[0, 0] * cyclic[1, 1] - cyclic[1, 0] * cyclic[0, 1]))
    )
    delta = observed - p_hat
    expected_r[0] += eta_r * delta
    expected_r[1] -= eta_r * delta
    expected_c[0, 0] += eta_c * delta * cyclic[1, 1]
    expected_c[1, 0] += eta_c * -delta * cyclic[0, 1]
    expected_c[0, 1] += eta_c * -delta * cyclic[1, 0]
    expected_c[1, 1] += eta_c * delta * cyclic[0, 0]

    melo_online_update(0, 1, observed, rating, cyclic, eta_r=eta_r, eta_c=eta_c)
    assert np.allclose(rating, expected_r)
    assert np.allclose(cyclic, expected_c)


# --------------------------------------------------------------------------------------------
# Building A from match rows
# --------------------------------------------------------------------------------------------


def _row(a, b, score, status="ok"):
    winner = {1.0: "a", 0.0: "b", 0.5: "draw"}[score]
    return {"bot_a": a, "bot_b": b, "score_a": score, "status": status, "winner": winner}


def test_tally_counts_both_orders_and_draws():
    rows = [
        _row("x@1", "y@2", 1.0),
        _row("y@2", "x@1", 1.0),  # y wins when playing first
        _row("x@1", "y@2", 0.5),  # a draw
    ]
    bots, games, wins = tally(rows)
    assert bots == ["x@1", "y@2"]
    i, j = 0, 1
    assert games[i, j] == 3 and games[j, i] == 3
    assert wins[i, j] == pytest.approx(1.5)  # one win + one draw
    assert wins[j, i] == pytest.approx(1.5)


def test_tally_treats_final_engine_coinflip_as_draw():
    row = _row("x@1", "y@2", 1.0)
    row["win_condition"] = "coinflip"
    _, games, wins = tally([row])
    assert games[0, 1] == 1
    assert wins[0, 1] == pytest.approx(0.5)
    assert wins[1, 0] == pytest.approx(0.5)


def test_evaluate_retains_even_numbers_of_draws_for_exact_reporting():
    result = evaluate(
        [
            {**_row("x@1", "y@2", 1.0), "win_condition": "coinflip"},
            {**_row("y@2", "x@1", 1.0), "win_condition": "coinflip"},
        ]
    )
    assert result.draws[0, 1] == 2
    assert result.draws[1, 0] == 2


def test_tally_excludes_errored_matches():
    rows = [_row("x@1", "y@2", 1.0), _row("x@1", "y@2", 1.0, status="error")]
    _, games, _ = tally(rows)
    assert games[0, 1] == 1


def test_logit_matrix_is_antisymmetric_even_after_a_clean_sweep():
    """A 42-0 sweep is routine here; raw relative frequency would give logit(1) = inf."""
    rows = [_row("x@1", "y@2", 1.0) for _ in range(42)]
    _, games, wins = tally(rows)
    matrix = logit_matrix(win_probability(games, wins))
    assert np.all(np.isfinite(matrix))
    assert np.allclose(matrix, -matrix.T)
    assert matrix[0, 1] > 0  # x is rated above y


def test_unplayed_pairs_are_neutral():
    """Never having met is not evidence, and must contribute 0 to the logit matrix."""
    rows = [_row("x@1", "y@2", 1.0)]
    bots, games, wins = tally(rows, bots=["x@1", "y@2", "z@3"])
    matrix = logit_matrix(win_probability(games, wins))
    assert games[0, 2] == 0
    assert matrix[0, 2] == pytest.approx(0.0)
