"""The reference opponent set, and the promotion gate that uses it.

A single opponent is a trap: a bot can be tuned into beating one archetype while
collapsing against another. The zoo is the minimum set that makes "is this better"
answerable.

    idle           does literally nothing. Two jobs: it is the floor (anything
                   that cannot beat idle is broken), and because the tiebreak
                   metric `titanium_collected` is ABSOLUTE rather than relative,
                   the economy numbers from a game against idle are an
                   uncontested measurement of how much a bot can actually mine.

    starter_fixed  the shipped starter with its out-of-bounds crash repaired.
                   This is the field median: most teams will submit something
                   close to the starter, so beating it is the bar for being
                   mid-table, not for being good. The crash is repaired because
                   an opponent that deletes its own builders is not the starter,
                   it is a handicapped starter, and tuning against a handicapped
                   opponent teaches the wrong lesson.

Promotion aggregates the candidate's S against every zoo member as::

    0.7 * mean(S) + 0.3 * min(S)

The min term is the point. A candidate that averages +0.4 by crushing idle while
losing -0.5 to starter_fixed has a hole in it, and the ladder will find the hole.
Weighting the worst case at 30% makes one catastrophic matchup block promotion.
"""

from __future__ import annotations

import os
import shutil
import statistics
import sys
from pathlib import Path
from typing import Sequence

from arena import ALL_15, BOTS_DIR, ZOO_DIR, bot_dir, bot_name, resolve_bot

__all__ = [
    "ZOO_NAMES",
    "ensure_zoo",
    "zoo_paths",
    "clean_pycache",
    "promotion_score",
    "promotion_gate",
    "format_promotion",
]

ZOO_NAMES = ("idle", "starter_fixed")

STARTER_SRC = BOTS_DIR / "starter" / "main.py"

IDLE_SRC = '''"""idle -- the zoo floor. Does nothing at all, ever.

Two jobs:

1. The absolute floor. A bot that cannot beat `idle` is broken, not weak.
2. The economy yardstick. `titanium_collected` is an ABSOLUTE tiebreak metric
   (G01/G03): it counts only stacks that land on a Core footprint tile, and it
   is not scaled by what the opponent did. Against an opponent that never
   contests anything, a bot's collected total is a clean read on how much
   economy its build order actually produces.

Deliberately imports nothing. Pure stdlib, no fcode import, no state.
"""


class Player:
    def run(self, ct) -> None:
        return
'''

# --- starter_fixed patches ---------------------------------------------------
# Applied as exact-string substitutions against bots/starter/main.py so that this
# stays a *copy with one fix*, and so that any future edit to the starter that
# moves this code makes ensure_zoo() fail loudly instead of drifting silently.

_OOB_CALL_OLD = "        if ct.is_tile_empty(next_pos) and self.core_pos is not None:\n"
_OOB_CALL_NEW = (
    "        # ARENA FIX (was the crash at starter main.py:369): is_tile_empty()\n"
    "        # raises GameError for an out-of-bounds tile, and an uncaught GameError\n"
    "        # permanently deletes the unit (G23). pos.add(d) walks off the map edge\n"
    "        # constantly, so this call needs a bounds guard in front of it.\n"
    "        if (\n"
    "            self._in_bounds(ct, next_pos)\n"
    "            and ct.is_tile_empty(next_pos)\n"
    "            and self.core_pos is not None\n"
    "        ):\n"
)

# The starter calls random.shuffle / random.choice / random.randrange and never
# seeds. Each unit runs in its own CPython sub-interpreter (G20), and a fresh
# interpreter seeds the Mersenne Twister from os.urandom -- which the sandbox does
# not stub. Unseeded, the starter is NOT reproducible: two identical 4-map sweeps
# disagreed on titanium on every map and flipped the winner on fjord. That makes it
# useless as a benchmark, because every measurement against it is noise. Seeding
# once per unit from ct.get_id() leaves the strategy exactly as written -- still a
# uniform shuffle, still a different stream per unit -- and makes it repeatable.
_SEED_INIT_OLD = "        # Core tracks how many builder bots it has spawned\n        self.num_spawned = 0\n"
_SEED_INIT_NEW = (
    "        # Core tracks how many builder bots it has spawned\n"
    "        self.num_spawned = 0\n"
    "\n"
    "        # ARENA FIX (reproducibility, not strategy): see arena/zoo.py.\n"
    "        self.seeded = False\n"
)

