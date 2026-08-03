"""mElo and Nash averaging, following Balduzzi et al., "Re-evaluating Evaluation" (NeurIPS 2018).

Paper: articles/1806.02643v2.pdf. Section references below are to that PDF.

Why not just count wins. Win rate and Elo are *not invariant to redundant agents* (paper, P1 and
Example 1): duplicating one agent in a rock-paper-scissors field moves Elo from (0,0,0) to
(-63, 63, 0, 0), "falsely suggesting agent B is superior". Our roster is full of near-duplicates --
seven vg_v* ancestors, eight v233_* probes -- so this is not a hypothetical. Nash averaging is
invariant to exactly that (Theorem 1); the transitive part of mElo is not, which is why this module
computes both and report.py shows where they disagree.

Pipeline (paper section 3.1 and section 4):

    match results -> P (win probabilities) -> A = logit(P), antisymmetric
                  -> r = div(A)          the transitive component, primary ranking key
                  -> rot(A) = A - grad(r)  the cyclic component
                  -> maxent Nash p* over {p in simplex : A p <= 0}, Nash average n = A p*

This module imports numpy/scipy and therefore must never be imported by anything that calls the
game engine. See the header of tournament/run_match.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import linprog, minimize
from scipy.special import logsumexp

from tournament.outcome import score_a as evaluation_score_a

# logit(p) = log(p/(1-p)) with p in Elo's base-10 convention is alpha-scaled; the paper sets
# alpha = 1 and works in natural log-odds ("The constant alpha is not important in what follows,
# so we pretend alpha = 1"). This converts a natural-log rating back to familiar Elo points.
ELO_PER_LOGIT = 400.0 / np.log(10.0)


@dataclass
class Ratings:
    bots: list[str]
    games: np.ndarray  # n x n, games played (symmetric)
    wins: np.ndarray  # n x n, wins of i over j (draws counted as 0.5 each side)
    draws: np.ndarray  # n x n, exact draw count (symmetric)
    win_prob: np.ndarray  # P, smoothed
    logit: np.ndarray  # A = logit(P), antisymmetric
    transitive: np.ndarray  # r = div(A), the mElo transitive component
    cyclic: np.ndarray  # rot(A) = A - grad(r)
    nash: np.ndarray  # p*, the maxent Nash equilibrium
    nash_average: np.ndarray  # n = A p*
    melo_r: np.ndarray  # r from the fitted mElo_2k model
    melo_c: np.ndarray  # n x 2k cyclic vectors from the fitted model
    fit: dict = field(default_factory=dict)

    @property
    def missing_pairs(self) -> list[tuple[str, str]]:
        """Pairs with no game between them, as (bot_i, bot_j).

        These are the entries where A_ij = 0 was imputed rather than measured. Callers must not
        have to infer this from a coverage percentage: a rating built on unmeasured pairs is a
        different object from one built on a complete matrix, and the difference has to be
        visible to anything that consumes Ratings, not just to whoever reads the printed table.
        """
        n = len(self.bots)
        return [
            (self.bots[i], self.bots[j])
            for i in range(n)
            for j in range(i + 1, n)
            if self.games[i, j] == 0
        ]

    @property
    def complete(self) -> bool:
        """True when every pair has played. Ratings are only comparable across complete fields."""
        return not self.missing_pairs

    @property
    def intransitivity(self) -> float:
        """||rot(A)||_F / ||A||_F -- how much of the field is rock-paper-scissors."""
        total = float(np.linalg.norm(self.logit))
        return float(np.linalg.norm(self.cyclic) / total) if total > 0 else 0.0


# --------------------------------------------------------------------------------------------
# Building the antisymmetric matrix
# --------------------------------------------------------------------------------------------


def tally(rows: list[dict], bots: list[str] | None = None) -> tuple[list[str], np.ndarray, np.ndarray]:
    """Aggregate match rows into (bots, games, wins) matrices.

    Only rows with status == "ok" count; a crashed bot produced no evidence about relative skill.
    Draws contribute 0.5 to each side, the standard treatment -- the paper itself only models
    binary outcomes and never mentions draws.
    """
    playable = [row for row in rows if row.get("status") == "ok" and row.get("winner")]
    if bots is None:
        bots = sorted({row[key] for row in playable for key in ("bot_a", "bot_b")})
    position = {bot: i for i, bot in enumerate(bots)}

    n = len(bots)
    games = np.zeros((n, n))
    wins = np.zeros((n, n))
    for row in playable:
        a, b = row["bot_a"], row["bot_b"]
        if a not in position or b not in position:
            continue
        i, j = position[a], position[b]
        score = evaluation_score_a(row)
        games[i, j] += 1
        games[j, i] += 1
        wins[i, j] += score
        wins[j, i] += 1.0 - score
    return bots, games, wins


def tally_draws(rows: list[dict], bots: list[str]) -> np.ndarray:
    """Count draws exactly; they cannot be reconstructed from aggregated half-points."""
    position = {bot: i for i, bot in enumerate(bots)}
    draws = np.zeros((len(bots), len(bots)))
    for row in rows:
        if row.get("status") != "ok" or not row.get("winner"):
            continue
        a, b = row["bot_a"], row["bot_b"]
        if a not in position or b not in position or evaluation_score_a(row) != 0.5:
            continue
        i, j = position[a], position[b]
        draws[i, j] += 1
        draws[j, i] += 1
    return draws


def win_probability(games: np.ndarray, wins: np.ndarray) -> np.ndarray:
    """P_ij = (wins_ij + 1/2) / (games_ij + 1), the add-half (Krichevsky-Trofimov) estimate.

    The paper uses raw relative frequencies, but logit(0) = -inf, and a 42-game sweep produces
    clean sweeps routinely. Add-half keeps every entry interior AND preserves antisymmetry
    exactly, since the numerators for (i,j) and (j,i) sum to games_ij + 1. Unplayed pairs land at
    P = 1/2, i.e. no evidence either way.
    """
    n = games.shape[0]
    probability = (wins + 0.5) / (games + 1.0)
    np.fill_diagonal(probability, 0.5)
    assert np.allclose(probability + probability.T, 1.0), "P must satisfy p_ij + p_ji = 1"
    return probability.reshape(n, n)


def logit_matrix(probability: np.ndarray) -> np.ndarray:
    """A = logit(P). Antisymmetric because p_ij + p_ji = 1 (paper, section 3.1)."""
    matrix = np.log(probability / (1.0 - probability))
    np.fill_diagonal(matrix, 0.0)
    if not np.allclose(matrix, -matrix.T, atol=1e-9):
        raise ValueError("logit matrix is not antisymmetric")
    return matrix


# --------------------------------------------------------------------------------------------
# Hodge decomposition: A = grad(r) + rot(A)   (paper, section 2.2)
# --------------------------------------------------------------------------------------------


def div(matrix: np.ndarray) -> np.ndarray:
    """div(A) = (1/n) A 1 -- the transitive component, and the mElo rating vector."""
    return matrix.mean(axis=1)


def grad(rating: np.ndarray) -> np.ndarray:
    """grad(r)_ij = r_i - r_j."""
    return rating[:, None] - rating[None, :]


def rot(matrix: np.ndarray) -> np.ndarray:
    """The cyclic residual, A - grad(div(A))."""
    return matrix - grad(div(matrix))


# --------------------------------------------------------------------------------------------
# mElo_2k   (paper, section 3.1 and appendix E)
# --------------------------------------------------------------------------------------------


def omega(k: int) -> np.ndarray:
    """Omega = sum_i (e_{2i-1} e_{2i}^T - e_{2i} e_{2i-1}^T): block-diagonal [[0,1],[-1,0]] blocks.

    Antisymmetric, so c_i^T Omega c_j = -c_j^T Omega c_i and the model always predicts
    p_ij + p_ji = 1 regardless of what C contains.
    """
    matrix = np.zeros((2 * k, 2 * k))
    for i in range(k):
        matrix[2 * i, 2 * i + 1] = 1.0
        matrix[2 * i + 1, 2 * i] = -1.0
    return matrix


def _sigmoid(x: np.ndarray | float) -> np.ndarray | float:
    return 1.0 / (1.0 + np.exp(-x))


def fit_melo(matrix: np.ndarray, k: int = 1) -> tuple[np.ndarray, np.ndarray]:
    """Fit mElo_2k in closed form: r = div(A), then a Schur decomposition of the residual.

    This is the paper's own recommendation (section F.3): "We recommend to first extract the
    transitive component and then perform the Schur decomposition on A~ = rot(A). Although this may
    not always be optimal with respect to the ||.||_2-norm, it has the important advantage that
    div(A) is readily understood by humans as a measure of average performance."

    A real antisymmetric matrix has a real Schur form that is block diagonal with 2x2 blocks
    lambda_j * [[0,1],[-1,0]] (its eigenvalues are the purely imaginary pairs +-i*lambda_j, which
    is also why antisymmetric matrices have even rank). Keeping the k largest blocks and folding
    sqrt(lambda_j) into the basis vectors gives C with

        c_i^T Omega c_j  ==  the rank-2k truncation of A~_ij

    exactly. Preferred over the appendix-E online updates (see melo_online_update) because it is
    deterministic and needs no learning-rate tuning -- with the paper's 16:1 rate ratio, SGD cannot
    grow C away from its initialisation fast enough to represent a strong cycle.

    One deviation worth stating. The paper asks for "the rows of C ... orthogonal to each other, to
    r, and to 1". Here the columns are mutually orthogonal and orthogonal to 1 (the Schur vectors
    of a zero-divergence matrix are), but *not* in general orthogonal to r -- forcing that would
    destroy the exact reconstruction above. What the constraint exists to guarantee does hold
    exactly: the Schur vectors for non-zero blocks are orthogonal to 1, so C^T Omega C has zero
    divergence, lies in im(rot), and is therefore orthogonal to every grad(s). The cyclic term
    cannot smuggle in transitive information, which is the property that matters.
    """
    from scipy.linalg import schur

    n = matrix.shape[0]
    rating = div(matrix)
    residual = matrix - grad(rating)
    if k == 0:
        return rating, np.zeros((n, 0))

    # For antisymmetric input the real Schur form is block diagonal; `blocks` is orthogonal.
    triangular, blocks = schur(residual, output="real")

    # Blocks occupy disjoint index pairs (0,1), (2,3), ...
    found: list[tuple[float, np.ndarray, np.ndarray]] = []
    for start in range(0, n - 1, 2):
        value = triangular[start, start + 1]
        if abs(value) > 1e-12:
            found.append((value, blocks[:, start], blocks[:, start + 1]))

    found.sort(key=lambda item: -abs(item[0]))
    cyclic = np.zeros((n, 2 * k))
    for slot, (value, first, second) in enumerate(found[:k]):
        scale = np.sqrt(abs(value))
        # A negative block value flips the block's orientation; swapping the pair restores it,
        # since Omega's convention fixes the sign of the cross term.
        if value >= 0:
            cyclic[:, 2 * slot] = scale * first
            cyclic[:, 2 * slot + 1] = scale * second
        else:
            cyclic[:, 2 * slot] = scale * second
            cyclic[:, 2 * slot + 1] = scale * first
    return rating, cyclic


def melo_online_update(
    i: int,
    j: int,
    observed: float,
    rating: np.ndarray,
    cyclic: np.ndarray,
    eta_r: float = 16.0 / ELO_PER_LOGIT,
    eta_c: float | None = None,
) -> None:
    """One online mElo_2 update, in place -- the paper's appendix E listing.

        p_hat_ij = sigmoid(r_i - r_j + c[i,0]*c[j,1] - c[j,0]*c[i,1])
        delta    = p_ij - p_hat_ij
        r_i += eta_r*delta ;  r_j -= eta_r*delta
        c_i += eta_c*delta*(Omega c_j) ;  c_j -= eta_c*delta*(Omega c_i)

    Kept because it is the only code the paper ships, and because it is what you would use to
    update ratings as new matches arrive without refitting. `fit_melo` is used for reporting.

    The paper's eta_r = 16 is Elo's K-factor in *Elo points*; ratings here are natural log-odds, so
    it is converted. The paper says only that "r has higher learning rate than c", and its listing
    applies an implicit coefficient of 1 to c against 16 for r, hence the default 16:1 ratio.
    """
    eta_c = eta_r / 16.0 if eta_c is None else eta_c
    k = cyclic.shape[1] // 2
    omega_matrix = omega(k)
    predicted = _sigmoid(rating[i] - rating[j] + cyclic[i] @ omega_matrix @ cyclic[j])
    delta = observed - predicted
    rating[i] += eta_r * delta
    rating[j] -= eta_r * delta
    grad_i = omega_matrix @ cyclic[j]
    grad_j = omega_matrix @ cyclic[i]
    cyclic[i] += eta_c * delta * grad_i
    cyclic[j] -= eta_c * delta * grad_j


def predict(rating: np.ndarray, cyclic: np.ndarray, k: int) -> np.ndarray:
    """The model's predicted win-probability matrix."""
    interaction = cyclic @ omega(k) @ cyclic.T
    return _sigmoid(grad(rating) + interaction)


