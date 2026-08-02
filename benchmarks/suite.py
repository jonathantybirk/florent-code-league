"""Benchmark suite orchestrator.

Materialises pinned bots with `git archive`, builds a match schedule for the
requested suites, runs each match in its own subprocess (the engine hosts both
bots inside the calling process, so isolation is per-match), and leaves one
JSON per match under the run directory.

    uv run python -m benchmarks.suite --run-dir benchmarks/runs/<name> \
        --suites econ,stress,breach,defense,h2h --jobs 14

Re-running skips matches whose result file already exists.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tarfile
import io
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# name -> (git ref or None for working tree, path). Entry point is main.py.
BOTS: dict[str, tuple[str | None, str]] = {
    # Luc lineage (x/luc working tree).
    "ragnarok": (None, "bots/luc/ragnarok"),
    "vigil": (None, "bots/luc/vigil"),
    "prospect": (None, "bots/luc/prospect"),
    "prospect_rushonly": (None, "bots/luc/prospect_rushonly"),
    "tempest_reinf": (None, "bots/luc/tempest_reinforcements"),
    # Jon current fair lineage.
    "casemate": ("origin/x/jon", "bots/jon/fair/casemate"),
    "vanguard": ("origin/x/jon", "bots/jon/fair/vanguard"),
    "undertow": ("origin/x/jon", "bots/jon/fair/undertow"),
    "tempest_jon": ("origin/x/jon", "bots/jon/fair/tempest"),
    "tempest_fast": ("origin/x/jon", "bots/jon/fair/tempest_fast"),
    "mistral": ("origin/x/jon", "bots/jon/fair/mistral"),
    "mistral_fast": ("origin/x/jon", "bots/jon/fair/mistral_fast"),
    "jonbot": ("origin/x/jon", "bots/jon/fair/jonbot"),
    # Jon ancestors (the regression-hypothesis time axis).
    "vg_v1": ("origin/x/jon", "bots/jon/legacy/vg_v1"),
    "vg_v5": ("origin/x/jon", "bots/jon/legacy/vg_v5"),
    "vg_v7": ("origin/x/jon", "bots/jon/legacy/vg_v7"),
    "titanium_v1": ("origin/x/jon", "bots/jon/legacy/archive/titanium_v1"),
    "frontier": ("origin/x/jon", "bots/jon/legacy/archive/frontier"),
    "riptide": ("origin/x/jon", "bots/jon/legacy/riptide"),
    "turtle": ("origin/x/jon", "bots/jon/legacy/turtle"),
    # Elias.
    "autistimusprime": ("origin/elias_dev", "bots/elias/unfair/autistimusprime"),
    "gobbleglitch": ("origin/elias_dev", "bots/elias/unfair/gobbleglitch"),
    # Viktor + baseline.
    "green": ("origin/viktor", "bots/green"),
    "starter": ("origin/main", "bots/starter"),
}

TIPS = [
    "vigil", "prospect", "tempest_reinf", "casemate", "vanguard", "undertow",
    "mistral", "tempest_jon", "jonbot", "autistimusprime", "gobbleglitch",
    "green",
]

ECON_MAPS = ["sprint", "fjord", "quarry", "string", "hive"]
STRESS_MAPS = ["twins", "pinch", "vase"]
BREACH_MAPS = ["bridge", "vase", "quarry", "duel", "showdown"]
DEFENSE_MAPS = ["sprint", "duel", "showdown", "twins", "fjord"]
H2H_MAPS = ["bridge", "quarry", "vase", "string", "jackpot",
            "duel", "showdown", "fjord", "twins", "sprint"]

DEFENDERS = ["casemate", "turtle"]
RUSHERS = ["mistral_fast", "prospect_rushonly"]


def materialise(run_dir: Path, names: set[str]) -> dict[str, Path]:
    stage = run_dir / "stage"
    result: dict[str, Path] = {}
    for name in sorted(names):
        ref, path = BOTS[name]
        dest = stage / name
        result[name] = dest / "main.py"
        if dest.exists():
            continue
        dest.mkdir(parents=True)
        if ref is None:
            src = REPO / path
            for f in src.rglob("*"):
                if f.is_file() and "__pycache__" not in f.parts:
                    target = dest / f.relative_to(src)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(f.read_bytes())
        else:
            archive = subprocess.run(
                ["git", "archive", f"{ref}:{path}"],
                cwd=REPO, check=True, capture_output=True,
            ).stdout
            with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
                tar.extractall(dest, filter="data")
    return result


def schedule(suites: list[str], subjects: list[str]) -> list[dict]:
    matches: list[dict] = []

    def add(kind, a, b, map_name, a_path=None, b_path=None):
        matches.append({
            "kind": kind, "a": a, "b": b, "map": map_name,
            "a_path": a_path, "b_path": b_path,
            "id": f"{kind}-{a}-vs-{b}-{map_name}",
        })

    probe = str(REPO / "benchmarks/probes")
    if "econ" in suites:
        for bot in subjects:
            for map_name in ECON_MAPS:
                add("econ", bot, "idle", map_name,
                    b_path=f"{probe}/idle/entry.py")
    if "stress" in suites:
        for bot in subjects:
            for map_name in STRESS_MAPS:
                add("stress", bot, "denier", map_name,
                    b_path=f"{probe}/denier/entry.py")
    if "breach" in suites:
        for bot in subjects:
            for defender in DEFENDERS:
                if defender == bot:
                    continue
                for map_name in BREACH_MAPS:
                    add("breach", bot, defender, map_name)
    if "defense" in suites:
        for bot in subjects:
            for rusher in RUSHERS:
                if rusher == bot:
                    continue
                for map_name in DEFENSE_MAPS:
                    add("defense", bot, rusher, map_name)
    if "h2h" in suites:
        for i, a in enumerate(TIPS):
            for b in TIPS[i + 1:]:
                for map_name in H2H_MAPS:
                    add("h2h", a, b, map_name)
                    add("h2h", b, a, map_name)
    return matches


ALL_MAPS = ["atoll", "aurora", "bridge", "crossfire", "duel", "fjord", "hive",
            "jackpot", "longship", "pinch", "quarry", "runestone", "showdown",
            "skerry", "sprint", "strait", "string", "sweden", "twins", "vase",
            "vault"]


def duel_schedule(candidate: str, opponents: list[str],
                  maps: list[str]) -> list[dict]:
    matches = []
    for opponent in opponents:
        for map_name in maps:
            for a, b in ((candidate, opponent), (opponent, candidate)):
                matches.append({
                    "kind": "duel", "a": a, "b": b, "map": map_name,
                    "a_path": None, "b_path": None,
                    "id": f"duel-{a}-vs-{b}-{map_name}",
                })
    return matches


def run_suite(run_dir: Path, matches: list[dict], jobs: int) -> None:
    results = run_dir / "results"
    results.mkdir(parents=True, exist_ok=True)
    needed = {m["a"] for m in matches if m["a_path"] is None}
    needed |= {m["b"] for m in matches if m["b_path"] is None}
    staged = materialise(run_dir, needed)

    pending = [m for m in matches
               if not (results / f"{m['id']}.json").exists()]
    print(f"{len(matches)} scheduled, {len(pending)} to run", flush=True)
    started = time.time()
    done = 0

    def run_one(m: dict) -> str:
        a = m["a_path"] or str(staged[m["a"]])
        b = m["b_path"] or str(staged[m["b"]])
        out = results / f"{m['id']}.json"
        cmd = [sys.executable, str(REPO / "benchmarks/run_one.py"),
               "--a", a, "--b", b,
               "--map", str(REPO / "maps" / f"{m['map']}.map26"),
               "--seed", "1", "--out", str(out)]
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=600, cwd=REPO)
        if proc.returncode != 0 and not out.exists():
            out.write_text(json.dumps({
                "status": "error", "a": m["a"], "b": m["b"], "map": m["map"],
                "error": proc.stderr[-500:],
            }) + "\n")
        return m["id"]

    with ThreadPoolExecutor(max_workers=jobs) as pool:
        for match_id in pool.map(run_one, pending):
            done += 1
            if done % 25 == 0 or done == len(pending):
                rate = done / max(time.time() - started, 1)
                print(f"  {done}/{len(pending)} ({rate:.1f}/s)", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--suites", default="econ,stress,breach,defense,h2h")
    parser.add_argument("--subjects", default=None,
                        help="comma list; default: all registered bots")
    parser.add_argument("--duel", default=None,
                        help="candidate vs --opponents on --maps, both orders")
    parser.add_argument("--opponents", default=None)
    parser.add_argument("--maps", default=None,
                        help="comma list; default H2H_MAPS, 'all' for pool")
    parser.add_argument("--register", action="append", default=[],
                        metavar="NAME=PATH",
                        help="add a working-tree bot, e.g. an ablation build")
    parser.add_argument("--jobs", type=int, default=14)
    args = parser.parse_args()

    for entry in args.register:
        name, _, path = entry.partition("=")
        BOTS[name] = (None, path)

    if args.duel:
        maps = (ALL_MAPS if args.maps == "all"
                else args.maps.split(",") if args.maps else H2H_MAPS)
        matches = duel_schedule(args.duel, args.opponents.split(","), maps)
    else:
        subjects = (args.subjects.split(",") if args.subjects
                    else list(BOTS))
        matches = schedule(args.suites.split(","), subjects)
    run_dir = args.run_dir.resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "schedule.json").write_text(json.dumps(matches, indent=1))
    run_suite(run_dir, matches, args.jobs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
