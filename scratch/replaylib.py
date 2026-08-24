"""Decoder for .replay26 match logs, shared by the reviewer and the arena."""

import pathlib
from collections import defaultdict

TYPE_MARKERS = {10: "builder", 11: "conveyor", 12: "splitter", 13: "barrier",
                15: "harvester", 21: "gunner", 22: "sentinel", 24: "launcher"}


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


def signed(v):
    return v - (1 << 64) if v >= (1 << 63) else v


def parse_pos(b):
    d = {fn: v for fn, wt, v in fields(b)}
    return d.get(1, 0), d.get(2, 0)


def classify(body):
    d = {}
    for fn, wt, v in body:
        d.setdefault(fn, []).append((wt, v))
    return d


def load(path):
    data = pathlib.Path(path).read_bytes()
    snapshot, rounds, winner, condition = None, [], None, None
    for fn, wt, v in fields(data):
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
    rows, cores = [], []
    for fn, wt, v in fields(snapshot):
        if fn == 1 and wt == 0:
            w = v
        elif fn == 2 and wt == 0:
            h = v
        elif fn == 3 and wt == 2:
            rows.append(list(fields(v)[0][2]))
        elif fn == 4 and wt == 2:
            d = {f: val for f, _, val in fields(v)}
            cores.append((d.get(1, 1), parse_pos(d[3]) if 3 in d else (0, 0)))
    return w, h, rows, cores


def decode(path):
    """Return every fact the reviewer and the arena need from one replay."""
    snapshot, rounds, winner, condition = load(path)
    w, h, rows, cores = parse_map(snapshot)

    entities, damage, shots, transfers, titanium = {}, [], [], [], []
    for rnd, payload in enumerate(rounds):
        for fn, wt, v in fields(payload):
            if wt != 2:
                continue
            d = classify(unwrap(v))
            marker = next((f for f in d if f > 5), None)
            if marker in TYPE_MARKERS and 1 in d and 3 in d:
                entities[d[1][0][1]] = dict(
                    type=TYPE_MARKERS[marker], team=1 if 2 in d else 0,
                    pos=parse_pos(d[3][0][1]), born=rnd, died=None,
                    hp=d[4][0][1], maxhp=d[5][0][1])
            elif set(d) == {2} and d[2][0][0] == 2:
                inner = classify(fields(d[2][0][1]))
                eid = inner[1][0][1]
                if eid in entities and 2 in inner:
                    entities[eid]["pos"] = parse_pos(inner[2][0][1])
            elif set(d) == {5}:
                inner = classify(fields(d[5][0][1]))
                if 1 in inner and 2 in inner:
                    delta = signed(inner[2][0][1])
                    if delta < 0:
                        damage.append((rnd, inner[1][0][1], -delta))
            elif set(d) == {13}:
                eid = classify(fields(d[13][0][1]))[1][0][1]
                if eid in entities:
                    entities[eid]["died"] = rnd
            elif set(d) == {12}:
                s = classify(fields(d[12][0][1]))
                if 1 in s and 2 in s:
                    shots.append((rnd, parse_pos(s[1][0][1]),
                                  parse_pos(s[2][0][1])))
            elif set(d) == {4}:
                for _, w2, v2 in fields(d[4][0][1]):
                    if w2 != 2:
                        continue
                    s = classify(fields(v2))
                    if 1 in s and 2 in s:
                        transfers.append((rnd, parse_pos(s[1][0][1]),
                                          parse_pos(s[2][0][1])))
            elif set(d) == {6}:
                vals = [classify(fields(v2))[1][0][1]
                        for _, w2, v2 in fields(d[6][0][1]) if w2 == 2]
                if len(vals) == 2:
                    titanium.append((rnd, vals[0], vals[1]))

    return dict(w=w, h=h, rows=rows, cores=cores, winner=winner,
                condition=condition, rounds=len(rounds), entities=entities,
                damage=damage, shots=shots, transfers=transfers,
                titanium=titanium)


def summarize(path):
    """One-line-per-team facts: what each side built, and who hurt whom."""
    m = decode(path)
    core_tiles = {}
    for owner, (cx, cy) in m["cores"]:
        for dx in (0, 1):
            for dy in (0, 1):
                core_tiles[(cx + dx, cy + dy)] = owner - 1

    built = defaultdict(lambda: defaultdict(int))
    first = {}
    for e in m["entities"].values():
        built[e["team"]][e["type"]] += 1
        key = (e["team"], e["type"])
        if key not in first or e["born"] < first[key]:
            first[key] = e["born"]

    # Core ids never appear as spawns; damage to an unknown id is Core damage.
    core_damage = defaultdict(int)
    core_first = {}
    for rnd, eid, amount in m["damage"]:
        if eid in m["entities"]:
            continue
        core_damage[eid] += amount
        core_first.setdefault(eid, rnd)
    # Whoever took ~500 and lost is the destroyed Core; order ids for stability.
    ordered = sorted(core_damage.items(), key=lambda kv: -kv[1])

    # Engine 2.3.3 feeds turrets from a global pool, so "stacks delivered into
    # a turret" is always zero now and tells us nothing. Shots fired is the
    # combat metric that survived the change.
    turret_tiles = {}
    for e in m["entities"].values():
        if e["type"] in ("gunner", "sentinel"):
            turret_tiles[e["pos"]] = e["team"]
    fed = defaultdict(int)
    for _, src, dst in m["transfers"]:
        team = turret_tiles.get(dst)
        if team is not None:
            fed[team] += 1

    return dict(
        fed=fed, turrets=len(turret_tiles),
        rounds=m["rounds"], condition=m["condition"], winner=m["winner"],
        built=built, first=first, core_damage=ordered, core_first=core_first,
        shots=len(m["shots"]),
        first_shot=m["shots"][0][0] if m["shots"] else None,
        titanium=m["titanium"][-1] if m["titanium"] else None,
    )
