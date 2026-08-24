"""Replay-for-replay reproduction test.

Take a real ladder game (our tempest_fast, seat A, vs Pantheon, seat B), rerun
the same map locally with pantheon_clone in seat B, and diff seat B's actions
round by round. The engine is deterministic, so a faithful clone should track
the real Pantheon at least until our own bot's behaviour diverges.
"""
import glob, os, subprocess, sys
import decode

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = "/home/Ucals/projects/florent-code-league-llm-rl"
RIVAL = f"{HERE}/rivals/tempest_fast"
CLONE = f"{REPO}/bots/luc/pantheon_clone"


def local_maps():
    out = {}
    for f in sorted(glob.glob(f"{REPO}/maps/*.map26")):
        m = decode.parse(open(f, "rb").read(), "Map")
        g = tuple(tuple(r.get("tiles", [])) for r in m.get("rows", []))
        out[(m.get("width"), m.get("height"), g)] = f
    return out


def actions(replay, team, upto=12):
    """Seat `team`'s visible actions per round, as comparable tuples."""
    per = {}
    posn = {}
    for c in replay["map"]["cores"]:
        posn[c["id"]] = c["pos"]
    owner = {c["id"]: c.get("team", "TEAM_A") for c in replay["map"]["cores"]}
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
                    kind = "throw" if max(abs(to[0]-frm[0]),
                                          abs(to[1]-frm[1])) > 1 else "walk"
                    acts.append((kind, frm, to))
            elif "removeEntity" in u:
                i = u["removeEntity"]["id"]
                if owner.get(i) == team:
                    acts.append(("remove", posn.get(i)))
        per[rnd] = acts
    return per


def main():
    upto = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    maps = local_maps()
    reps = sorted(glob.glob(f"{HERE}/pantheon/vs_us/*.replay26"))
    os.makedirs(f"{HERE}/repro", exist_ok=True)
    totals = [0, 0]
    for rp in reps:
        real = decode.decode(rp)
        m = real["map"]
        key = (m["width"], m["height"],
               tuple(tuple(x) for x in m["grid"]))
        mp = maps.get(key)
        if not mp:
            continue
        name = os.path.basename(mp).replace(".map26", "")
        # Pantheon is seat B in all three matches.
        out = f"{HERE}/repro/{os.path.basename(rp)}"
        subprocess.run(["fcode", "run", RIVAL, CLONE, mp, "--tle", "10",
                        "--replay", out], capture_output=True, text=True,
                       cwd=REPO, timeout=600)
        if not os.path.exists(out):
            print(f"{name:12s} local run produced no replay")
            continue
        mine = decode.decode(out)
        a = actions(real, "TEAM_B", upto)
        b = actions(mine, "TEAM_B", upto)
        first_diff = None
        same = 0
        for r in range(upto):
            if a.get(r) == b.get(r):
                same += 1
            else:
                first_diff = r
                break
        totals[0] += same
        totals[1] += upto
        flag = "identical" if first_diff is None else f"diverges at r{first_diff}"
        print(f"{name:12s} rounds 0-{upto-1}: {flag}")
        if first_diff is not None and first_diff <= 6:
            print(f"    real r{first_diff}: {a.get(first_diff)}")
            print(f"    mine r{first_diff}: {b.get(first_diff)}")
    print(f"\nmatching rounds before first divergence: {totals[0]}/{totals[1]}")


main()
