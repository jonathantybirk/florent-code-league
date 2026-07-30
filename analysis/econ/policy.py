"""Per-map optimal builder count vs what the Core can actually see on round 0.

Purpose: derive a decision rule that uses only round-0 Core-visible information.
"""
import sys
from collections import deque
sys.path.insert(0, 'analysis/econ')
from maplib import ORE, WALL, read_map
from mapstats import CORES, D4, D8, bfs, footprint
from simfog import simulate

HZ = [250, 400, 1000]
NBS = [1, 2, 3, 4]


def round0_view(name):
    """Exactly what the Core can determine on its first run(): terrain inside
    r^2<=36 of its footprint, plus map size."""
    w, h, rows = read_map(f"maps/{name}.map26")
    ca, _ = CORES[name]
    fa = footprint(ca)
    vis = {(x, y) for y in range(h) for x in range(w)
           if any((x - fx) ** 2 + (y - fy) ** 2 <= 36 for (fx, fy) in fa)}
    ore_vis = [p for p in vis if rows[p[1]][p[0]] == ORE]
    # conveyor length to each visible deposit, routed only through visible tiles
    adj4 = {p for p in ((x + dx, y + dy) for (x, y) in fa for dx, dy in D4)
            if p not in fa and p in vis and rows[p[1]][p[0]] != WALL}
    allore = {(x, y) for y in range(h) for x in range(w) if rows[y][x] == ORE}
    blocked = {p for p in vis if rows[p[1]][p[0]] == WALL} | fa | (allore - set())
    dist = {}
    q = deque()
    for s in adj4:
        dist[s] = 0
        q.append(s)
    while q:
        c = q.popleft()
        for dx, dy in D4:
            n = (c[0] + dx, c[1] + dy)
            if n in dist or n not in vis or n in blocked:
                continue
            dist[n] = dist[c] + 1
            q.append(n)
    lens = []
    for o in ore_vis:
        L = min((dist[n] for n in [(o[0] + dx, o[1] + dy) for dx, dy in D4] if n in dist),
                default=None)
        lens.append(L + 1 if L is not None else None)
    return {"w": w, "h": h, "area": w * h, "n_vis": len(ore_vis),
            "lens": sorted(x for x in lens if x is not None),
            "n_reach": sum(1 for x in lens if x is not None)}


def revenue_by(ev, hz):
    return sum(2.5 * (hz - c) for c, _ in ev if c < hz)


if __name__ == "__main__":
    rows_out = []
    for m in CORES:
        v = round0_view(m)
        rev = {}
        for n in NBS:
            _, _, _, ev = simulate(m, n)
            for hz in HZ:
                rev[(n, hz)] = revenue_by(ev, hz)
        rows_out.append((m, v, rev))

    print("Round-0 Core-visible signal vs simulated best builder count\n")
    print(f"{'map':<11}{'area':>6}{'vis':>5}{'reach':>6}  {'visible Ls':<14}"
          + "".join(f"{f'best@{h}':>10}" for h in HZ) + f"{'margin@400':>12}")
    for m, v, rev in rows_out:
        bests = []
        for hz in HZ:
            b = max(NBS, key=lambda n: rev[(n, hz)])
            bests.append(b)
        r400 = [rev[(n, 400)] for n in NBS]
        margin = (max(r400) - r400[0]) / max(r400[0], 1) * 100
        print(f"{m:<11}{v['area']:>6}{v['n_vis']:>5}{v['n_reach']:>6}  "
              f"{str(v['lens']):<14}" + "".join(f"{b:>10}" for b in bests)
              + f"{margin:>11.1f}%")

    # --- candidate rules, scored against always-N and the per-map oracle ---
    def rule_vis(v):
        n = v["n_reach"]
        return 1 if n <= 1 else (2 if n <= 3 else 3)

    def rule_area2(v):      # map size is knowable on round 0 and is the real signal
        return 2 if v["area"] <= 330 else 3

    def rule_area3(v):
        return 2 if v["area"] <= 330 else 4

    def rule_area_vis(v):
        if v["area"] <= 330:
            return 2
        return 3 if v["n_reach"] >= 3 else 4

    print()
    for hz in HZ:
        tot = {}
        for label, f in [("always 1", lambda v: 1), ("always 2", lambda v: 2),
                         ("always 3", lambda v: 3), ("always 4", lambda v: 4),
                         ("rule: visible-count", rule_vis),
                         ("rule: area<=330?2:3", rule_area2),
                         ("rule: area<=330?2:4", rule_area3),
                         ("rule: area+visible", rule_area_vis),
                         ("per-map oracle", None)]:
            s = 0
            for m, v, rev in rows_out:
                s += max(rev[(n, hz)] for n in NBS) if f is None else rev[(f(v), hz)]
            tot[label] = s
        base = tot["always 1"]
        print(f"H={hz}")
        for k, v in tot.items():
            print(f"    {k:<24}{v/base*100-100:+7.1f}%")
