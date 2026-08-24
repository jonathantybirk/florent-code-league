"""Post-match replay review: build timelines, core damage, final board.

Usage:
    uv run python scratch/review.py replay.replay26 [--board ROUND] [--events]
"""
import argparse
import pathlib
import sys
from collections import defaultdict

EMPTY, WALL, ORE = 0, 1, 2
TYPE_MARKERS = {10: "builder", 11: "conveyor", 12: "splitter", 13: "barrier",
                15: "harvester", 21: "gunner", 22: "sentinel", 24: "launcher"}
GLYPH = {"builder": "b", "conveyor": "c", "splitter": "s", "barrier": "B",
         "harvester": "H", "gunner": "G", "sentinel": "S", "launcher": "L",
         "core": "@"}


def read_varint(b, i):
    v = s = 0
    while True:
        c = b[i]
        i += 1
        v |= (c & 0x7F) << s
        if not c & 0x80:
            return v, i
        s += 7


def fields(b, off=0, end=None):
    if end is None:
        end = len(b)
    out = []
    while off < end:
        key, off = read_varint(b, off)
        fn, wt = key >> 3, key & 7
        if wt == 0:
            v, off = read_varint(b, off)
        elif wt == 1:
            v, off = b[off:off + 8], off + 8
        elif wt == 2:
            ln, off = read_varint(b, off)
            v, off = b[off:off + ln], off + ln
        elif wt == 5:
            v, off = b[off:off + 4], off + 4
        else:
            raise ValueError(wt)
        out.append((fn, wt, v))
    return out


def unwrap(v):
    while True:
        fs = fields(v)
        if len(fs) == 1 and fs[0][0] == 1 and fs[0][1] == 2:
            v = fs[0][2]
            continue
        return fs


def zigzag_or_signed(v):
    # engine writes raw two's-complement varints for negative deltas
    return v - (1 << 64) if v >= (1 << 63) else v


def parse_pos(b):
    d = {fn: v for fn, wt, v in fields(b)}
    return d.get(1, 0), d.get(2, 0)


def load(path):
    data = pathlib.Path(path).read_bytes()
    top = fields(data)
    snapshot = None
    rounds = []
    winner = None
    condition = None
    for fn, wt, v in top:
        if fn == 1 and snapshot is None:
            snapshot = v
        elif fn == 3:
            rounds.append(v)
        elif fn == 4 and wt == 0:
            winner = v
        elif fn == 6:
            condition = v.decode(errors="replace")
    return snapshot, rounds, winner, condition


def parse_map(snapshot):
    w = h = None
    rows = []
    cores = []
    for fn, wt, v in fields(snapshot):
        if fn == 1 and wt == 0:
            w = v
        elif fn == 2 and wt == 0:
            h = v
        elif fn == 3 and wt == 2:
            inner = fields(v)
            rows.append(list(inner[0][2]))
        elif fn == 4 and wt == 2:
            d = {fn2: v2 for fn2, wt2, v2 in fields(v)}
            owner = d.get(1, 1)
            pos = parse_pos(d[3]) if 3 in d else (0, 0)
            cores.append((owner, pos))
    return w, h, rows, cores


def parse_rounds(rounds):
    """Yield per-round lists of decoded events."""
    for rnd, payload in enumerate(rounds):
        evs = []
        for fn, wt, v in fields(payload):
            if fn != 1 or wt != 2:
                continue
            body = unwrap(v)
            nums = {f for f, _, _ in body}
            if nums == {1} and len(body) == 1:
                continue
            evs.append((rnd, body))
        yield rnd, evs


def classify(body):
    d = {}
    for fn, wt, v in body:
        d.setdefault(fn, []).append((wt, v))
    return d


