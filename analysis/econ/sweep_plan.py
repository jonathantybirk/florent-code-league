"""Engine sweep with planner-generated plans: near-optimal execution, full
knowledge. Compares engine reality against the planner's prediction."""
import json, os, re, subprocess, sys
from concurrent.futures import ProcessPoolExecutor
sys.path.insert(0, 'analysis/econ')
from maplib import WALL, read_map
from mapstats import CORES, footprint
from planner import plan

ROOT = "/Users/jonathantybirk/Documents/GitHub/florent-code-league"
SCR = "/private/tmp/claude-501/-Users-jonathantybirk-Documents-GitHub-florent-code-league/2c47d030-787d-4a82-a6f5-224c333e01c1/scratchpad"
MAPS = list(CORES)
NBS = [1, 2, 3, 4, 6]


def make_plan(m, nb):
    w, h, rows = read_map(f"{ROOT}/maps/{m}.map26")
    ca, cb = CORES[m]
    p = plan(m, nb)
    d = {"w": w, "h": h,
         "walls": [[x, y] for y in range(h) for x in range(w) if rows[y][x] == WALL],
         "foot": [list(t) for t in footprint(ca)],
         "efoot": [list(t) for t in footprint(cb)],
         "jobs": [b["jobs"] for b in p["builders"]]}
    path = f"{SCR}/plan_{m}_{nb}.json"
    json.dump(d, open(path, "w"))
    return path, p["revenue"], p["connected"], p["total_ore"]


def one(a):
    m, nb = a
    path, pred, conn, tot = make_plan(m, nb)
    env = dict(os.environ, EP_PLAN=path)
    r = subprocess.run(["uv", "run", "fcode", "run", "exec_plan", "do_nothing_bot", m,
                        "--replay", f"{SCR}/pl_{m}_{nb}.replay26"],
                       cwd=ROOT, env=env, capture_output=True, text=True)
    mm = re.search(r"Titanium\s+([\d,]+) \(([\d,]+) mined\)", r.stdout)
    return m, nb, int(mm.group(2).replace(",", "")) if mm else None, pred, conn, tot


if __name__ == "__main__":
    jobs = [(m, nb) for m in MAPS for nb in NBS]
    with ProcessPoolExecutor(max_workers=8) as ex:
        rows = list(ex.map(one, jobs))
    d = {(m, nb): (v, pred, c, t) for m, nb, v, pred, c, t in rows}
    print("ENGINE, planner-driven (full knowledge, exact pathing)")
    print(f"{'map':<11}" + "".join(f"{f'NB={n}':>9}" for n in NBS) + "   ore  predicted(NB=4)")
    tot = {n: 0 for n in NBS}
    for m in MAPS:
        vs = [d[(m, n)][0] for n in NBS]
        for n, v in zip(NBS, vs):
            tot[n] += v or 0
        print(f"{m:<11}" + "".join(f"{v if v is not None else '-':>9}" for v in vs)
              + f"   {d[(m,4)][3]:>3}  {d[(m,4)][1]:>8.0f}")
    print(f"{'TOTAL':<11}" + "".join(f"{tot[n]:>9}" for n in NBS))
    print(f"{'vs NB=1':<11}" + "".join(f"{100*tot[n]/tot[1]-100:>8.1f}%" for n in NBS))
    print()
    for n in NBS:
        pr = sum(d[(m, n)][1] for m in MAPS)
        print(f"  NB={n}: engine={tot[n]:>7}  planner_predicted={pr:>8.0f}  "
              f"engine/predicted={100*tot[n]/pr:.1f}%")
