"""The standing benchmark set: pacing, launch accuracy, build exposure.

Usage: bench.py <stderr-log>
"""
import re, sys, pathlib, collections

p = pathlib.Path(sys.argv[1])
lines = p.read_text(errors="ignore").splitlines()

# ---- pacing -----------------------------------------------------------------
match = 0
last_r = 0
tracks = collections.defaultdict(list)
for l in lines:
    if not l.startswith("DIAG_POS"):
        continue
    d = dict(re.findall(r"(\w+)=([\d,]+)", l))
    r, i = int(d["r"]), int(d["id"])
    x, y = map(int, d["at"].split(","))
    if r < last_r:
        match += 1
    last_r = r
    tracks[(match, i)].append((r, (x, y)))

WIN = 60
tot = paced = idle = 0
for tr in tracks.values():
    if len(tr) < WIN:
        continue
    tail = tr[-WIN:]
    distinct = len(set(pos for _, pos in tail))
    moves = sum(1 for a, b in zip(tail, tail[1:]) if a[1] != b[1])
    tot += 1
    if distinct <= 3 and moves >= WIN * 0.3:
        paced += 1
    if moves == 0:
        idle += 1
print("=== BUILDER PACING (last 60 rounds of each Builder's life) ===")
print(f"  builders sampled : {tot}")
print(f"  pacing (<=3 tiles, moving >=30%): {paced} ({100*paced/max(tot,1):.1f}%)")
print(f"  never moved                     : {idle} ({100*idle/max(tot,1):.1f}%)")

# ---- launch accuracy --------------------------------------------------------
pos = {}
match = 0
last_r = 0
for l in lines:
    if l.startswith("DIAG_POS"):
        d = dict(re.findall(r"(\w+)=([\d,]+)", l))
        r, i = int(d["r"]), int(d["id"])
        x, y = map(int, d["at"].split(","))
        if r < last_r:
            match += 1
        last_r = r
        pos[(match, r, i)] = (x, y)
serves = []
match = 0
last_r = 0
for l in lines:
    if l.startswith("DIAG_POS"):
        r = int(re.search(r"r=(\d+)", l).group(1))
        if r < last_r:
            match += 1
        last_r = r
    elif l.startswith("LSERV"):
        r = int(re.search(r"r=(\d+)", l).group(1))
        pid = int(re.search(r"passenger=(\d+)", l).group(1))
        m = re.search(r"to=\((\d+),\s*(\d+)\)", l)
        if m:
            serves.append((match, r, pid, (int(m.group(1)), int(m.group(2)))))
errs = []
for m, r, pid, to in serves:
    nxt = pos.get((m, r + 1, pid)) or pos.get((m, r, pid))
    if nxt is None:
        continue
    errs.append(max(abs(nxt[0] - to[0]), abs(nxt[1] - to[1])))
served = len([l for l in lines if l.startswith("LSERV")])
refused = len([l for l in lines if l.startswith("LREJ")])
print("=== LAUNCHER ===")
print(f"  served {served}  refused {refused}  "
      f"(refusal {100*refused/max(served+refused,1):.1f}%, by design: firing-line check)")
if errs:
    big = sum(1 for e in errs if e >= 2)
    print(f"  landed >=2 tiles from request: {big}/{len(errs)} "
          f"({100*big/len(errs):.1f}%), max {max(errs)}")

# ---- build exposure ---------------------------------------------------------
builds = [l for l in lines if l.startswith("BUILDX")]
exp = sum(1 for l in builds if any(f"{k}=1" in l for k in ("knew", "visible", "remembered")))
by = collections.Counter()
for l in builds:
    if any(f"{k}=1" in l for k in ("knew", "visible", "remembered")):
        m = re.search(r"action=(\S+)", l)
        by[m.group(1) if m else "?"] += 1
print("=== BUILD EXPOSURE ===")
print(f"  placed in an enemy turret's line: {exp}/{len(builds)} "
      f"({100*exp/max(len(builds),1):.1f}%)")
print(f"  worst: {by.most_common(3)}")
