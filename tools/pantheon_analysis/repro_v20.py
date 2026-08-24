"""1:1 action diff against fresh Pantheon v20 vs tempest_fast games.

Reruns each real game locally with the replica in Pantheon's seat and compares
the seat's actions round by round. Usage: repro_v20.py [rounds]
"""
import glob, json, os, subprocess, sys, statistics
import decode

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = "/home/Ucals/projects/florent-code-league-llm-rl"
S = ("/tmp/claude-1000/-home-Ucals-projects-florent-code-league-llm-rl/"
     "05d146e7-6b75-4d33-a413-788991e5ff01/scratchpad")
RIVAL = f"{S}/rivals/tempest_fast"
ME = f"{REPO}/bots/luc/pantheon_replica_day3"


def local_maps():
    out = {}
    for f in sorted(glob.glob(f"{REPO}/maps/*.map26")):
        m = decode.parse(open(f, "rb").read(), "Map")
        g = tuple(tuple(r.get("tiles", [])) for r in m.get("rows", []))
        out[(m.get("width"), m.get("height"), g)] = f
    return out


def actions(replay, team, upto):
    """Seat `team`'s visible actions per round."""
    per, posn, owner = {}, {}, {}
    for c in replay["map"]["cores"]:
        posn[c["id"]] = c["pos"]
        owner[c["id"]] = c.get("team", "TEAM_A")
    for rnd, ups in enumerate(replay["turns"]):
        if rnd >= upto:
            break
        acts = []
        for u in ups:
            if "placeEntity" in u:
                e = u["placeEntity"]["entity"]
                t = e.get("team", "TEAM_A")
                owner[e["id"]] = t
                p = decode.pos(e.get("position", {}))
                posn[e["id"]] = p
                if t == team:
                    acts.append(("build", decode.entity_kind(e), p))
            elif "moveBuilderBot" in u:
                mv = u["moveBuilderBot"]
                i = mv["id"]
                to = decode.pos(mv.get("to", {}))
                frm = posn.get(i)
                posn[i] = to
                if owner.get(i) == team and frm is not None:
                    kind = ("throw" if max(abs(to[0]-frm[0]),
                                           abs(to[1]-frm[1])) > 1 else "walk")
                    acts.append((kind, frm, to))
            elif "removeEntity" in u:
                i = u["removeEntity"]["id"]
                if owner.get(i) == team:
                    acts.append(("remove", posn.get(i)))
        per[rnd] = acts
    return per


def kill_round(replay, victim_team):
    cores = {c.get("team", "TEAM_A"): c for c in replay["map"]["cores"]}
    if victim_team not in cores:
        return None
    cid = cores[victim_team]["id"]
    for rnd, ups in enumerate(replay["turns"]):
        for u in ups:
            if "removeEntity" in u and u["removeEntity"]["id"] == cid:
                return rnd
    return None


def main():
    upto = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    maps = local_maps()
    rows, matched, total = [], 0, 0
    os.makedirs(f"{S}/repro_v20", exist_ok=True)
    for rp in sorted(glob.glob(f"{S}/pantheon/vs_us_v20/*.replay26")):
        real = decode.decode(rp)
        m = real["map"]
        key = (m["width"], m["height"], tuple(tuple(x) for x in m["grid"]))
        mp = maps.get(key)
        if not mp:
            continue
        name = os.path.basename(mp).replace(".map26", "")
        # Which seat is Pantheon? tempest_fast loses, so the winner's seat.
        pan = "TEAM_A" if real["winner"] == "TEAM_A" else "TEAM_B"
        out = f"{S}/repro_v20/{name}_{os.path.basename(rp)[:8]}.replay26"
        order = ([ME, RIVAL] if pan == "TEAM_A" else [RIVAL, ME])
        subprocess.run(["fcode", "run", *order, mp, "--tle", "10",
                        "--replay", out], capture_output=True, text=True,
                       cwd=REPO, timeout=600)
        if not os.path.exists(out):
            continue
        mine = decode.decode(out)
        a, b = actions(real, pan, upto), actions(mine, pan, upto)
        first, same = None, 0
        for r in range(upto):
            if a.get(r) == b.get(r):
                same += 1
            else:
                first = r
                break
        matched += same
        total += upto
        victim = "TEAM_B" if pan == "TEAM_A" else "TEAM_A"
        rows.append((name, kill_round(real, victim), kill_round(mine, victim),
                     first, a, b))
    print("%-11s | %-9s | %-9s | first divergence" % ("map", "real kill", "ours"))
    print("-" * 58)
    deltas = []
    for name, rk, mk, first, a, b in rows:
        if rk is not None and mk is not None:
            deltas.append(mk - rk)
        print("%-11s | %-9s | %-9s | %s" % (
            name, rk, mk, "identical" if first is None else "r%d" % first))
    print("-" * 58)
    print("action agreement: %d/%d rounds (%.0f%%)" % (
        matched, total, 100 * matched / max(1, total)))
    if deltas:
        print("median kill-round delta: %+.0f" % statistics.median(deltas))
    # show the earliest divergences in detail
    print("\nfirst divergence detail (earliest 4):")
    for name, rk, mk, first, a, b in sorted(
            [r for r in rows if r[3] is not None], key=lambda r: r[3])[:4]:
        print("  %s r%d" % (name, first))
        print("    real: %s" % (a.get(first),))
        print("    ours: %s" % (b.get(first),))


main()
