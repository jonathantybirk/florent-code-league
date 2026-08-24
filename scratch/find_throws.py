"""Find Launcher throws in a replay.

A throw is encoded exactly like a move -- a position-change event -- just with
a jump bigger than one tile, which no legal Builder move can be.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import replaylib  # noqa: E402


def throws(path):
    m = replaylib.decode(path)
    _, rounds, _, _ = replaylib.load(path)
    entities, out = {}, []
    for rnd, payload in enumerate(rounds):
        for fn, wt, v in replaylib.fields(payload):
            if wt != 2:
                continue
            d = replaylib.classify(replaylib.unwrap(v))
            marker = next((f for f in d if f > 5), None)
            if marker in replaylib.TYPE_MARKERS and 1 in d and 3 in d:
                entities[d[1][0][1]] = dict(
                    type=replaylib.TYPE_MARKERS[marker],
                    team=1 if 2 in d else 0,
                    pos=replaylib.parse_pos(d[3][0][1]))
            elif set(d) == {2} and d[2][0][0] == 2:
                inner = replaylib.classify(replaylib.fields(d[2][0][1]))
                eid = inner[1][0][1]
                if eid in entities and 2 in inner:
                    old = entities[eid]["pos"]
                    new = replaylib.parse_pos(inner[2][0][1])
                    jump = max(abs(new[0] - old[0]), abs(new[1] - old[1]))
                    if jump > 1:
                        out.append((rnd, eid, entities[eid]["team"],
                                    entities[eid]["type"], old, new, jump))
                    entities[eid]["pos"] = new
    return m, out


def main():
    m, found = throws(sys.argv[1])
    cores = {owner: pos for owner, pos in m["cores"]}
    print(f"map {m['w']}x{m['h']}  cores {m['cores']}  "
          f"{m['condition']} r{m['rounds']}")
    print(f"{len(found)} throw(s):")
    for rnd, eid, team, kind, old, new, jump in found:
        # Which Core did the victim get moved away from?
        home = cores.get(team + 1)
        away = ""
        if home:
            before = max(abs(old[0] - home[0]), abs(old[1] - home[1]))
            after = max(abs(new[0] - home[0]), abs(new[1] - home[1]))
            away = " TOWARD its own core" if after < before else " deeper out"
        print(f"  r{rnd:4d} team{'AB'[team]} {kind:8s} {old} -> {new} "
              f"({jump} tiles){away}")


main()
