"""Sweep ore distance; extract build/deliver timings from probe stderr."""
import json
import os
import re
import subprocess

ROOT = "/Users/jonathantybirk/Documents/GitHub/florent-code-league"
SCRATCH = "/private/tmp/claude-501/-Users-jonathantybirk-Documents-GitHub-florent-code-league/2c47d030-787d-4a82-a6f5-224c333e01c1/scratchpad"


def run(cfg, mapname):
    p = f"{SCRATCH}/cfg.json"
    json.dump(cfg, open(p, "w"))
    env = dict(os.environ, FCODE_ECON_CFG=p)
    out = subprocess.run(
        ["uv", "run", "fcode", "run", "probe_econ", "do_nothing_bot", mapname,
         "--replay", f"{SCRATCH}/s.replay26"],
        cwd=ROOT, env=env, capture_output=True, text=True).stderr
    res, events = {}, []
    for line in out.splitlines():
        m = re.match(r"T (\d+) res=(\d+) scale=([\d.]+)", line)
        if m:
            res[int(m.group(1))] = (int(m.group(2)), float(m.group(3)))
        elif line.startswith(("HARV", "SPAWN", "LINE_DONE", "BOT")):
            events.append(line)
    return res, events


def deliveries(res):
    """Rounds where the balance rose by more than the round's passive tick."""
    out = []
    for r in sorted(res)[1:]:
        if r - 1 not in res:
            continue
        passive = 10 if r % 4 == 0 else 0
        gain = res[r][0] - res[r - 1][0]
        scale_spend = 0  # spending is separate; we only flag surplus gains
        if gain - passive >= 10:
            out.append(r)
    return out


if __name__ == "__main__":
    print(f"{'d':>3} {'harv_r':>7} {'convs':>6} {'first_del':>10} {'cadence':>8} {'setup_cost':>10}")
    for d in range(3, 16):
        tx = 2 + d
        res, ev = run({"spawns": [0], "targets": [[tx, 2]], "core": [2, 2]}, f"_line{d}")
        harv_r = next((int(re.search(r"r=(\d+)", e).group(1)) for e in ev if e.startswith("HARV")), None)
        dels = deliveries(res)
        cad = (dels[5] - dels[1]) / 4 if len(dels) > 5 else None
        # conveyors = scale rise after harvester, in 1% units
        end_scale = res[max(res)][1]
        convs = round(end_scale - 125.0)
        print(f"{d:>3} {harv_r:>7} {convs:>6} {dels[0] if dels else '-':>10} {cad if cad else '-':>8} "
              f"{500 - res[max(r for r in res if r < (dels[0] if dels else 60))][0]:>10}")
