"""Diagnose: how many harvesters actually end up connected and delivering?"""
import os, re, subprocess, sys

ROOT = "/Users/jonathantybirk/Documents/GitHub/florent-code-league"
SCR = "/private/tmp/claude-501/-Users-jonathantybirk-Documents-GitHub-florent-code-league/2c47d030-787d-4a82-a6f5-224c333e01c1/scratchpad"


def run(mapname, nb, debug=0):
    env = dict(os.environ, EL_BUILDERS=str(nb), EL_TRACE="1", EL_DEBUG=str(debug))
    p = subprocess.run(["uv", "run", "fcode", "run", "econ_lab", "do_nothing_bot",
                        mapname, "--replay", f"{SCR}/d.replay26"],
                       cwd=ROOT, env=env, capture_output=True, text=True)
    res, dbg = {}, []
    for l in p.stderr.splitlines():
        m = re.match(r"T (\d+) res=(\d+) scale=([\d.]+) units=(\d+)", l)
        if m:
            res[int(m.group(1))] = (int(m.group(2)), float(m.group(3)), int(m.group(4)))
        elif l.startswith("["):
            dbg.append(l)
    mined = re.search(r"Titanium\s+([\d,]+) \(([\d,]+) mined\)", p.stdout)
    return res, dbg, int(mined.group(2).replace(",", "")) if mined else None


def summarise(mapname, nb):
    res, dbg, mined = run(mapname, nb)
    lo, hi = 700, 990
    rate = (res[hi][0] - res[lo][0]) / (hi - lo)
    conn = (rate - 2.5) / 2.5
    # rate early, to see how fast it ramps
    r300 = (res[350][0] - res[250][0]) / 100
    print(f"{mapname:<10} NB={nb}  mined={mined:>6}  final_scale={res[990][1]:>6.0f}  "
          f"units={res[990][2]}  connected_harv~{conn:>4.1f}  "
          f"early(250-350)~{(r300-2.5)/2.5:>4.1f}")
    return dbg


if __name__ == "__main__":
    for mp in ["fjord", "quarry", "longship", "runestone", "vault"]:
        for nb in [1, 2, 3, 4, 5]:
            summarise(mp, nb)
        print()
