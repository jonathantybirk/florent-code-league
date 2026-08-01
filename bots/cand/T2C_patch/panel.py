"""Run the mechanism audit over a whole panel, both map pools, and print one table.

usage: python panel.py <botdir> [jobs]
"""
import glob
import json
import pathlib
import subprocess
import sys
from collections import Counter

HERE = pathlib.Path(__file__).resolve().parent
REPO = pathlib.Path(r"c:\Users\edlun\Desktop\lucky shots\Hackathons\florent-code-league")
PANEL = ["vanguard", "undertow", "jonbot", "mistral", "tempest", "luc1", "lockin"]
ZOO = {"starter_fixed": "bots/zoo/starter_fixed"}


def load(tag):
    rows = []
    for f in glob.glob(str(HERE / tag / "*.jsonl")):
        for line in open(f):
            if line.strip():
                rows.append(json.loads(line))
    return rows


def main():
    bot = sys.argv[1]
    jobs = sys.argv[2] if len(sys.argv) > 2 else "7"
    name = pathlib.Path(bot).name
    opps = [("bots/rivals/" + o, o) for o in PANEL] + [(v, k) for k, v in ZOO.items()]
    print("=== PANEL %s ===" % bot)
    print("%-16s%-22s%-22s" % ("opponent", "known (42)", "UNSEEN (24)"))
    tot = Counter()
    for path, o in opps:
        line = ["%-16s" % o]
        for pool, n in (("known", "0"), ("unseen", "12")):
            subprocess.run([sys.executable, str(HERE / "audit.py"), bot, path, pool, n, jobs],
                           cwd=str(REPO), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            rows = load("_out_%s_%s_%s" % (name, o, pool))
            w = sum(1 for r in rows if r['won'])
            k = sum(1 for r in rows if r['won'] and r['cond'] == 'core_destroyed')
            ng = sum(1 for r in rows if r['guns'] == 0)
            guns = sum(r['guns'] for r in rows)
            fired = sum(r['fired'] for r in rows)
            idle = sum(r['idle'] for r in rows)
            on = sum(r['on_core'] for r in rows)
            firsts = sorted(r['first_gun'] for r in rows if r['first_gun'] is not None)
            tot[pool + '_w'] += w
            tot[pool + '_g'] += len(rows)
            tot[pool + '_k'] += k
            tot[pool + '_ng'] += ng
            tot[pool + '_guns'] += guns
            tot[pool + '_fired'] += fired
            tot[pool + '_idle'] += idle
            tot[pool + '_on'] += on
            tot[pool + '_firsts'] = tot.get(pool + '_firsts', 0)
            line.append("%-22s" % ("%d-%d k%d ng%d/%d g%d" %
                                   (w, len(rows) - w, k, ng, len(rows), guns)))
        print("".join(line))
    for pool in ("known", "unseen"):
        g = max(1, tot[pool + '_g'])
        print("\nTOTAL %-7s %d-%d   kills %d   zero-gun games %d/%d (%.0f%%)   gunners %d "
              "(fired %d, idle %d)   shots on core %d"
              % (pool, tot[pool + '_w'], tot[pool + '_g'] - tot[pool + '_w'], tot[pool + '_k'],
                 tot[pool + '_ng'], tot[pool + '_g'], 100.0 * tot[pool + '_ng'] / g,
                 tot[pool + '_guns'], tot[pool + '_fired'], tot[pool + '_idle'],
                 tot[pool + '_on']))


if __name__ == "__main__":
    main()
