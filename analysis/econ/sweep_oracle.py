"""Same builder sweep, but with fog removed (EL_ORACLE). Isolates construction
throughput from scouting."""
import os, re, subprocess, sys
from concurrent.futures import ProcessPoolExecutor
sys.path.insert(0, 'analysis/econ')
from maplib import ORE, read_map
from mapstats import CORES

ROOT = "/Users/jonathantybirk/Documents/GitHub/florent-code-league"
SCR = "/private/tmp/claude-501/-Users-jonathantybirk-Documents-GitHub-florent-code-league/2c47d030-787d-4a82-a6f5-224c333e01c1/scratchpad"
MAPS = list(CORES)
NBS = [1, 2, 3, 4, 6]


def ore_file(m):
    w, h, rows = read_map(f"{ROOT}/maps/{m}.map26")
    p = f"{SCR}/ore_{m}.txt"
    with open(p, "w") as f:
        for y in range(h):
            for x in range(w):
                if rows[y][x] == ORE:
                    f.write(f"{x} {y}\n")
    return p


def one(a):
    m, nb, oracle = a
    env = dict(os.environ, EL_BUILDERS=str(nb), EL_REUSE="0", EL_DEBUG="0")
    if oracle:
        env["EL_ORACLE"] = ore_file(m)
    r = subprocess.run(["uv", "run", "fcode", "run", "econ_lab", "do_nothing_bot", m,
                        "--replay", f"{SCR}/o_{m}_{nb}_{int(oracle)}.replay26"],
                       cwd=ROOT, env=env, capture_output=True, text=True)
    mm = re.search(r"Titanium\s+([\d,]+) \(([\d,]+) mined\)", r.stdout)
    return m, nb, oracle, int(mm.group(2).replace(",", "")) if mm else None


if __name__ == "__main__":
    jobs = [(m, nb, o) for m in MAPS for nb in NBS for o in (True, False)]
    with ProcessPoolExecutor(max_workers=8) as ex:
        rows = list(ex.map(one, jobs))
    d = {(m, nb, o): v for m, nb, o, v in rows}
    for oracle in (True, False):
        print(f"\n{'ORACLE (no fog)' if oracle else 'FOG (real conditions)'}")
        print(f"{'map':<11}" + "".join(f"{f'NB={n}':>9}" for n in NBS))
        tot = {n: 0 for n in NBS}
        for m in MAPS:
            vs = [d.get((m, n, oracle)) for n in NBS]
            for n, v in zip(NBS, vs):
                tot[n] += v or 0
            print(f"{m:<11}" + "".join(f"{v if v is not None else '-':>9}" for v in vs))
        print(f"{'TOTAL':<11}" + "".join(f"{tot[n]:>9}" for n in NBS))
        print(f"{'vs NB=1':<11}" + "".join(f"{100*tot[n]/tot[NBS[0]]-100:>8.1f}%" for n in NBS))
    print("\nfog cost (oracle - fog) / oracle:")
    for n in NBS:
        o = sum(d.get((m, n, True)) or 0 for m in MAPS)
        f = sum(d.get((m, n, False)) or 0 for m in MAPS)
        print(f"  NB={n}: oracle={o} fog={f}  fog loses {100*(o-f)/o:.1f}%")
