"""Play every version of a bot lineage against every other, and rank them.

A lineage is a sequence of commits to one bot directory, each of which its
author believed was an improvement. That belief is usually tested against
whatever the previous build was, one step at a time, which is exactly the
measurement that accumulates error: a change that beats its immediate
predecessor can still be worse than something five commits back, and nothing
in a linear workflow ever notices.

This plays them all against each other on the full map pool in both seats, so
the ranking is transitive evidence rather than a chain of pairwise claims.

    uv run python tools/roundrobin.py --ref origin/x/luc --path bots/luc/hildr
    uv run python tools/roundrobin.py --ref origin/x/luc --path bots/luc/hildr \
        --maps holmgang,skald,helheim --limit 8
"""

from __future__ import annotations

import argparse
import itertools
import json
import shutil
import subprocess
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sweep import POOL, ROOT, play  # noqa: E402

STAGE = Path("/tmp/lineage")


def versions(ref: str, path: str, limit: int | None):
    out = subprocess.run(
        ["git", "log", ref, "--format=%h|%ci|%s", "--", path],
        cwd=ROOT, capture_output=True, text=True, check=True).stdout
    rows = []
    for line in out.splitlines():
        sha, when, subject = line.split("|", 2)
        rows.append((sha, when[:16], subject))
    rows.reverse()                       # oldest first, so ranks read as history
    if limit:
        rows = rows[-limit:]
    return rows


def stage(sha: str, path: str) -> Path | None:
    """Extract one version, skipping any whose code is byte-identical."""
    dest = STAGE / sha
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    archive = subprocess.run(["git", "archive", sha, path],
                             cwd=ROOT, capture_output=True)
    if archive.returncode != 0:
        return None
    depth = len(Path(path).parts)
    untar = subprocess.run(
        ["tar", "-x", "-C", str(dest), f"--strip-components={depth}"],
        input=archive.stdout, capture_output=True)
    if untar.returncode != 0 or not (dest / "main.py").exists():
        return None
    return dest


def code_hash(directory: Path) -> str:
    """Hash only the .py files -- a README or a metadata file is not the bot."""
    import hashlib
    digest = hashlib.md5()
    for file in sorted(directory.rglob("*.py")):
        digest.update(file.relative_to(directory).as_posix().encode())
        digest.update(file.read_bytes())
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ref", default="origin/x/luc")
    parser.add_argument("--path", default="bots/luc/hildr")
    parser.add_argument("--maps", default=",".join(POOL))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--jobs", type=int, default=10)
    parser.add_argument("--extra", default="",
                        help="comma-separated bot dirs to include in the field")
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()

    maps = [m.strip() for m in args.maps.split(",") if m.strip()]
    rows = versions(args.ref, args.path, args.limit)

    field, meta, seen_hashes = [], {}, {}
    for sha, when, subject in rows:
        directory = stage(sha, args.path)
        if directory is None:
            continue
        digest = code_hash(directory)
        if digest in seen_hashes:
            # Same Python, different commit: playing it twice measures nothing
            # and distorts every rating in the field.
            meta[seen_hashes[digest]]["aliases"].append(sha)
            continue
        seen_hashes[digest] = sha
        field.append(str(directory))
        meta[sha] = {"when": when, "subject": subject, "dir": str(directory),
                     "aliases": []}
    for extra in (e.strip() for e in args.extra.split(",") if e.strip()):
        field.append(extra)
        meta[extra] = {"when": "", "subject": "(reference bot)", "dir": extra,
                       "aliases": []}
    by_dir = {v["dir"]: k for k, v in meta.items()}
    print(f"{len(field)} distinct builds x {len(maps)} maps, both seats "
          f"= {len(field) * (len(field) - 1) // 2 * len(maps) * 2} games\n")

    tasks = []
    for a, b in itertools.combinations(field, 2):
        for map_name in maps:
            tasks.append((a, b, map_name, 1, 0))
            tasks.append((b, a, map_name, 1, 0))
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        results = list(pool.map(play, tasks))

    wins = defaultdict(float)
    games = defaultdict(int)
    head = defaultdict(lambda: defaultdict(float))
    for task, result in zip(tasks, results):
        if "error" in result or result.get("winner") not in ("A", "B"):
            continue
        a, b = task[0], task[1]
        winner = a if result["winner"] == "A" else b
        loser = b if winner is a else a
        wins[winner] += 1
        games[winner] += 1
        games[loser] += 1
        head[winner][loser] += 1

    order = sorted(field, key=lambda d: -(wins[d] / games[d] if games[d] else 0))
    print(f"{'#':>3}  {'commit':<9}{'when':<17}{'win%':>6}{'games':>7}  subject")
    for rank, directory in enumerate(order, 1):
        key = by_dir[directory]
        info = meta[key]
        rate = wins[directory] / games[directory] if games[directory] else 0
        alias = f" (+{len(info['aliases'])} identical)" if info["aliases"] else ""
        print(f"{rank:>3}  {key:<9}{info['when']:<17}{rate:>5.1%}"
              f"{games[directory]:>7}  {info['subject'][:70]}{alias}")

    if args.json_out:
        args.json_out.write_text(json.dumps(
            {"meta": {by_dir[d]: meta[by_dir[d]] for d in field},
             "wins": {by_dir[d]: wins[d] for d in field},
             "games": {by_dir[d]: games[d] for d in field},
             "head_to_head": {by_dir[a]: {by_dir[b]: v for b, v in row.items()}
                              for a, row in head.items()}}, indent=2))


if __name__ == "__main__":
    main()