def fit_quality(
    probability: np.ndarray, predicted: np.ndarray, games: np.ndarray
) -> dict[str, float]:
    """Frobenius error and mean log-loss over played pairs, as reported in the paper's Go table."""
    mask = games > 0
    if not mask.any():
        return {"frobenius": 0.0, "log_loss": 0.0}
    error = np.where(mask, probability - predicted, 0.0)
    clipped = np.clip(predicted[mask], 1e-12, 1 - 1e-12)
    observed = probability[mask]
    log_loss = -(observed * np.log(clipped) + (1 - observed) * np.log(1 - clipped))
    return {
        "frobenius": float(np.linalg.norm(error)),
        "log_loss": float(log_loss.mean()),
    }


# --------------------------------------------------------------------------------------------
# Nash averaging   (paper, section 4, Proposition 4, Definition 2)
# --------------------------------------------------------------------------------------------


def maxent_nash(matrix: np.ndarray, tolerance: float = 1e-9) -> np.ndarray:
    """The unique maximum-entropy Nash equilibrium of the meta-game with payoff A.

    For antisymmetric A the game is symmetric zero-sum and its value is 0, so the equilibrium set
    is the polytope {p in simplex : A p <= 0} (paper, proof of Lemma 1). Proposition 4: entropy is
    strictly concave on that compact convex set, hence a unique maximiser.

    Solved directly as a convex program rather than the paper's two-stage "LP-solver, then the
    algorithm in [71,72]" -- maximising a concave objective over linear constraints is one shot.
    """
    n = matrix.shape[0]
    uniform = np.full(n, 1.0 / n)
    if n == 1:
        return uniform

    # Confirm the polytope is non-empty (it always should be; this catches a malformed A).
    feasibility = linprog(
        c=np.zeros(n),
        A_ub=matrix,
        b_ub=np.zeros(n),
        A_eq=np.ones((1, n)),
        b_eq=[1.0],
        bounds=[(0.0, 1.0)] * n,
        method="highs",
    )
    if not feasibility.success:
        raise RuntimeError(f"no Nash equilibrium found: {feasibility.message}")

    def negative_entropy(p: np.ndarray) -> float:
        safe = np.clip(p, 1e-300, None)
        return float(np.sum(safe * np.log(safe)))

    def negative_entropy_gradient(p: np.ndarray) -> np.ndarray:
        safe = np.clip(p, 1e-300, None)
        return np.log(safe) + 1.0

    constraints = [
        {"type": "eq", "fun": lambda p: np.sum(p) - 1.0, "jac": lambda p: np.ones(n)},
        {"type": "ineq", "fun": lambda p: -matrix @ p, "jac": lambda p: -matrix},
    ]

    best: np.ndarray | None = None
    best_entropy = -np.inf
    # Seed from the uniform point and from the LP vertex: SLSQP is local, and the entropy surface
    # near a degenerate vertex can stall a single start.
    for start in (uniform, np.clip(feasibility.x, 1e-6, None) / np.sum(np.clip(feasibility.x, 1e-6, None))):
        solution = minimize(
            negative_entropy,
            start,
            jac=negative_entropy_gradient,
            method="SLSQP",
            bounds=[(0.0, 1.0)] * n,
            constraints=constraints,
            options={"maxiter": 500, "ftol": 1e-12},
        )
        candidate = np.clip(solution.x, 0.0, None)
        total = candidate.sum()
        if total <= 0:
            continue
        candidate = candidate / total
        if np.max(matrix @ candidate) > 1e-6:  # not actually an equilibrium
            continue
        entropy = -negative_entropy(candidate)
        if entropy > best_entropy:
            best, best_entropy = candidate, entropy

    if best is None:
        # Degenerate fields built from only two games per pair can make SLSQP stall against the
        # boundary of the equilibrium polytope. The entropy dual has one non-negative multiplier
        # per strategy and no explicit linear constraints:
        #   min_lambda logsumexp(A lambda), lambda >= 0;  p = softmax(A lambda).
        # Its gradient is -A p, so optimality is exactly the primal feasibility condition A p <= 0.
        def entropy_dual(multiplier: np.ndarray) -> tuple[float, np.ndarray, np.ndarray]:
            logits = matrix @ multiplier
            normalizer = logsumexp(logits)
            candidate = np.exp(logits - normalizer)
            return float(normalizer), -matrix @ candidate, candidate

        # Stop on the gradient, not on the objective. The dual's gradient is -Ap, so gtol *is* the
        # primal feasibility this solve is judged by, while ftol measures progress in logsumexp --
        # a quantity that flattens long before p is feasible. At ftol=1e-14 a 93-strategy field
        # quit after 34 iterations at max(Ap) = 1.03e-6, a hair past the 1e-6 acceptance bound
        # below, and the entire solve was then reported as failed; it needs 63 iterations to reach
        # 1e-13. ftol is set below machine precision so that gtol governs.
        dual = minimize(
            lambda multiplier: entropy_dual(multiplier)[0],
            np.zeros(n),
            jac=lambda multiplier: entropy_dual(multiplier)[1],
            method="L-BFGS-B",
            bounds=[(0.0, None)] * n,
            options={"maxiter": 5000, "maxfun": 20000, "ftol": 1e-18, "gtol": 1e-12},
        )
        candidate = entropy_dual(dual.x)[2]
        if np.max(matrix @ candidate) <= 1e-6:
            best = candidate
        else:
            raise RuntimeError("maxent Nash solve failed from every starting point and its dual")
    best[best < tolerance] = 0.0
    return best / best.sum()


