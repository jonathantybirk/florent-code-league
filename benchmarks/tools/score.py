"""Per-opponent score for one candidate out of a benchmarks run directory."""
import json, glob, sys, collections

run, me = sys.argv[1], sys.argv[2]
h = collections.defaultdict(lambda: [0.0, 0])
for f in glob.glob(f"{run}/results/*.json"):
    d = json.load(open(f))
    if d.get("status") != "ok":
        continue
    a = d["a"].split("/stage/")[1].split("/")[0]
    b = d["b"].split("/stage/")[1].split("/")[0]
    if me not in (a, b):
        continue
    w = str(d["engine"]["winner"]).lower()
    sa = 1.0 if w == "a" else 0.5 if d["metrics"]["win_condition"] == "coinflip" else 0.0
    opp = b if a == me else a
    s = sa if a == me else 1 - sa
    h[opp][0] += s
    h[opp][1] += 1

tot = [0.0, 0]
for o, (s, n) in sorted(h.items(), key=lambda kv: kv[1][0] / kv[1][1]):
    print(f"{s/n:6.3f}  {s:>5}/{n:<4} vs {o}")
    tot[0] += s
    tot[1] += n
if tot[1]:
    worst = min(s / n for s, n in h.values())
    print(f"{tot[0]/tot[1]:6.3f}  MEAN  n={tot[1]}   worst={worst:.3f}")
