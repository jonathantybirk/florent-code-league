"""Engine tempo curves: titanium DELIVERED by round H, for each builder count.

Spending is reconstructed exactly from the scale trace: a +20 jump is a builder
(cost floor(30*S/100) at the pre-jump scale S), +5 a harvester, +1 a conveyor.
delivered(H) = res(H) - 500 - passive(H) + spend(H)
"""
import os, re, subprocess, sys
from concurrent.futures import ProcessPoolExecutor
sys.path.insert(0, 'analysis/econ')
from mapstats import CORES
from sweep_plan import make_plan

ROOT = "/Users/jonathantybirk/Documents/GitHub/florent-code-league"
SCR = "/private/tmp/claude-501/-Users-jonathantybirk-Documents-GitHub-florent-code-league/2c47d030-787d-4a82-a6f5-224c333e01c1/scratchpad"
HZ = [150, 250, 400, 999]
NBS = [1, 2, 3, 4]
BASE = {20: 30, 5: 20, 1: 3}      # scale delta -> base cost


def one(a):
    m, nb = a
    path, _, _, _ = make_plan(m, nb)
    env = dict(os.environ, EP_PLAN=path, EP_TRACE="1")
    r = subprocess.run(["uv", "run", "fcode", "run", "exec_plan", "do_nothing_bot", m,
                        "--replay", f"{SCR}/tp_{m}_{nb}.replay26"],
                       cwd=ROOT, env=env, capture_output=True, text=True)
    tr = {}
    for l in r.stderr.splitlines():
        g = re.match(r"T (\d+) (\d+) (\d+)$", l)
        if g:
            tr[int(g.group(1))] = (int(g.group(2)), int(g.group(3)))
    spend, out = 0, {}
    prev_scale = None
    for rd in sorted(tr):
        res, sc = tr[rd]
        if prev_scale is not None and sc > prev_scale:
            d = sc - prev_scale
            for delta in (20, 5, 1):          # decompose the jump greedily
                while d >= delta:
                    spend += BASE[delta] * prev_scale // 100
                    d -= delta
        prev_scale = sc
        passive = (rd // 4) * 10
        out[rd] = res - 500 - passive + spend
    return m, nb, {h: out.get(h, 0) for h in HZ}


if __name__ == "__main__":
    with ProcessPoolExecutor(max_workers=8) as ex:
        rows = list(ex.map(one, [(m, n) for m in CORES for n in NBS]))
    d = {(m, n): v for m, n, v in rows}
    print("Titanium DELIVERED by round H, summed over 15 maps (engine, plan-driven)")
    print(f"{'':<8}" + "".join(f"{f'H={h}':>12}" for h in HZ))
    tot = {n: {h: 0 for h in HZ} for n in NBS}
    for m in CORES:
        for n in NBS:
            for h in HZ:
                tot[n][h] += d[(m, n)][h]
    for n in NBS:
        print(f"NB={n:<5}" + "".join(f"{tot[n][h]:>12}" for h in HZ))
    print()
    for n in NBS[1:]:
        print(f"NB={n} vs NB=1:" + "".join(
            f"{100*tot[n][h]/tot[1][h]-100:>10.1f}%" for h in HZ))
