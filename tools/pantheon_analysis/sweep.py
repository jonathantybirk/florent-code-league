"""Run a bot against opponents over the whole map pool, both seats."""
import json, subprocess, sys, glob, os, statistics
from concurrent.futures import ThreadPoolExecutor

REPO = "/home/Ucals/projects/florent-code-league-llm-rl"
MAPS = sorted(glob.glob(f"{REPO}/maps/*.map26"))


SCRATCH = os.path.dirname(os.path.abspath(__file__)) + "/sweep_replays"
os.makedirs(SCRATCH, exist_ok=True)


def one(args):
    a, b, m, seed = args
    tag = f"{os.path.basename(a)}_{os.path.basename(b)}_{os.path.basename(m)}_{seed}"
    r = subprocess.run(
        ["fcode", "run", a, b, m, "--json", "--seed", str(seed), "--tle", "10",
         "--replay", f"{SCRATCH}/{tag}.replay26"],
        capture_output=True, text=True, cwd=REPO, timeout=600)
    try:
        start = r.stdout.index("{")
        d = json.loads(r.stdout[start:])
    except Exception:
        return None
    return (a, b, os.path.basename(m), d)


def main():
    me = sys.argv[1]
    opponents = sys.argv[2].split(",")
    seeds = [int(s) for s in sys.argv[3].split(",")] if len(sys.argv) > 3 else [1]
    jobs = []
    for opp in opponents:
        for m in MAPS:
            for s in seeds:
                jobs.append((me, opp, m, s))
                jobs.append((opp, me, m, s))
    with ThreadPoolExecutor(max_workers=8) as ex:
        results = [r for r in ex.map(one, jobs) if r]

    per_opp = {}
    rounds_won = []
    for a, b, m, d in results:
        opp = b if a == me else a
        rec = per_opp.setdefault(opp, [0, 0])
        won = (d.get("winner") == ("A" if a == me else "B"))
        rec[0] += won
        rec[1] += 1
        if won:
            rounds_won.append(d.get("turns") or 0)
    total = [0, 0]
    for opp, (w, n) in sorted(per_opp.items()):
        print(f"  vs {os.path.basename(opp):28s} {w:3d}/{n:3d}  {100*w/n:5.1f}%")
        total[0] += w
        total[1] += n
    print(f"  {'TOTAL':31s} {total[0]:3d}/{total[1]:3d}  {100*total[0]/total[1]:5.1f}%")
    if rounds_won:
        print(f"  median rounds in wins: {statistics.median(rounds_won):.0f}")


main()