def analyse(path, board_round=None, show_events=False):
    snapshot, rounds, winner, condition = load(path)
    w, h, rows, cores = parse_map(snapshot)

    entities = {}          # id -> dict(type, team, pos, born, died, hp)
    damage = []            # (round, victim_id, amount)
    shots = []             # (round, src, dst)
    transfers = []         # (round, src, dst, stack_id)
    titanium = []          # (round, a_ti, b_ti)

    for rnd, payload in enumerate(rounds):
        for fn, wt, v in fields(payload):
            if wt != 2:
                continue
            d = classify(unwrap(v))
            marker = next((f for f in d if f > 5), None)
            if marker in TYPE_MARKERS and 1 in d and 3 in d:
                eid = d[1][0][1]
                entities[eid] = dict(type=TYPE_MARKERS[marker],
                                     team=1 if 2 in d else 0,
                                     pos=parse_pos(d[3][0][1]),
                                     born=rnd, died=None,
                                     hp=d[4][0][1], maxhp=d[5][0][1])
            elif set(d) == {2} and d[2][0][0] == 2:
                inner = classify(fields(d[2][0][1]))
                eid = inner[1][0][1]
                if eid in entities and 2 in inner:
                    entities[eid]["pos"] = parse_pos(inner[2][0][1])
            elif set(d) == {5}:
                inner = classify(fields(d[5][0][1]))
                if 1 in inner and 2 in inner:
                    delta = zigzag_or_signed(inner[2][0][1])
                    if delta < 0:
                        damage.append((rnd, inner[1][0][1], -delta))
            elif set(d) == {13}:
                inner = classify(fields(d[13][0][1]))
                eid = inner[1][0][1]
                if eid in entities:
                    entities[eid]["died"] = rnd
            elif set(d) == {12}:
                s = classify(fields(d[12][0][1]))
                if 1 in s and 2 in s:
                    shots.append((rnd, parse_pos(s[1][0][1]),
                                  parse_pos(s[2][0][1])))
            elif set(d) == {4}:
                for f2, w2, v2 in fields(d[4][0][1]):
                    if w2 != 2:
                        continue
                    s = classify(fields(v2))
                    if 1 in s and 2 in s:
                        transfers.append((rnd, parse_pos(s[1][0][1]),
                                          parse_pos(s[2][0][1])))
            elif set(d) == {6}:
                teams = []
                for f2, w2, v2 in fields(d[6][0][1]):
                    if w2 == 2:
                        t = classify(fields(v2))
                        teams.append(t[1][0][1] if 1 in t else 0)
                if len(teams) == 2:
                    titanium.append((rnd, teams[0], teams[1]))

    core_tiles = {}
    for owner, (cx, cy) in cores:
        for dx in (0, 1):
            for dy in (0, 1):
                core_tiles[(cx + dx, cy + dy)] = owner

    print(f"map {w}x{h}  cores {cores}  winner={winner} condition={condition} "
          f"rounds={len(rounds)}")

    # --- build timeline -------------------------------------------------
    per_team = defaultdict(lambda: defaultdict(list))
    for e in entities.values():
        per_team[e["team"]][e["type"]].append(e["born"])
    print("\nbuild counts:")
    for k in sorted({k for t in per_team.values() for k in t}):
        a, b = sorted(per_team[0].get(k, [])), sorted(per_team[1].get(k, []))
        print(f"  {k:10s} A={len(a):3d} first r{a[0] if a else '-':>4}   "
              f"B={len(b):3d} first r{b[0] if b else '-':>4}")

    # --- damage ---------------------------------------------------------
    # Cores are pre-placed, never spawned: infer their ids from damage events
    # that reference no known entity but whose owner is decided by elimination.
    core_dmg = defaultdict(list)
    unit_dmg = defaultdict(int)
    for rnd, eid, amount in damage:
        e = entities.get(eid)
        if e is None:
            core_dmg[eid].append((rnd, amount))
        else:
            unit_dmg[(e["team"], e["type"])] += amount
    print("\ncore damage (unknown ids = the two pre-placed Cores):")
    for eid, hits in sorted(core_dmg.items()):
        total = sum(a for _, a in hits)
        print(f"  id{eid}: {total} dmg, {len(hits)} hits, "
              f"r{hits[0][0]}..{hits[-1][0]}")
        buckets = defaultdict(int)
        for r, a in hits:
            buckets[r // 50 * 50] += a
        print("     " + " ".join(f"r{k}:{v}" for k, v in sorted(buckets.items())))
    if not core_dmg:
        print("  (none)")
    print("\ndamage taken by team/type:")
    for (team, kind), amount in sorted(unit_dmg.items(), key=lambda kv: -kv[1]):
        print(f"  team{'AB'[team]} {kind:10s} {amount}")

    # --- economy --------------------------------------------------------
    if titanium:
        print("\ntitanium (A / B):")
        step = max(1, len(titanium) // 12)
        print("  " + "  ".join(f"r{r}:{a}/{b}" for r, a, b in titanium[::step]))
    deliveries = defaultdict(int)
    for rnd, src, dst in transfers:
        owner = core_tiles.get(dst)
        if owner is not None:
            deliveries[owner] += 1
    print(f"\nstacks delivered to core: "
          + "  ".join(f"owner{o}:{n}" for o, n in sorted(deliveries.items())))

    # --- combat ---------------------------------------------------------
    if shots:
        by_shooter = defaultdict(int)
        for rnd, src, dst in shots:
            by_shooter[src] += 1
        print(f"\nturret shots: {len(shots)}, first r{shots[0][0]}; "
              f"busiest tiles {sorted(by_shooter.items(), key=lambda kv: -kv[1])[:6]}")

    # --- board ----------------------------------------------------------
    r = board_round if board_round is not None else len(rounds)
    grid = [[".#O"[c] for c in row] for row in rows]
    for owner, (cx, cy) in cores:
        for dx in (0, 1):
            for dy in (0, 1):
                if 0 <= cy + dy < h and 0 <= cx + dx < w:
                    grid[cy + dy][cx + dx] = "@" if owner == 1 else "%"
    for eid, e in entities.items():
        if e["born"] > r:
            continue
        x, y = e["pos"]
        if 0 <= y < h and 0 <= x < w:
            g = GLYPH.get(e["type"], "?")
            grid[y][x] = g.upper() if e["team"] == 0 else g.lower()
    print(f"\nboard after round {r} (A=UPPER/@, B=lower/%):")
    for y, row in enumerate(grid):
        print(f" {y:2d} " + "".join(row))
    print("    " + "".join(str(x % 10) for x in range(w)))

    if show_events:
        print("\nfirst 60 spawns:")
        for eid, e in sorted(entities.items(), key=lambda kv: kv[1]["born"])[:60]:
            print(f"  r{e['born']:4d} team{'AB'[e['team']]} {e['type']:10s} {e['pos']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("replay")
    ap.add_argument("--board", type=int, default=None)
    ap.add_argument("--events", action="store_true")
    a = ap.parse_args()
    analyse(a.replay, a.board, a.events)


main()
