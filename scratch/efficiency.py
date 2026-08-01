"""Where a bot wasted its match.

Win/loss says a bot lost; this says what it was doing instead of winning.
Everything is read out of the replay, so it works on opponents too.

    uv run python scratch/efficiency.py <replay> [--team A|B]

Metrics, per team:

  idle builders     rounds a Builder neither moved nor produced a building.
                    A Builder can legitimately be healing or attacking, which
                    the replay does not record per-unit, so treat a *high*
                    number as a smell rather than proof.
  stalled belts     Conveyors that received a stack and never passed one on.
                    A belt that accepts and never emits is a dead end.
  idle harvesters   Harvesters that never once emitted a stack. Their output
                    is being dropped on the floor.
  delivery          stacks reaching the Core, and the longest drought between
                    two deliveries -- the clearest sign of an economy that
                    stopped.
  collapse          the round after which the team never built or delivered
                    anything again. This is the "gave up" detector.
"""

import argparse
import pathlib
import sys
from collections import defaultdict

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import replaylib  # noqa: E402


def walk(path):
    """Replay the event stream, keeping per-round facts we can attribute."""
    snapshot, rounds, winner, condition = replaylib.load(path)
    w, h, rows, cores = replaylib.parse_map(snapshot)
    entities = {}
    moved = defaultdict(set)        # round -> {entity id}
    born = defaultdict(list)        # round -> [(team, kind, pos)]
    sent = defaultdict(int)         # tile -> stacks emitted
    got = defaultdict(int)          # tile -> stacks received
    delivered = defaultdict(list)   # team -> [round]
    titanium = []

    core_tiles = {}
    for owner, (cx, cy) in cores:
        for dx in (0, 1):
            for dy in (0, 1):
                core_tiles[(cx + dx, cy + dy)] = owner - 1

    for rnd, payload in enumerate(rounds):
        for fn, wt, v in replaylib.fields(payload):
            if wt != 2:
                continue
            d = replaylib.classify(replaylib.unwrap(v))
            marker = next((f for f in d if f > 5), None)
            if marker in replaylib.TYPE_MARKERS and 1 in d and 3 in d:
                team = 1 if 2 in d else 0
                kind = replaylib.TYPE_MARKERS[marker]
                pos = replaylib.parse_pos(d[3][0][1])
                entities[d[1][0][1]] = dict(type=kind, team=team, pos=pos,
                                            born=rnd, died=None)
                born[rnd].append((team, kind, pos))
            elif set(d) == {2} and d[2][0][0] == 2:
                inner = replaylib.classify(replaylib.fields(d[2][0][1]))
                eid = inner[1][0][1]
                if eid in entities and 2 in inner:
                    entities[eid]["pos"] = replaylib.parse_pos(inner[2][0][1])
                    moved[rnd].add(eid)
            elif set(d) == {13}:
                eid = replaylib.classify(replaylib.fields(d[13][0][1]))[1][0][1]
                if eid in entities:
                    entities[eid]["died"] = rnd
            elif set(d) == {4}:
                for _, w2, v2 in replaylib.fields(d[4][0][1]):
                    if w2 != 2:
                        continue
                    s = replaylib.classify(replaylib.fields(v2))
                    if 1 in s and 2 in s:
                        src = replaylib.parse_pos(s[1][0][1])
                        dst = replaylib.parse_pos(s[2][0][1])
                        sent[src] += 1
                        got[dst] += 1
                        owner = core_tiles.get(dst)
                        if owner is not None:
                            delivered[owner].append(rnd)
            elif set(d) == {6}:
                vals = [replaylib.classify(replaylib.fields(v2))[1][0][1]
                        for _, w2, v2 in replaylib.fields(d[6][0][1]) if w2 == 2]
                if len(vals) == 2:
                    titanium.append((rnd, vals[0], vals[1]))

    return dict(rounds=len(rounds), winner=winner, condition=condition,
                cores=cores, entities=entities, moved=moved, born=born,
                sent=sent, got=got, delivered=delivered, titanium=titanium)


def longest_gap(rounds_list, end):
    """Longest stretch with no event, including the tail."""
    if not rounds_list:
        return end, 0
    marks = sorted(set(rounds_list))
    gaps = [(marks[0], 0)]
    for a, b in zip(marks, marks[1:]):
        gaps.append((b - a, a))
    gaps.append((end - marks[-1], marks[-1]))
    return max(gaps)


def report(path, only=None):
    m = walk(path)
    end = m["rounds"]
    print(f"{pathlib.Path(path).name}  {m['condition']}  r{end}  "
          f"winner=team{'AB'[m['winner']] if m['winner'] is not None else '?'}")

    for team in (0, 1):
        if only is not None and team != only:
            continue
        label = "AB"[team]
        mine = {i: e for i, e in m["entities"].items() if e["team"] == team}

        # --- idle builders -------------------------------------------------
        builders = {i: e for i, e in mine.items() if e["type"] == "builder"}
        build_rounds = defaultdict(int)
        for rnd, made in m["born"].items():
            for t, _, _ in made:
                if t == team:
                    build_rounds[rnd] += 1
        alive = idle = 0
        for eid, e in builders.items():
            death = e["died"] if e["died"] is not None else end
            for rnd in range(e["born"] + 1, death):
                alive += 1
                if eid not in m["moved"][rnd] and not build_rounds.get(rnd):
                    idle += 1
        share = 100 * idle / alive if alive else 0

        # --- belts and harvesters ------------------------------------------
        belts = [e["pos"] for e in mine.values() if e["type"] == "conveyor"]
        stalled = [t for t in belts if m["got"][t] and not m["sent"][t]]
        starved = [t for t in belts if not m["got"][t]]
        harvs = [e["pos"] for e in mine.values() if e["type"] == "harvester"]
        dead_harv = [t for t in harvs if not m["sent"][t]]

        # --- delivery ------------------------------------------------------
        drops = m["delivered"][team]
        gap, gap_at = longest_gap(drops, end)
        rate = len(drops) / end * 100 if end else 0

        print(f"\n  team{label}: {len(builders)} builders, {len(harvs)} "
              f"harvesters, {len(belts)} conveyors")
        print(f"    idle builder-rounds  {idle}/{alive} ({share:.0f}%)")
        print(f"    stalled conveyors    {len(stalled)}/{len(belts)}"
              f"   never-fed {len(starved)}")
        print(f"    harvesters that never emitted  {len(dead_harv)}/{len(harvs)}"
              f"  {sorted(dead_harv)[:6]}")
        print(f"    delivered {len(drops)} stacks ({rate:.1f} per 100 rounds)"
              f"; longest drought {gap} rounds from r{gap_at}")

        # --- collapse ------------------------------------------------------
        last_build = max((r for r, made in m["born"].items()
                          if any(t == team for t, _, _ in made)), default=0)
        last_drop = drops[-1] if drops else 0
        quiet = max(last_build, last_drop)
        if end - quiet > 60:
            print(f"    ** COLLAPSE: nothing built or delivered after r{quiet} "
                  f"({end - quiet} rounds of silence)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("replay")
    ap.add_argument("--team", choices=["A", "B"], default=None)
    args = ap.parse_args()
    report(args.replay, {"A": 0, "B": 1}.get(args.team))


main()
