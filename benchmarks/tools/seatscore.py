"""Per-opponent score split by seat, for one candidate in a benchmarks run."""
import json, glob, sys, collections

run, me = sys.argv[1], sys.argv[2]
h = collections.defaultdict(lambda: {"A": [0.0, 0], "B": [0.0, 0]})
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
    mine_is_a = a == me
    seat = "A" if mine_is_a else "B"
    opp = b if mine_is_a else a
    h[opp][seat][0] += sa if mine_is_a else 1 - sa
    h[opp][seat][1] += 1

tA = [0.0, 0]
tB = [0.0, 0]
print(f"{'opponent':22} {'seat A':>10} {'seat B':>10} {'total':>10}")
for o in sorted(h):
    sA, nA = h[o]["A"]
    sB, nB = h[o]["B"]
    tA[0] += sA; tA[1] += nA; tB[0] += sB; tB[1] += nB
    fa = f"{sA/nA:.3f}" if nA else "  -  "
    fb = f"{sB/nB:.3f}" if nB else "  -  "
    ft = (sA + sB) / (nA + nB)
    print(f"{o:22} {fa:>10} {fb:>10} {ft:>10.3f}")
if tA[1] and tB[1]:
    print(f"{'OVERALL':22} {tA[0]/tA[1]:>10.3f} {tB[0]/tB[1]:>10.3f} "
          f"{(tA[0]+tB[0])/(tA[1]+tB[1]):>10.3f}")
    print(f"seat gap (A - B): {tA[0]/tA[1] - tB[0]/tB[1]:+.3f}")