_SEED_RUN_OLD = "        etype = ct.get_entity_type()\n        if etype == EntityType.CORE:\n"
_SEED_RUN_NEW = (
    "        # ARENA FIX (reproducibility, not strategy): an unseeded `random` in a\n"
    "        # fresh sub-interpreter is seeded from os.urandom, which makes every\n"
    "        # match unrepeatable. ct.get_id() is stable within a match and distinct\n"
    "        # between units, so the strategy is unchanged and the result repeats.\n"
    "        if not self.seeded:\n"
    "            random.seed(ct.get_id())\n"
    "            self.seeded = True\n"
    "\n"
    "        etype = ct.get_entity_type()\n"
    "        if etype == EntityType.CORE:\n"
)

_HELPER_ANCHOR = "    def _try_move(self, ct: Controller, d: Direction) -> bool:\n"
_HELPER_NEW = (
    "    @staticmethod\n"
    "    def _in_bounds(ct: Controller, pos: Position) -> bool:\n"
    '        """ARENA FIX: True if pos is a real tile on this map."""\n'
    "        return 0 <= pos.x < ct.get_map_width() and 0 <= pos.y < ct.get_map_height()\n"
    "\n"
    "    def _try_move(self, ct: Controller, d: Direction) -> bool:\n"
)

_HEADER = '''"""starter_fixed -- bots/starter/main.py with its out-of-bounds crash repaired.

GENERATED by arena/zoo.py -- do not hand-edit; run `python -m arena.zoo --rebuild`.

Two changes from the shipped starter, neither of them a strategy change:

1. A bounds guard in front of `ct.is_tile_empty(next_pos)` in `_try_move`
   (starter main.py:369). Without it the builder walks a candidate step off the
   map edge, `is_tile_empty` raises GameError, and the uncaught exception
   permanently deletes the builder -- 520 times across 90 games in our
   measurements.

2. A per-unit `random.seed(ct.get_id())` on the unit's first turn. The starter
   uses `random` and never seeds it; a fresh sub-interpreter seeds from
   os.urandom, so the shipped starter is not reproducible and cannot serve as a
   benchmark. Same strategy, repeatable results.

It also passes the engine's AST validator audit: no `finally:` blocks, no bare
`except:`, no non-allowlisted exception names. (The starter has no try/except at
all, so the audit is a regression guard rather than a repair.)
"""

'''


def clean_pycache(path: str | os.PathLike[str]) -> int:
    """Delete every __pycache__ / .pyc under `path`. Returns how many were removed.

    A stray __pycache__ inside a bot directory makes the engine silently run the
    bot INERT (G30) -- it looks exactly like "my bot does nothing" with no error.
    """
    root = Path(path)
    removed = 0
    if not root.exists():
        return 0
    for p in sorted(root.rglob("*"), key=lambda q: len(q.parts), reverse=True):
        if p.name == "__pycache__" and p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
            removed += 1
        elif p.suffix == ".pyc" and p.is_file():
            p.unlink(missing_ok=True)
            removed += 1
    return removed


def _write(path: Path, text: str) -> bool:
    """Write UTF-8 with LF endings and no BOM. Returns True if the file changed."""
    data = text.encode("utf-8")
    if path.is_file() and path.read_bytes() == data:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return True


def _build_starter_fixed() -> str:
    if not STARTER_SRC.is_file():
        raise FileNotFoundError(f"cannot build starter_fixed: {STARTER_SRC} is missing")
    src = STARTER_SRC.read_text(encoding="utf-8")
    if src.startswith("﻿"):
        src = src.lstrip("﻿")
    src = src.replace("\r\n", "\n")

    for old, new, label in (
        (_OOB_CALL_OLD, _OOB_CALL_NEW, "out-of-bounds guard call site"),
        (_HELPER_ANCHOR, _HELPER_NEW, "_in_bounds helper"),
        (_SEED_INIT_OLD, _SEED_INIT_NEW, "per-unit RNG seed flag"),
        (_SEED_RUN_OLD, _SEED_RUN_NEW, "per-unit RNG seed call"),
    ):
        if src.count(old) != 1:
            raise RuntimeError(
                f"starter_fixed patch '{label}' did not apply: expected exactly one match "
                f"for {old!r}, found {src.count(old)}. bots/starter/main.py has changed; "
                "update arena/zoo.py."
            )
        src = src.replace(old, new, 1)

    # Keep the starter's own module docstring, prefixed with provenance.
    out = _HEADER + src

    from arena.strict import check_source

    violations = check_source(out, "<bot>/main.py")
    if violations:
        raise RuntimeError("starter_fixed fails the AST validator audit: " + "; ".join(violations))
    return out


