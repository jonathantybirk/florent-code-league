"""Head-to-head arena with a diagnostic breakdown of why matches were lost.

    uv run python scratch/arena.py <botA> <botB> [-v] [--maps a,b] [--seeds 1,2]
"""
import argparse
import concurrent.futures as cf
import os
import pathlib
import re
import statistics
import subprocess
import sys
import tempfile
import hashlib
from collections import defaultdict

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import replaylib  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
MAPS = sorted(p.name[:-6] for p in (ROOT / "maps").glob("*.map26"))
RESULT_RE = re.compile(r"Winner:\s+(\S+)\s+\((.*?), turn (\d+)\)")
KINDS = ("builder", "harvester", "conveyor", "gunner", "launcher")


def play(a, b, mapname, seed, tle):
    handle, replay = tempfile.mkstemp(suffix=".replay26")
    os.close(handle)
    cmd = ["uv", "run", "fcode", "run", a, b, f"maps/{mapname}.map26",
           "--replay", replay, "--seed", str(seed), "--tle", str(tle)]
    try:
        out = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                             timeout=300).stdout.replace("\n", " ")
        match = RESULT_RE.search(out)
        if match is None:
            return None
        winner, reason, turn = match.group(1), match.group(2), int(match.group(3))
        an, bn = a.split("/")[-1], b.split("/")[-1]
        side = "A" if winner == an else ("B" if winner == bn else "?")
        return dict(side=side, reason=reason, turn=turn,
                    summary=replaylib.summarize(replay))
    except Exception as error:  # noqa: BLE001
        return dict(side="?", reason=f"error:{error}", turn=0, summary=None)
    finally:
        try:
            os.unlink(replay)
        except OSError:
            pass


def fingerprint(bot):
    """Hash a bot's sources so we can tell if it changed under us."""
    root = ROOT / "bots" / bot
    digest = hashlib.md5()
    for path in sorted(root.rglob("*.py")):
        digest.update(path.read_bytes())
    return digest.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--maps", default=None)
    ap.add_argument("--seeds", default="1")
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--tle", type=int, default=10,
                    help="per-turn limit in ms (server default: 10)")
    ap.add_argument("-v", action="store_true")
    args = ap.parse_args()

    maps = args.maps.split(",") if args.maps else MAPS
    seeds = [int(s) for s in args.seeds.split(",")]
    jobs = [(args.a, args.b, m, s, args.tle, "fwd")
            for m in maps for s in seeds]
    jobs += [(args.b, args.a, m, s, args.tle, "rev")
             for m in maps for s in seeds]

    # Another agent edits some of these bots live, and a run measured against a
    # bot that changed halfway through is worthless. Fingerprint both ends.
    before = {b: fingerprint(b) for b in (args.a, args.b)}
    wins = defaultdict(int)
    rows = []
    stats = {"a": defaultdict(list), "b": defaultdict(list)}
    with cf.ThreadPoolExecutor(args.jobs) as ex:
        futures = {ex.submit(play, *j[:5]): j for j in jobs}
        for future in cf.as_completed(futures):
            job = futures[future]
            result = future.result()
            if result is None or result["side"] == "?":
                wins["?"] += 1
                continue
            forward = job[5] == "fwd"
            # Engine team 0 is always the bot passed first on the command line.
            mine, theirs = (0, 1) if forward else (1, 0)
            key = "a" if (result["side"] == "A") == forward else "b"
            wins[key] += 1
            rows.append((job[2], job[3], job[5], key, result["reason"],
                         result["turn"]))
            summary = result["summary"]
            if summary is None:
                continue
            for who, team in (("a", mine), ("b", theirs)):
                for kind in KINDS:
                    stats[who][kind].append(summary["built"][team].get(kind, 0))
                born = summary["first"].get((team, "gunner"))
                stats[who]["first_gunner"].append(9999 if born is None else born)
                stats[who]["fed"].append(summary["fed"].get(team, 0))
                stats[who]["shots"].append(summary["shots"])
            stats["a"]["turn"].append(result["turn"])

    if args.v:
        for row in sorted(rows):
            print(f"  {row[0]:12s} seed{row[1]} {row[2]:3s} -> {row[3]}  "
                  f"{row[4]} t{row[5]}")

    changed = [b for b, h in before.items() if fingerprint(b) != h]
    if changed:
        print(f"!! CONTAMINATED: {', '.join(changed)} changed during this run")
    total = wins["a"] + wins["b"]
    print(f"{args.a} {wins['a']} - {wins['b']} {args.b}   "
          f"({100 * wins['a'] / max(total, 1):.1f}%)  errors={wins['?']}")

    def show(who, label):
        parts = [f"{label:>7s}"]
        for kind in KINDS:
            values = stats[who][kind]
            parts.append(f"{kind[:4]}={statistics.mean(values):4.1f}"
                         if values else f"{kind[:4]}=   -")
        shots = stats[who]["shots"]
        parts.append(f"shots={statistics.mean(shots):5.1f}" if shots
                     else "shots=    -")
        got = [v for v in stats[who]["first_gunner"] if v < 9999]
        share = 100 * len(got) / max(len(stats[who]["first_gunner"]), 1)
        parts.append(f"gun1@r{statistics.median(got):.0f}" if got else "gun1@ -")
        parts.append(f"in {share:.0f}% of games")
        print("  ".join(parts))

    if stats["a"]["builder"]:
        show("a", "A")
        show("b", "B")
        print(f"        median match length "
              f"r{statistics.median(stats['a']['turn']):.0f}")


main()
