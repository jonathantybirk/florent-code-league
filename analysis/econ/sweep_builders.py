"""Sweep builder count across all shipped maps. Opponent does nothing, so this
measures pure opening-economy throughput with no combat interference."""
import os, re, subprocess, sys
from concurrent.futures import ProcessPoolExecutor

ROOT = "/Users/jonathantybirk/Documents/GitHub/florent-code-league"
SCR = "/private/tmp/claude-501/-Users-jonathantybirk-Documents-GitHub-florent-code-league/2c47d030-787d-4a82-a6f5-224c333e01c1/scratchpad"
MAPS = ["atoll", "aurora", "crossfire", "duel", "fjord", "hive", "longship",
        "pinch", "quarry", "runestone", "skerry", "sprint", "strait", "twins", "vault"]


def one(args):
    mapname, nb, extra = args
    env = dict(os.environ, EL_BUILDERS=str(nb), EL_DEBUG="0", EL_REUSE="0", **extra)
    tag = f"{mapname}_{nb}_{'_'.join(sorted(extra.values())) or 'd'}"
    p = subprocess.run(
        ["uv", "run", "fcode", "run", "econ_lab", "do_nothing_bot", mapname,
         "--replay", f"{SCR}/sw_{tag}.replay26"],
        cwd=ROOT, env=env, capture_output=True, text=True)
    m = re.search(r"Titanium\s+([\d,]+) \(([\d,]+) mined\)", p.stdout)
    b = re.search(r"Buildings\s+(\d+)", p.stdout)
    if not m:
        return mapname, nb, None, None, p.stdout[-300:]
    return mapname, nb, int(m.group(2).replace(",", "")), int(b.group(1)), ""


if __name__ == "__main__":
    nbs = [1, 2, 3, 4, 5, 6, 8]
    jobs = [(m, nb, {}) for m in MAPS for nb in nbs]
    with ProcessPoolExecutor(max_workers=8) as ex:
        rows = list(ex.map(one, jobs))
    data = {}
    for mp, nb, mined, blds, err in rows:
        if err:
            print("ERR", mp, nb, err, file=sys.stderr)
        data[(mp, nb)] = mined
    print(f"{'map':<11}" + "".join(f"{f'NB={n}':>9}" for n in nbs) + "   best")
    tot = {n: 0 for n in nbs}
    for mp in MAPS:
        vals = [data.get((mp, n)) for n in nbs]
        best = nbs[max(range(len(nbs)), key=lambda i: vals[i] or -1)]
        for n, v in zip(nbs, vals):
            tot[n] += v or 0
        print(f"{mp:<11}" + "".join(f"{v if v is not None else '-':>9}" for v in vals)
              + f"   {best}")
    print(f"{'TOTAL':<11}" + "".join(f"{tot[n]:>9}" for n in nbs))
    base = tot[1]
    print(f"{'vs NB=1':<11}" + "".join(f"{100*tot[n]/base-100:>8.1f}%" for n in nbs))
