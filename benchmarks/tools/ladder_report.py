"""Per-opponent ladder record for one bot out of a tournament run.

Reports both readings of "80% against all opponents":
  (a) fraction of distinct opponents beaten (>50% head-to-head)
  (b) overall win rate across all matches
"""
import csv, sys, collections, pathlib

run = pathlib.Path(sys.argv[1])
me = sys.argv[2]

h = collections.defaultdict(lambda: [0.0, 0])
src = run / "matches-distinct.csv"
if not src.exists():
    src = run / "matches.csv"
with open(src) as fh:
    for r in csv.DictReader(fh):
        if r["status"] != "ok":
            continue
        a, b, w = r["bot_a"], r["bot_b"], r["winner"]
        if me not in (a, b):
            continue
        sa = 1.0 if w == "a" else (0.0 if w == "b" else 0.5)
        opp = b if a == me else a
        h[opp][0] += sa if a == me else 1 - sa
        h[opp][1] += 1

if not h:
    print(f"no matches for {me} in {src}")
    sys.exit(1)

rows = sorted(((s / n, n, o) for o, (s, n) in h.items()))
beaten = sum(1 for f, _, _ in rows if f > 0.5)
drawn = sum(1 for f, _, _ in rows if f == 0.5)
total_s = sum(s for s, _ in h.values())
total_n = sum(n for _, n in h.values())

print(f"bot            : {me}")
print(f"opponents      : {len(rows)}")
print(f"(a) beaten     : {beaten}/{len(rows)} = {beaten/len(rows):.3f}   (drawn {drawn})")
print(f"(b) win rate   : {total_s/total_n:.4f}  over {total_n} matches")
print()
print("losses and draws:")
for f, n, o in rows:
    if f <= 0.5:
        print(f"  {f:5.3f} n={n:<4} {o}")
