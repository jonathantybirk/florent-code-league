"""Antisymmetric mirrored scoring -- the team's arbiter.

Why mirrored
------------
Team A's Core acts first, and that is worth ~58-60% in an identical-bot mirror
(ground truth G27). Any unpaired estimate is measuring seat, not skill; on this
repo an unpaired sweep once reported +1024 Ti for a change whose true paired
effect was -106. So every comparison plays each map twice, once per side, and
takes the difference::

    S(X, Y) = 0.5 * [ s(X as A, Y as B) - s(Y as A, X as B) ]

with s = +1 win / 0 draw / -1 loss for the bot named first in each term. The
first-mover bonus enters both terms with the same sign and cancels exactly, and
S(X, X) == 0 structurally, not just on average.

Why no replication and no seed sweeping
---------------------------------------
The engine is deterministic (G26): the same bots on the same map with the same
sides produce bit-identical results, and `--seed` only moves the coinflip
tiebreak. Replaying a completed (bots, map, side) triple returns the answer you
already have, and varying the seed manufactures the appearance of a sample while
adding zero information. 100% of outcome variance is between-map. The only
honest way to buy precision is more maps -- and there are exactly 15, so the
30-game sweep is not a sample, it is the census.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable, Sequence

from arena import ALL_15, ALL_MAPS, bot_name, resolve_bot, resolve_map
from arena.runner import run_matches

__all__ = ["compare", "score_for_a", "format_report", "determinism_probe", "ALL_15"]

#: Result fields that must repeat exactly if a matchup is reproducible.
DETERMINISM_KEYS = (
    "winner",
    "turns",
    "win_condition",
    "a_titanium",
    "a_titanium_collected",
    "a_units",
    "a_buildings",
    "b_titanium",
    "b_titanium_collected",
    "b_units",
    "b_buildings",
)

WIN = 1.0
DRAW = 0.0
LOSS = -1.0


def score_for_a(result: dict) -> float:
    """Score of the *Team A* bot in one game: +1 win, 0 draw, -1 loss.

    A crashed match scores a loss for Team A. A crash is a real failure of the
    thing under test, and the one behaviour we must never have is a crash that
    silently disappears from the denominator.
    """
    if result.get("crashed") or not result.get("ok"):
        return LOSS
    w = result.get("winner")
    if w == "A":
        return WIN
    if w == "B":
        return LOSS
    return DRAW


# ---------------------------------------------------------------------------
# determinism
# ---------------------------------------------------------------------------


def determinism_probe(
    bot_a: str | os.PathLike[str],
    bot_b: str | os.PathLike[str],
    maps: Sequence[str] = ("atoll", "duel", "fjord", "hive"),
    repeats: int = 2,
    seed: int = 1,
    workers: int | None = None,
) -> dict:
    """Play the same (bots, map, side) triples `repeats` times and diff the results.

    The ENGINE is deterministic (G26), but a BOT is not automatically so. Each unit
    runs in its own CPython sub-interpreter (G20), and a fresh interpreter seeds
    `random` from `os.urandom` -- which the sandbox does not stub. A bot that calls
    `random` without seeding therefore produces a different match every time, and
    every number the arena reports about it is noise. The shipped starter does
    exactly this: two identical 4-map sweeps disagreed on titanium on all four maps
    and flipped the winner on one.

    If this probe reports `deterministic: False`, seed your RNG per unit from
    `ct.get_id()` on the unit's first turn. Until then, do not trust a single
    30-game sweep to resolve a difference smaller than the run-to-run spread.
    """
    a = str(resolve_bot(bot_a))
    b = str(resolve_bot(bot_b))
    map_names = [Path(m).stem for m in maps]
    runs: list[list[dict]] = []
    for _ in range(max(2, repeats)):
        plan = [
            {"a": a, "b": b, "map": str(resolve_map(m)), "seed": seed, "capture": False}
            for m in map_names
        ]
        res, _stats = run_matches(plan, workers=workers)
        runs.append([{k: r.get(k) for k in DETERMINISM_KEYS} for r in res])

    diffs = []
    for i, m in enumerate(map_names):
        variants = [r[i] for r in runs]
        if any(v != variants[0] for v in variants):
            changed = sorted(
                {k for v in variants for k in DETERMINISM_KEYS if v[k] != variants[0][k]}
            )
            diffs.append({"map": m, "fields": changed, "variants": variants})
    return {
        "a": bot_name(a),
        "b": bot_name(b),
        "maps": map_names,
        "repeats": len(runs),
        "deterministic": not diffs,
        "diverging_maps": [d["map"] for d in diffs],
        "diffs": diffs,
    }


# ---------------------------------------------------------------------------
# optional content-addressed result cache (off by default)
# ---------------------------------------------------------------------------


def bot_fingerprint(main_py: str | os.PathLike[str]) -> str:
    """SHA-256 over every .py in the bot directory, path-sorted.

    Content-addressed, so a cache entry can never go stale behind an edit.
    """
    d = Path(main_py).resolve().parent
    h = hashlib.sha256()
    for p in sorted(d.rglob("*.py"), key=lambda q: str(q).lower()):
        if "__pycache__" in p.parts:
            continue
        h.update(str(p.relative_to(d)).replace("\\", "/").encode())
        h.update(b"\0")
        h.update(p.read_bytes())
        h.update(b"\0")
    return h.hexdigest()[:16]


def _cache_key(fa: str, fb: str, map_name: str, seed: int, tle: int) -> str:
    return f"{fa}|{fb}|{map_name}|{seed}|{tle}"


def _load_cache(path: str | os.PathLike[str] | None) -> dict[str, dict]:
    if not path or not Path(path).is_file():
        return {}
    out: dict[str, dict] = {}
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            out[rec["key"]] = rec["result"]
    return out


def _append_cache(path: str | os.PathLike[str], entries: list[tuple[str, dict]]) -> None:
    if not entries:
        return
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        for key, result in entries:
            slim = {k: v for k, v in result.items() if k != "traceback_samples"}
            fh.write(json.dumps({"key": key, "result": slim}, separators=(",", ":")) + "\n")


# ---------------------------------------------------------------------------
# the headline API
# ---------------------------------------------------------------------------


def compare(
    bot_x: str | os.PathLike[str],
    bot_y: str | os.PathLike[str],
    maps: Sequence[str] = ALL_15,
    seed: int = 1,
    workers: int | None = None,
    replays: bool = False,
    replay_dir: str | os.PathLike[str] | None = None,
    capture: bool = True,
    cache: str | os.PathLike[str] | None = None,
    progress=None,
) -> dict:
    """Exhaustive mirrored comparison of two bots.

    Plays every map with both side assignments (15 maps x 2 sides = 30 oriented
    games) and returns the antisymmetric score S in [-1, +1], where positive
    means X is better than Y.

    Set `replays=True` (with `replay_dir`) only when you need the replay files;
    replay I/O is roughly 200 kB per match and buys nothing for scoring.
    """
    x = resolve_bot(bot_x)
    y = resolve_bot(bot_y)
    map_names = [Path(m).stem for m in maps]
    map_paths = {m: str(resolve_map(m)) for m in map_names}
    mirror = os.path.normcase(str(x)) == os.path.normcase(str(y))

    if replay_dir is not None:
        replays = True
    if replays and replay_dir is None:
        replay_dir = Path("replays") / f"{bot_name(x)}_vs_{bot_name(y)}"
    if replays:
        Path(replay_dir).mkdir(parents=True, exist_ok=True)

    # Enumerate the 30 oriented games, then collapse to unique engine games.
    # A (bots, map, side) triple is played exactly once: in a mirror the two
    # orientations ARE the same triple, so 30 orientations become 15 games.
    orientations: list[tuple[str, str, str, str]] = []  # (map, role, a_path, b_path)
    for m in map_names:
        orientations.append((m, "x_as_a", str(x), str(y)))
        orientations.append((m, "y_as_a", str(y), str(x)))

    unique: dict[tuple[str, str, str], int] = {}
    plan: list[dict] = []
    for m, _role, a, b in orientations:
        key = (os.path.normcase(a), os.path.normcase(b), m)
        if key in unique:
            continue
        unique[key] = len(plan)
        spec = {
            "a": a,
            "b": b,
            "map": map_paths[m],
            "seed": seed,
            "capture": capture,
            "replay": None,
        }
        if replays:
            tag = "xa" if os.path.normcase(a) == os.path.normcase(str(x)) else "ya"
            spec["replay"] = str(Path(replay_dir) / f"{m}_{tag}.replay26")
        plan.append(spec)

    # cache lookup
    cached: dict[int, dict] = {}
    fx = fy = None
    if cache:
        store = _load_cache(cache)
        fx, fy = bot_fingerprint(x), bot_fingerprint(y)
        for (_na, _nb, m), idx in unique.items():
            a_is_x = os.path.normcase(plan[idx]["a"]) == os.path.normcase(str(x))
            fa, fb = (fx, fy) if a_is_x else (fy, fx)
            hit = store.get(_cache_key(fa, fb, m, seed, 0))
            if hit is not None and not plan[idx]["replay"]:
                cached[idx] = hit

    to_run = [spec for i, spec in enumerate(plan) if i not in cached]
    run_results, stats = run_matches(to_run, workers=workers, progress=progress)
    it = iter(run_results)
    results: list[dict] = []
    fresh: list[tuple[str, dict]] = []
    for i, spec in enumerate(plan):
        if i in cached:
            results.append(cached[i])
        else:
            r = next(it)
            results.append(r)
            if cache:
                m = Path(spec["map"]).stem
                a_is_x = os.path.normcase(spec["a"]) == os.path.normcase(str(x))
                fa, fb = (fx, fy) if a_is_x else (fy, fx)
                fresh.append((_cache_key(fa, fb, m, seed, 0), r))
    if cache:
        _append_cache(cache, fresh)
    stats["cache_hits"] = len(cached)

    def lookup(a: str, b: str, m: str) -> dict:
        return results[unique[(os.path.normcase(a), os.path.normcase(b), m)]]

    per_map = []
    x_wins = y_wins = draws = 0
    conds: Counter[str] = Counter()
    x_exc = y_exc = 0
    x_ti = x_col = y_ti = y_col = 0
    crashed = 0

    for m in map_names:
        g1 = lookup(str(x), str(y), m)  # X as A
        g2 = lookup(str(y), str(x), m)  # Y as A
        s1 = score_for_a(g1)  # score for X
        s2 = score_for_a(g2)  # score for Y
        s_m = 0.5 * (s1 - s2)

        # oriented win tally (30 slots even in a mirror, where both point at one game)
        for g, first_is_x in ((g1, True), (g2, False)):
            s = score_for_a(g)
            winner_is_x = (s == WIN) == first_is_x if s != DRAW else None
            if s == DRAW:
                draws += 1
            elif winner_is_x:
                x_wins += 1
            else:
                y_wins += 1

        x_ti += g1.get("a_titanium") or 0
        x_col += g1.get("a_titanium_collected") or 0
        x_ti += g2.get("b_titanium") or 0
        x_col += g2.get("b_titanium_collected") or 0
        y_ti += g1.get("b_titanium") or 0
        y_col += g1.get("b_titanium_collected") or 0
        y_ti += g2.get("a_titanium") or 0
        y_col += g2.get("a_titanium_collected") or 0

        per_map.append(
            {
                "map": m,
                "s_x_as_a": s1,
                "s_y_as_a": s2,
                "S_m": s_m,
                "x_as_a": {
                    "winner": g1.get("winner"),
                    "win_condition": g1.get("win_condition"),
                    "turns": g1.get("turns"),
                    "a_titanium_collected": g1.get("a_titanium_collected"),
                    "b_titanium_collected": g1.get("b_titanium_collected"),
                    "crashed": bool(g1.get("crashed")),
                },
                "y_as_a": {
                    "winner": g2.get("winner"),
                    "win_condition": g2.get("win_condition"),
                    "turns": g2.get("turns"),
                    "a_titanium_collected": g2.get("a_titanium_collected"),
                    "b_titanium_collected": g2.get("b_titanium_collected"),
                    "crashed": bool(g2.get("crashed")),
                },
            }
        )

    for r in results:
        conds[r.get("win_condition") or "unknown"] += 1
        if r.get("crashed"):
            crashed += 1
        a_is_x = os.path.normcase(r["a"]) == os.path.normcase(str(x))
        ae = r.get("a_exceptions") or 0
        be = r.get("b_exceptions") or 0
        if a_is_x:
            x_exc += ae
            y_exc += be
        else:
            y_exc += ae
            x_exc += be

    n = len(map_names)
    S = sum(p["S_m"] for p in per_map) / n if n else 0.0
    s_x_as_a_mean = sum(p["s_x_as_a"] for p in per_map) / n if n else 0.0
    s_y_as_a_mean = sum(p["s_y_as_a"] for p in per_map) / n if n else 0.0

    return {
        "x": bot_name(x),
        "y": bot_name(y),
        "x_path": str(x),
        "y_path": str(y),
        "mirror": mirror,
        "maps": map_names,
        "seed": seed,
        "oriented_games": 2 * n,
        "engine_games": len(plan),
        "S": S,
        "s_x_as_a_mean": s_x_as_a_mean,
        "s_y_as_a_mean": s_y_as_a_mean,
        "side_bias": 0.5 * (s_x_as_a_mean + s_y_as_a_mean),
        "per_map": per_map,
        "wins": {"x": x_wins, "y": y_wins, "draws": draws},
        "win_conditions": dict(conds.most_common()),
        "crashed": crashed,
        "exceptions": {"x": x_exc, "y": y_exc},
        "economy": {
            "x": {
                "titanium_collected_mean": x_col / (2 * n) if n else 0.0,
                "titanium_mean": x_ti / (2 * n) if n else 0.0,
            },
            "y": {
                "titanium_collected_mean": y_col / (2 * n) if n else 0.0,
                "titanium_mean": y_ti / (2 * n) if n else 0.0,
            },
        },
        "throughput": stats,
        "replay_dir": str(replay_dir) if replays else None,
        "results": results,
    }


def format_report(rep: dict) -> str:
    """Human-readable rendering of a `compare()` report."""
    x, y = rep["x"], rep["y"]
    lines: list[str] = []
    lines.append(f"{x}  vs  {y}    seed={rep['seed']}  maps={len(rep['maps'])}")
    lines.append(
        f"{rep['oriented_games']} oriented games / {rep['engine_games']} engine games"
        + ("  [mirror: sides collapse to one game per map]" if rep["mirror"] else "")
    )
    lines.append("")
    lines.append(f"{'map':<12} {x[:11]:>11} as A {y[:11]:>11} as A {'S_m':>7}   detail")
    lines.append("-" * 78)
    for p in rep["per_map"]:
        d1, d2 = p["x_as_a"], p["y_as_a"]
        lines.append(
            f"{p['map']:<12} {p['s_x_as_a']:>+14.1f} {p['s_y_as_a']:>+16.1f} {p['S_m']:>+7.2f}   "
            f"{d1['win_condition']}/{d2['win_condition']}"
        )
    lines.append("-" * 78)
    lines.append(f"{'AGGREGATE S':<12} {'':>14} {'':>16} {rep['S']:>+7.3f}")
    lines.append("")
    verdict = "X better" if rep["S"] > 0 else ("Y better" if rep["S"] < 0 else "dead even")
    lines.append(f"S({x}, {y}) = {rep['S']:+.4f}   ({verdict})")
    w = rep["wins"]
    lines.append(
        f"oriented wins: {x}={w['x']}  {y}={w['y']}  draws={w['draws']}"
        f"   (measured Team-A side bias {rep['side_bias']:+.3f})"
    )
    lines.append(f"win_condition histogram: {rep['win_conditions']}")
    lines.append(
        f"economy (absolute, per game): {x} collected={rep['economy']['x']['titanium_collected_mean']:.1f} "
        f"stored={rep['economy']['x']['titanium_mean']:.1f} | "
        f"{y} collected={rep['economy']['y']['titanium_collected_mean']:.1f} "
        f"stored={rep['economy']['y']['titanium_mean']:.1f}"
    )
    lines.append(f"unit-deleting exceptions: {x}={rep['exceptions']['x']}  {y}={rep['exceptions']['y']}")
    t = rep["throughput"]
    lines.append(
        f"crashed games: {rep['crashed']}   worker failures: {t.get('worker_failures') or 'none'}"
    )
    if rep["crashed"]:
        # S is antisymmetric, so a bot that crashes in BOTH orientations scores 0,
        # not -1. Zero here means "no evidence", not "even". Read this line first.
        lines.append(
            f"  !! {rep['crashed']}/{rep['engine_games']} games did not complete. S is NOT "
            "trustworthy: a bot that crashes on both sides scores S=0, not S=-1."
        )
    if rep["exceptions"]["x"] or rep["exceptions"]["y"]:
        lines.append(
            "  !! units were deleted by uncaught exceptions; run `python -m arena.strict <bot>`"
        )
    lines.append(
        f"throughput: {t['matches']} matches on {t['workers']} workers in "
        f"{t['wall_seconds']:.2f}s = {t['matches_per_sec']:.2f} matches/sec "
        f"({t['matches_per_hour']:,.0f} matches/hour)"
        + (f"   cache hits: {t['cache_hits']}" if t.get("cache_hits") else "")
    )
    return "\n".join(lines)


def _cli(argv: list[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Mirrored antisymmetric bot comparison.")
    ap.add_argument("bot_x")
    ap.add_argument("bot_y")
    ap.add_argument("--maps", nargs="*", default=list(ALL_MAPS))
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--replays", action="store_true")
    ap.add_argument("--replay-dir", default=None)
    ap.add_argument("--cache", default=None)
    ap.add_argument("--json", action="store_true", help="emit the full report as JSON")
    args = ap.parse_args(argv)

    rep = compare(
        args.bot_x,
        args.bot_y,
        maps=args.maps,
        seed=args.seed,
        workers=args.workers,
        replays=args.replays,
        replay_dir=args.replay_dir,
        cache=args.cache,
    )
    if args.json:
        slim = dict(rep)
        slim.pop("results", None)
        print(json.dumps(slim, indent=2))
    else:
        print(format_report(rep))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli(sys.argv[1:]))
