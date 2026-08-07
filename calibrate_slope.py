"""Measure whether our bots actually obey standard Elo, and set the policy's slope prior.

`policy.PRIOR_SLOPE_SD` decides how much the batch design spreads, and it is currently
a guess. This measures it from the farm's own match history, which lives in `data/` on
the machine that runs the farm and is never deployed -- so this has to be run there:

    python3 calibrate_slope.py

The model being fitted, per bot, over its own games:

    logit P(win vs team j)  =  a  +  b * (r_us - r_j) * ln(10)/400

`b = 1` is standard Elo. `b < 1` means the bot is FLAT -- it beats strong teams more
often and weak teams less often than its rating implies. `b > 1` means it is SWINGY.
The spread of fitted `b` ACROSS our bots is the number the policy needs: if every bot
comes out near 1, the slope carries no information, batch design has nothing to buy,
and greedy selection is provably optimal. If they scatter, the spread is the prior.

Prints the fitted values and the `PRIOR_SLOPE_SD` they imply. It does not edit
policy.py -- read the number, decide, and change the constant deliberately.
"""

from __future__ import annotations

import csv
import math
import pathlib
import statistics
import sys

HERE = pathlib.Path(__file__).resolve().parent
GAMES = HERE / "data" / "games.csv"
SERIES = HERE / "data" / "series.csv"
LN10_OVER_400 = math.log(10.0) / 400.0
MIN_GAMES = 30          # below this a two-parameter fit is not identified
MIN_SPREAD = 120.0      # Elo range of opponents needed before `b` means anything


def fit(rows: list[tuple[float, bool]], our_rating: float) -> tuple[float, float] | None:
    """Newton fit of (a, b). None when the design cannot identify a slope."""
    ratings = [r for r, _ in rows]
    if len(rows) < MIN_GAMES or (max(ratings) - min(ratings)) < MIN_SPREAD:
        return None
    a, b = 0.0, 1.0
    for _ in range(60):
        g = [0.0, 0.0]
        H = [[1e-6, 0.0], [0.0, 1e-6]]          # ridge, keeps it invertible
        for r, won in rows:
            x1 = (our_rating - r) * LN10_OVER_400
            z = a + b * x1
            p = 1.0 / (1.0 + math.exp(-z))
            resid = (1.0 if won else 0.0) - p
            w = p * (1.0 - p)
            g[0] += resid
            g[1] += resid * x1
            H[0][0] += w
            H[0][1] += w * x1
            H[1][0] += w * x1
            H[1][1] += w * x1 * x1
        det = H[0][0] * H[1][1] - H[0][1] * H[1][0]
        if abs(det) < 1e-12:
            return None
        da = (H[1][1] * g[0] - H[0][1] * g[1]) / det
        db = (H[0][0] * g[1] - H[1][0] * g[0]) / det
        a, b = a + da, b + db
        if abs(da) < 1e-9 and abs(db) < 1e-9:
            break
    return a, b


def main() -> int:
    if not GAMES.exists():
        print(f"no history at {GAMES} -- run this on the machine that hosts the farm")
        return 1
    our_rating = 1800.0
    if SERIES.exists():
        pass  # series.csv carries opponent ratings, not ours; the CLI ladder has ours

    by_bot: dict[str, list[tuple[float, bool]]] = {}
    for row in csv.DictReader(GAMES.open()):
        by_bot.setdefault(row["bot_id"], []).append(
            (float(row["opponent_rating"]), row["we_won"] == "True"))

    fits: list[tuple[str, float, float, int, float]] = []
    for bot, rows in sorted(by_bot.items()):
        res = fit(rows, our_rating)
        if res is None:
            continue
        a, b = res
        ratings = [r for r, _ in rows]
        fits.append((bot, a, b, len(rows), max(ratings) - min(ratings)))

    if not fits:
        print("no bot has enough games over a wide enough rating spread to identify b.")
        print(f"need >= {MIN_GAMES} games spanning >= {MIN_SPREAD:.0f} Elo.")
        print("keep PRIOR_SLOPE_SD tight until then -- greedy is the safe default.")
        return 0

    print(f"{'bot':<44}{'n':<7}{'spread':<9}{'a':<9}{'b'}")
    for bot, a, b, n, spread in fits:
        print(f"{bot[:42]:<44}{n:<7}{spread:<9.0f}{a:<9.2f}{b:.3f}")

    bs = [b for _, _, b, _, _ in fits]
    mean_b = statistics.fmean(bs)
    sd_b = statistics.pstdev(bs) if len(bs) > 1 else 0.0
    print(f"\nmean b = {mean_b:.3f}   sd across bots = {sd_b:.3f}   (standard Elo is b = 1)")
    print(f"\nimplied PRIOR_SLOPE_SD = {max(sd_b, 0.05):.2f}")
    if sd_b < 0.10:
        print("-> our bots do obey standard Elo. The slope carries no information, batch")
        print("   design buys nothing, and greedy selection is provably optimal. Leave the")
        print("   prior tight.")
    else:
        print("-> b genuinely varies between our bots, so the slope is worth estimating and")
        print("   the batch design earns its keep. Set PRIOR_SLOPE_SD to the value above.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
