"""Aggregate every finished audit run for a set of bots into one comparison table."""
import glob
import json
import pathlib
import sys
from collections import Counter

HERE = pathlib.Path(__file__).resolve().parent
tags = sys.argv[1:] or ["T2BASE", "T2A", "T2C", "T2G"]


def rows_for(tag):
    out = {}
    for d in glob.glob(str(HERE / ("_out_%s_*" % tag))):
        parts = pathlib.Path(d).name.split("_")
        opp, pool = parts[3], parts[4]
        rs = []
        for f in glob.glob(d + "/*.jsonl"):
            for line in open(f):
                if line.strip():
                    rs.append(json.loads(line))
        if rs:
            out[(opp, pool)] = rs
    return out


data = {t: rows_for(t) for t in tags}
cells = sorted(set().union(*[set(v) for v in data.values()]))
print("%-12s%-8s" % ("opponent", "pool") + "".join("%-26s" % t for t in tags))
tot = {t: Counter() for t in tags}
for cell in cells:
    line = "%-12s%-8s" % cell
    for t in tags:
        rs = data[t].get(cell)
        if not rs:
            line += "%-26s" % "-"
            continue
        w = sum(1 for r in rs if r['won'])
        ng = sum(1 for r in rs if r['guns'] == 0)
        rich = sum(1 for r in rs if r['guns'] == 0 and r['peak_ti'] >= 1000)
        guns = sum(r['guns'] for r in rs)
        tot[t][cell[1] + '_w'] += w
        tot[t][cell[1] + '_n'] += len(rs)
        tot[t][cell[1] + '_ng'] += ng
        tot[t][cell[1] + '_rich'] += rich
        tot[t][cell[1] + '_guns'] += guns
        tot[t][cell[1] + '_idle'] += sum(r['idle'] for r in rs)
        tot[t][cell[1] + '_fired'] += sum(r['fired'] for r in rs)
        tot[t][cell[1] + '_kills'] += sum(1 for r in rs
                                          if r['won'] and r['cond'] == 'core_destroyed')
        line += "%-26s" % ("%d-%d ng%d rich%d g%d" % (w, len(rs) - w, ng, rich, guns))
    print(line)
print()
for pool in ("known", "unseen"):
    for t in tags:
        c = tot[t]
        if not c[pool + '_n']:
            continue
        print("%-8s %-8s %d-%d  kills %-4d zero-gun %-3d rich-blocked %-3d gunners %-4d "
              "fired %-4d idle %-3d"
              % (pool, t, c[pool + '_w'], c[pool + '_n'] - c[pool + '_w'], c[pool + '_kills'],
                 c[pool + '_ng'], c[pool + '_rich'], c[pool + '_guns'], c[pool + '_fired'],
                 c[pool + '_idle']))
    print()