def nash_average(matrix: np.ndarray, equilibrium: np.ndarray) -> np.ndarray:
    """n_A = A p* (paper, Definition 2), in log-odds. Support members tie at 0; others are < 0."""
    return matrix @ equilibrium


# --------------------------------------------------------------------------------------------
# Top level
# --------------------------------------------------------------------------------------------


def evaluate(rows: list[dict], k: int = 1) -> Ratings:
    """Full pipeline: match rows in, Ratings out."""
    bots, games, wins = tally(rows)
    if len(bots) < 2:
        raise ValueError("need results for at least two bots")

    probability = win_probability(games, wins)
    matrix = logit_matrix(probability)
    transitive = div(matrix)
    cyclic_part = rot(matrix)

    equilibrium = maxent_nash(matrix)
    averages = nash_average(matrix, equilibrium)

    melo_r, melo_c = fit_melo(matrix, k=k)
    # Vanilla Elo is literally mElo with 2k = 0 (paper, section 3.1): the same rating vector with
    # the cyclic term dropped. At k = 0, C has no columns and Omega is 0x0, so the interaction
    # contracts to exactly zero.
    elo_r, elo_c = fit_melo(matrix, k=0)

    fit = {
        "melo_2k": fit_quality(probability, predict(melo_r, melo_c, k), games),
        "elo": fit_quality(probability, predict(elo_r, elo_c, 0), games),
        "k": k,
    }

    return Ratings(
        bots=bots,
        games=games,
        wins=wins,
        draws=tally_draws(rows, bots),
        win_prob=probability,
        logit=matrix,
        transitive=transitive,
        cyclic=cyclic_part,
        nash=equilibrium,
        nash_average=averages,
        melo_r=melo_r,
        melo_c=melo_c,
        fit=fit,
    )