def ensure_zoo(rebuild: bool = False) -> dict[str, Path]:
    """Materialise bots/zoo/* on disk and return {name: path to main.py}.

    Idempotent: rewrites only what changed, and always sweeps __pycache__.
    """
    ZOO_DIR.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}

    idle = ZOO_DIR / "idle" / "main.py"
    if rebuild or not idle.is_file():
        _write(idle, IDLE_SRC)
    else:
        _write(idle, IDLE_SRC)
    paths["idle"] = idle

    fixed = ZOO_DIR / "starter_fixed" / "main.py"
    _write(fixed, _build_starter_fixed())
    paths["starter_fixed"] = fixed

    clean_pycache(ZOO_DIR)
    return paths


def zoo_paths() -> dict[str, Path]:
    """The zoo without rebuilding it (raises if it has not been built)."""
    out = {}
    for name in ZOO_NAMES:
        p = ZOO_DIR / name / "main.py"
        if not p.is_file():
            return ensure_zoo()
        out[name] = p
    return out


# ---------------------------------------------------------------------------
# promotion
# ---------------------------------------------------------------------------

MEAN_WEIGHT = 0.7
MIN_WEIGHT = 0.3


def promotion_score(
    candidate: str | os.PathLike[str],
    opponents: Sequence[str] | None = None,
    maps: Sequence[str] = ALL_15,
    seed: int = 1,
    workers: int | None = None,
    cache: str | os.PathLike[str] | None = None,
) -> dict:
    """Score a candidate against the whole zoo: 0.7 * mean(S) + 0.3 * min(S)."""
    from arena.score import compare

    cand = resolve_bot(candidate)
    zoo = ensure_zoo()
    names = list(opponents) if opponents else list(zoo.keys())

    per_opponent = []
    scores: list[float] = []
    for name in names:
        opp = zoo.get(name)
        opp_path = opp if opp is not None else resolve_bot(name)
        rep = compare(cand, opp_path, maps=maps, seed=seed, workers=workers, cache=cache)
        scores.append(rep["S"])
        per_opponent.append(
            {
                "opponent": rep["y"],
                "S": rep["S"],
                "wins": rep["wins"],
                "win_conditions": rep["win_conditions"],
                "our_exceptions": rep["exceptions"]["x"],
                "crashed": rep["crashed"],
                "our_collected_mean": rep["economy"]["x"]["titanium_collected_mean"],
                "their_collected_mean": rep["economy"]["y"]["titanium_collected_mean"],
                "matches_per_sec": rep["throughput"]["matches_per_sec"],
            }
        )

    mean_s = statistics.fmean(scores) if scores else 0.0
    min_s = min(scores) if scores else 0.0
    aggregate = MEAN_WEIGHT * mean_s + MIN_WEIGHT * min_s

    idle_row = next((r for r in per_opponent if r["opponent"] == "idle"), None)
    return {
        "candidate": bot_name(cand),
        "candidate_path": str(cand),
        "per_opponent": per_opponent,
        "mean_S": mean_s,
        "min_S": min_s,
        "worst_opponent": per_opponent[scores.index(min_s)]["opponent"] if scores else None,
        "aggregate": aggregate,
        "absolute_economy_vs_idle": idle_row["our_collected_mean"] if idle_row else None,
        "our_exceptions": sum(r["our_exceptions"] for r in per_opponent),
        "crashed": sum(r["crashed"] for r in per_opponent),
    }


