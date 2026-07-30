"""Is the 10 Ti/round cap per conveyor line, or per core?

Two independent trunks feed two different core tiles, 4 harvesters each.
Per-line cap  => ~20 Ti/round of harvest.  Per-core cap => ~10 Ti/round.
"""
import json, os, re, subprocess, sys
sys.path.insert(0, 'analysis/econ')
import fixtures
from maplib import EMPTY, ORE, write_map_with_cores, render

import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent))
from harness import ROOT, SCRATCH  # noqa: E402
W = H = 24
ORE_A = [(x, 1) for x in (6, 8, 10, 12)]     # feed trunk on row 2
ORE_B = [(x, 4) for x in (6, 8, 10, 12)]     # feed trunk on row 3


def build_map():
    rows = [[EMPTY] * W for _ in range(H)]
    for x, y in ORE_A + ORE_B:
        rows[y][x] = ORE
        rows[H - 1 - y][W - 1 - x] = ORE
    pass
    return rows


def tasks():
    t = []
    for x in range(13, 3, -1):                    # trunk A: row 2 -> core (3,2)
        t.append(["conveyor", x, 2, "west", 0])
    for x in range(13, 3, -1):                    # trunk B: row 3 -> core (3,3)
        t.append(["conveyor", x, 3, "west", 0])
    for i, (x, y) in enumerate(ORE_A):
        t.append(["harvester", x, y, None, 200 + i * 0])
    for i, (x, y) in enumerate(ORE_B):
        t.append(["harvester", x, y, None, 400])
    return t


def run(tasklist, mapname):
    json.dump({"tasks": tasklist}, open(f"{SCRATCH}/c.json", "w"))
    env = dict(os.environ, FCODE_ECON_CFG=f"{SCRATCH}/c.json")
    out = subprocess.run(["uv", "run", "fcode", "run", "jon/probes/probe_script", "common/donothingbot",
                          mapname, "--replay", f"{SCRATCH}/x.replay26"],
                         cwd=ROOT, env=env, capture_output=True, text=True).stderr
    res, ev = {}, []
    for l in out.splitlines():
        m = re.match(r"T (\d+) res=(\d+) scale=([\d.]+)", l)
        if m:
            res[int(m.group(1))] = (int(m.group(2)), float(m.group(3)))
        elif l.startswith("BUILD"):
            ev.append(l)
    return res, ev


def rate(res, a, b):
    return (res[b][0] - res[a][0]) / (b - a)


if __name__ == "__main__":
    build_map()
    res, ev = run(tasks(), fixtures.twoline())
    print("\n".join(e for e in ev if "harvester" in e))
    print(f"\ntotal builds: {len(ev)}")
    print(f"rate rounds 340-390 (4 harvesters, trunk A only): {rate(res,340,390):.3f}")
    print(f"rate rounds 600-990 (8 harvesters, two trunks)  : {rate(res,600,990):.3f}")
    print(f"  passive is 2.50; per-line cap predicts 22.50, per-core cap predicts 12.50")
