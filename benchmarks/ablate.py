"""Build single-change ablation copies of a bot and score each against a panel.

Every variant is the shipped bot with exactly one edit applied, so a score
difference is attributable. Variants live under benchmarks/ablations/ (a
scratch area, not bots/, so tournament discovery never sees them).

    uv run python -m benchmarks.ablate --run-dir benchmarks/runs/ab1
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BASE = REPO / "bots/luc/ragnarok"
OUT = REPO / "benchmarks/ablations"

PANEL = ["vigil", "tempest_reinf", "prospect", "mistral", "vanguard",
         "gobbleglitch"]

# name -> (file, old, new). "" means the shipped build, no edit.
VARIANTS: dict[str, tuple[str, str, str] | None] = {
    "rag": None,
    "rag_norush": (
        "doctrine.py",
        "    if on_side and on_end:\n        return FORTIFY\n    return RUSH",
        "    if on_side and on_end:\n        return RUSH\n    return RUSH",
    ),
    "rag_nofield": ("doctrine.py", "_FIELD_GUNNERS = {RUSH: 0, FORTIFY: 2}",
                    "_FIELD_GUNNERS = {RUSH: 0, FORTIFY: 0}"),
    "rag_noseal": ("constants.py", "SEAL_TITANIUM_RESERVE = 25",
                   "SEAL_TITANIUM_RESERVE = 100000"),
    "rag_nosentinel": ("constants.py", "MIN_AMMO_FOR_SENTINEL = 40",
                       "MIN_AMMO_FOR_SENTINEL = 100000"),
    "rag_noretire": ("constants.py", "LAUNCHER_QUIET_ROUNDS = 45",
                     "LAUNCHER_QUIET_ROUNDS = 100000"),
    "rag_noexpand": ("constants.py", "NETWORK_CAP_LATE = 8",
                     "NETWORK_CAP_LATE = 4"),
    "rag_nolane": ("builder.py", "    if _block_firing_lane(p, ct, enemies):",
                   "    if False and _block_firing_lane(p, ct, enemies):"),
    "rag_nodeny": ("builder.py", "    if _deny_enemy_ore(p, ct):",
                   "    if False and _deny_enemy_ore(p, ct):"),
    "rag_blitz0": ("doctrine.py", "BLITZ_MAX_DISTANCE = 8",
                   "BLITZ_MAX_DISTANCE = -1"),
    "rag_blitz6": ("doctrine.py", "BLITZ_MAX_DISTANCE = 8",
                   "BLITZ_MAX_DISTANCE = 6"),
    # Empty the atlas index so every lookup misses and the bot runs its fair
    # observation-and-symmetry path on every map. Behaviourally identical to
    # deleting the atlas, which is what shipping fair would require.
    "rag_noatlas": ("atlas.py", "_INDEX = {", "_INDEX = {}\n_UNUSED = {"),
}


def build(name: str) -> Path:
    dest = OUT / name
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    for f in BASE.rglob("*"):
        if f.is_file() and "__pycache__" not in f.parts:
            target = dest / f.relative_to(BASE)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(f.read_bytes())
    edit = VARIANTS[name]
    if edit is not None:
        path, old, new = edit
        source = (dest / path).read_text()
        if old not in source:
            raise SystemExit(f"{name}: pattern not found in {path}:\n{old}")
        (dest / path).write_text(source.replace(old, new, 1))
    return dest


def score(run_dir: Path, variants: list[str]) -> dict[str, dict[str, float]]:
    # Identity comes from the filename, not schedule.json: one run directory
    # holds every variant's duels and each suite invocation rewrites the
    # schedule, so only the last one would survive.
    points: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for path in (run_dir / "results").glob("duel-*.json"):
        row = json.loads(path.read_text())
        if row.get("status") != "ok":
            continue
        left, _, right = path.stem[len("duel-"):].partition("-vs-")
        a, b = left, right.rsplit("-", 1)[0]
        win = 1.0 if str(row["engine"]["winner"]).lower() == "a" else 0.0
        if row["metrics"]["win_condition"] == "coinflip":
            win = 0.5
        for bot, value, opponent in ((a, win, b), (b, 1 - win, a)):
            if bot in variants:
                points[bot][opponent] += value
                counts[bot][opponent] += 1
    return {v: {"total": sum(points[v].values()),
                "games": sum(counts[v].values()),
                **{o: points[v][o] for o in sorted(points[v])}}
            for v in variants if counts[v]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--variants", default=",".join(VARIANTS))
    parser.add_argument("--panel", default=",".join(PANEL))
    parser.add_argument("--maps", default=None)
    parser.add_argument("--jobs", type=int, default=14)
    args = parser.parse_args()

    variants = args.variants.split(",")
    registrations = []
    for name in variants:
        path = build(name)
        registrations += ["--register", f"{name}={path.relative_to(REPO)}"]

    for name in variants:
        command = [sys.executable, "-m", "benchmarks.suite",
                   "--run-dir", str(args.run_dir), "--duel", name,
                   "--opponents", args.panel, "--jobs", str(args.jobs)]
        if args.maps:
            command += ["--maps", args.maps]
        subprocess.run(command + registrations, cwd=REPO, check=True)

    table = score(args.run_dir.resolve(), variants)
    opponents = args.panel.split(",")
    print("\n| variant | total | " + " | ".join(opponents) + " |")
    print("|" + "---|" * (len(opponents) + 2))
    for name in sorted(table, key=lambda n: -table[n]["total"]):
        row = table[name]
        cells = " | ".join(f"{row.get(o, 0):.1f}" for o in opponents)
        print(f"| {name} | **{row['total']:.1f}**/{row['games']} | {cells} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