def promotion_gate(
    candidate: str | os.PathLike[str],
    incumbent: str | os.PathLike[str] | None = None,
    threshold: float = 0.0,
    **kwargs,
) -> dict:
    """Decide whether `candidate` may be promoted.

    Three conditions, all required:
      * aggregate zoo score strictly greater than `threshold`
      * no unit-deleting exceptions anywhere in the sweep
      * if an `incumbent` is given, S(candidate, incumbent) > 0
    """
    from arena.score import compare

    res = promotion_score(candidate, **kwargs)
    reasons: list[str] = []
    if res["aggregate"] <= threshold:
        reasons.append(
            f"zoo aggregate {res['aggregate']:+.4f} <= threshold {threshold:+.4f} "
            f"(mean {res['mean_S']:+.4f}, worst {res['min_S']:+.4f} vs {res['worst_opponent']})"
        )
    if res["our_exceptions"]:
        reasons.append(f"{res['our_exceptions']} of our units were deleted by exceptions")
    if res["crashed"]:
        reasons.append(f"{res['crashed']} games crashed in the harness")

    head_to_head = None
    if incumbent is not None:
        rep = compare(
            resolve_bot(candidate),
            resolve_bot(incumbent),
            maps=kwargs.get("maps", ALL_15),
            seed=kwargs.get("seed", 1),
            workers=kwargs.get("workers"),
            cache=kwargs.get("cache"),
        )
        head_to_head = {"incumbent": rep["y"], "S": rep["S"], "wins": rep["wins"]}
        if rep["S"] <= 0:
            reasons.append(f"S vs incumbent {rep['y']} is {rep['S']:+.4f}, not an improvement")

    res["head_to_head"] = head_to_head
    res["threshold"] = threshold
    res["promoted"] = not reasons
    res["reasons"] = reasons
    return res


def format_promotion(res: dict) -> str:
    lines = [f"PROMOTION -- {res['candidate']}", "=" * 60]
    lines.append(f"{'opponent':<18} {'S':>8}  {'W-L-D':>10}  our_exc  collected(us/them)")
    for r in res["per_opponent"]:
        w = r["wins"]
        lines.append(
            f"{r['opponent']:<18} {r['S']:>+8.4f}  "
            f"{w['x']:>3}-{w['y']:<3}-{w['draws']:<2}  {r['our_exceptions']:>7}  "
            f"{r['our_collected_mean']:.0f}/{r['their_collected_mean']:.0f}"
        )
    lines.append("-" * 60)
    lines.append(
        f"mean S = {res['mean_S']:+.4f}   min S = {res['min_S']:+.4f} (vs {res['worst_opponent']})"
    )
    lines.append(
        f"aggregate = {MEAN_WEIGHT}*mean + {MIN_WEIGHT}*min = {res['aggregate']:+.4f}"
        f"   (threshold {res.get('threshold', 0.0):+.4f})"
    )
    if res.get("absolute_economy_vs_idle") is not None:
        lines.append(
            f"absolute economy vs idle: {res['absolute_economy_vs_idle']:.0f} titanium_collected/game"
        )
    if res.get("head_to_head"):
        h = res["head_to_head"]
        lines.append(f"head-to-head vs incumbent {h['incumbent']}: S = {h['S']:+.4f}")
    lines.append("")
    if res.get("promoted"):
        lines.append("VERDICT: PROMOTE")
    else:
        lines.append("VERDICT: BLOCKED")
        for r in res.get("reasons", []):
            lines.append(f"  - {r}")
    return "\n".join(lines)


def _cli(argv: list[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Build the zoo / run the promotion gate.")
    ap.add_argument("candidate", nargs="?", default=None)
    ap.add_argument("--rebuild", action="store_true", help="rebuild zoo bots and exit")
    ap.add_argument("--incumbent", default=None)
    ap.add_argument("--threshold", type=float, default=0.0)
    ap.add_argument("--maps", nargs="*", default=list(ALL_15))
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--cache", default=None)
    args = ap.parse_args(argv)

    paths = ensure_zoo(rebuild=True)
    if args.rebuild or not args.candidate:
        for name, p in paths.items():
            print(f"{name:<16} {p}")
        return 0

    res = promotion_gate(
        args.candidate,
        incumbent=args.incumbent,
        threshold=args.threshold,
        maps=args.maps,
        seed=args.seed,
        workers=args.workers,
        cache=args.cache,
    )
    print(format_promotion(res))
    return 0 if res["promoted"] else 1


if __name__ == "__main__":
    raise SystemExit(_cli(sys.argv[1:]))
