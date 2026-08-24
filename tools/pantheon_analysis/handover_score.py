"""Per-action agreement after a scripted handover, across every map.

Whole-round agreement is too coarse: a round with four units scores zero if one
of them differs. This scores each of Pantheon's individual actions -- did we
take that same action in that same round -- and splits the result by what kind
of action it was, so it is visible whether the raid or the economy is what is
diverging.

Usage: handover_score.py <handover_round> [rounds_after]
"""
import glob, os, subprocess, sys, collections
import decode

REPO = "/home/Ucals/projects/florent-code-league-llm-rl"
S = ("/tmp/claude-1000/-home-Ucals-projects-florent-code-league-llm-rl/"
     "05d146e7-6b75-4d33-a413-788991e5ff01/scratchpad")
RIVAL = f"{S}/rivals/tempest_fast"
PUPPET = f"{REPO}/bots/luc/pantheon_puppet"


def local_maps():
    out = {}
    for f in sorted(glob.glob(f"{REPO}/maps/*.map26")):
        m = decode.parse(open(f, "rb").read(), "Map")
        g = tuple(tuple(r.get("tiles", [])) for r in m.get("rows", []))
        out[(m.get("width"), m.get("height"), g)] = os.path.basename(f).replace(".map26", "")
    return out


def acts(replay, team, lo, hi):
    per, posn, owner = collections.defaultdict(list), {}, {}
    for c in replay["map"]["cores"]:
        posn[c["id"]] = c["pos"]
        owner[c["id"]] = c.get("team", "TEAM_A")
    for rnd, ups in enumerate(replay["turns"]):
        if rnd >= hi:
            break
        for u in ups:
            if "placeEntity" in u:
                e = u["placeEntity"]["entity"]
                t = e.get("team", "TEAM_A")
                owner[e["id"]] = t
                p = decode.pos(e.get("position", {}))
                posn[e["id"]] = p
                if t == team and rnd >= lo:
                    per[rnd].append(("build", decode.entity_kind(e), p))
            elif "moveBuilderBot" in u:
                mv = u["moveBuilderBot"]
                i = mv["id"]
                to = decode.pos(mv.get("to", {}))
                frm = posn.get(i)
                posn[i] = to
                if owner.get(i) == team and frm is not None and rnd >= lo:
                    big = max(abs(to[0]-frm[0]), abs(to[1]-frm[1])) > 1
                    per[rnd].append((("throw" if big else "walk"), frm, to))
            elif "removeEntity" in u:
                i = u["removeEntity"]["id"]
                if owner.get(i) == team and rnd >= lo:
                    per[rnd].append(("remove", posn.get(i)))
    return per


def bucket(action):
    if action[0] == "build":
        kind = action[1]
        if kind in ("harvester", "conveyor", "splitter"):
            return "economy"
        if kind in ("gunner", "sentinel", "barrier"):
            return "turret"
        if kind == "launcher":
            return "pad"
        return "other"
    if action[0] == "throw":
        return "throw"
    if action[0] == "walk":
        return "walk"
    if action[0] == "remove":
        return "remove"
    return "other"


def main():
    handover = int(sys.argv[1])
    span = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    maps = local_maps()
    hit = collections.Counter()
    tot = collections.Counter()
    per_map = []
    # make_script.py always takes the first replay for a map, so a second game
    # on the same map would be scored against the wrong script. One per map.
    seen_maps = set()
    for rp in sorted(glob.glob(f"{S}/pantheon/vs_us_v20/*.replay26")):
        real = decode.decode(rp)
        m = real["map"]
        key = (m["width"], m["height"], tuple(tuple(x) for x in m["grid"]))
        name = maps.get(key)
        if not name or name in seen_maps:
            continue
        seen_maps.add(name)
        subprocess.run([sys.executable, f"{REPO}/tools/pantheon_analysis/make_script.py",
                        name], capture_output=True, text=True,
                       cwd=f"{REPO}/tools/pantheon_analysis")
        with open(f"{PUPPET}/handover.py", "w") as fh:
            fh.write(f"HANDOVER_ROUND = {handover}\n")
        pan = "TEAM_A" if real["winner"] == "TEAM_A" else "TEAM_B"
        out = f"{S}/hs_{name}.replay26"
        order = [PUPPET, RIVAL] if pan == "TEAM_A" else [RIVAL, PUPPET]
        subprocess.run(["fcode", "run", *order, f"{REPO}/maps/{name}.map26",
                        "--tle", "10", "--replay", out],
                       capture_output=True, text=True, cwd=REPO, timeout=600)
        if not os.path.exists(out):
            continue
        mine = decode.decode(out)
        hi = handover + span
        a = acts(real, pan, handover, hi)
        b = acts(mine, pan, handover, hi)
        mh = mt = 0
        for rnd in range(handover, hi):
            ours = list(b.get(rnd, []))
            for action in a.get(rnd, []):
                key2 = bucket(action)
                tot[key2] += 1
                mt += 1
                if action in ours:
                    ours.remove(action)
                    hit[key2] += 1
                    mh += 1
        per_map.append((name, mh, mt))
    print(f"handover r{handover}, scoring rounds {handover}-{handover+span-1}\n")
    print("%-11s %s" % ("map", "actions reproduced"))
    for name, mh, mt in per_map:
        print("  %-11s %3d/%-3d  %3.0f%%" % (name, mh, mt, 100*mh/max(1, mt)))
    print("\nby action type:")
    for key2 in sorted(tot, key=lambda k: -tot[k]):
        print("  %-8s %3d/%-3d  %3.0f%%" % (key2, hit[key2], tot[key2],
                                            100*hit[key2]/tot[key2]))
    print("\nTOTAL %d/%d = %.0f%%" % (sum(hit.values()), sum(tot.values()),
                                      100*sum(hit.values())/max(1, sum(tot.values()))))


main()
