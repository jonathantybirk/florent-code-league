"""Re-check every constant this bot rests on against a held-out replay set.

Usage: validate.py <matches.json> <replay-dir>
"""
import collections, glob, json, os, statistics, sys
from collections import deque

import decode

HERE = os.path.dirname(os.path.abspath(__file__))
matches_path, replay_dir = sys.argv[1], sys.argv[2]
MATCHES = json.load(open(matches_path))["matches"]
SIDE = {}
for m in MATCHES:
    if m["teamAName"] == "Pantheon":
        SIDE[m["id"]] = "TEAM_A"
    elif m["teamBName"] == "Pantheon":
        SIDE[m["id"]] = "TEAM_B"


def bfs(grid, w, h, src):
    D = {src: 0}
    q = deque([src])
    while q:
        x, y = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (x + dx, y + dy)
            if (0 <= n[0] < w and 0 <= n[1] < h and n not in D
                    and grid[n[1]][n[0]] != "ENV_WALL"):
                D[n] = D[(x, y)] + 1
                q.append(n)
    return D


opening = collections.Counter()
throw_rounds = collections.Counter()
throw_count = collections.Counter()
range_sq = collections.Counter()
launcher_life = collections.Counter()
launchers_per_game = collections.Counter()
pad_offset = collections.Counter()
bfs_opt = [0, 0]
tie_far = collections.Counter()
games = 0

for path in sorted(glob.glob(f"{replay_dir}/*.replay26")):
    mid = os.path.basename(path).split("_game_")[0]
    side = SIDE.get(mid)
    if side is None:
        continue
    r = decode.decode(path)
    m = r["map"]
    grid = m["grid"]
    if not grid or len(grid) != m["height"]:
        continue
    cores = {c.get("team", "TEAM_A"): c for c in m["cores"]}
    other = "TEAM_B" if side == "TEAM_A" else "TEAM_A"
    if side not in cores or other not in cores:
        continue
    games += 1
    my_core, enemy_core = cores[side]["pos"], cores[other]["pos"]
    D = bfs(grid, m["width"], m["height"], enemy_core)

    posn, owner, builds, deaths = {}, {}, [], {}
    launchers, throws, first_builder = [], [], None
    for rnd, ups in enumerate(r["turns"]):
        for u in ups:
            if "placeEntity" in u:
                e = u["placeEntity"]["entity"]
                t = e.get("team", "TEAM_A")
                owner[e["id"]] = t
                p = decode.pos(e.get("position", {}))
                posn[e["id"]] = p
                k = decode.entity_kind(e)
                if t == side:
                    builds.append((rnd, k, p))
                    if k == "launcher":
                        launchers.append((e["id"], rnd, p))
                    if k == "builder" and first_builder is None and rnd == 0:
                        first_builder = p
            elif "moveBuilderBot" in u:
                i = u["moveBuilderBot"]["id"]
                to = decode.pos(u["moveBuilderBot"].get("to", {}))
                frm = posn.get(i)
                posn[i] = to
                if owner.get(i) == side and frm is not None:
                    if max(abs(to[0] - frm[0]), abs(to[1] - frm[1])) > 1:
                        throws.append((rnd, frm, to))
            elif "removeEntity" in u:
                deaths.setdefault(u["removeEntity"]["id"], rnd)

    opening[tuple((rr, kk) for rr, kk, _ in builds if rr < 4)] += 1
    throw_count[len(throws)] += 1
    launchers_per_game[len(launchers)] += 1
    for rnd, frm, to in throws[:6]:
        throw_rounds[rnd] += 1
    for lid, lr, lp in launchers:
        d = deaths.get(lid)
        launcher_life[(d - lr) if d is not None else "survives"] += 1
    if launchers and first_builder:
        lp = launchers[0][2]
        pad_offset[(lp[0] - first_builder[0], lp[1] - first_builder[1])] += 1
    # throw targeting: BFS-optimal + far tie-break
    if launchers:
        lp = launchers[0][2]
        for rnd, frm, to in throws[:2]:
            legal = [(x, y) for y in range(m["height"]) for x in range(m["width"])
                     if (x - lp[0]) ** 2 + (y - lp[1]) ** 2 <= 26
                     and grid[y][x] != "ENV_WALL" and (x, y) in D]
            if not legal or to not in D:
                continue
            best = min(D[q] for q in legal)
            bfs_opt[1] += 1
            if D[to] == best:
                bfs_opt[0] += 1
                ties = [q for q in legal if D[q] == best]
                if len(ties) > 1:
                    far = max((q[0]-lp[0])**2 + (q[1]-lp[1])**2 for q in ties)
                    tie_far["far" if (to[0]-lp[0])**2 + (to[1]-lp[1])**2 == far
                            else "other"] += 1
    for rnd, frm, to in throws[:4]:
        if launchers:
            lp = launchers[0][2]
            range_sq[(to[0]-lp[0])**2 + (to[1]-lp[1])**2] += 1

print(f"held-out games: {games}\n")
top, n = opening.most_common(1)[0]
print(f"opening r0-3 : {n}/{games} = {100*n/games:.0f}%  {[f'{a}:{b}' for a,b in top]}")
print(f"throws/game  : {sorted(throw_count.items())}")
print(f"throw rounds : {sorted(throw_rounds.items())[:6]}")
mx = max(range_sq) if range_sq else 0
atmax = sum(v for k, v in range_sq.items() if k >= 25)
print(f"throw range  : max dist_sq {mx}, at max (>=25) {100*atmax/max(1,sum(range_sq.values())):.0f}%")
print(f"launchers/game: {sorted(launchers_per_game.items())}")
print(f"launcher life : {launcher_life.most_common(4)}")
print(f"pad offset from r0 Builder: {pad_offset.most_common(6)}")
if bfs_opt[1]:
    print(f"raider throw BFS-optimal: {bfs_opt[0]}/{bfs_opt[1]} = {100*bfs_opt[0]/bfs_opt[1]:.0f}%")
print(f"tie-break farthest      : {tie_far.most_common()}")
