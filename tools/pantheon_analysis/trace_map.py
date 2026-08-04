"""Side-by-side action trace for one map: real Pantheon v20 vs our replica.

Usage: trace_map.py <mapname> [rounds]
"""
import glob, os, subprocess, sys
import decode

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
        out[(m.get("width"), m.get("height"), g)] = os.path.basename(f).replace(".map26", "")
    return out


def acts(replay, team, upto):
    per, posn, owner = {}, {}, {}
    for c in replay["map"]["cores"]:
        posn[c["id"]] = c["pos"]
        owner[c["id"]] = c.get("team", "TEAM_A")
    for rnd, ups in enumerate(replay["turns"]):
        if rnd >= upto:
            break
        out = []
        for u in ups:
            if "placeEntity" in u:
                e = u["placeEntity"]["entity"]
                t = e.get("team", "TEAM_A")
                owner[e["id"]] = t
                p = decode.pos(e.get("position", {}))
                posn[e["id"]] = p
                if t == team:
                    out.append(f"build {decode.entity_kind(e)[:4]}@{p}")
            elif "moveBuilderBot" in u:
                mv = u["moveBuilderBot"]
                i = mv["id"]
                to = decode.pos(mv.get("to", {}))
                frm = posn.get(i)
                posn[i] = to
                if owner.get(i) == team and frm is not None:
                    big = max(abs(to[0]-frm[0]), abs(to[1]-frm[1])) > 1
                    out.append(f"{'THROW' if big else 'walk'} {frm}->{to}")
            elif "removeEntity" in u:
                i = u["removeEntity"]["id"]
                if owner.get(i) == team:
                    out.append(f"remove@{posn.get(i)}")
        per[rnd] = out
    return per


def main():
    want = sys.argv[1]
    upto = int(sys.argv[2]) if len(sys.argv) > 2 else 14
    maps = local_maps()
    real_path = None
    for rp in sorted(glob.glob(f"{S}/pantheon/vs_us_v20/*.replay26")):
        r = decode.decode(rp)
        m = r["map"]
        key = (m["width"], m["height"], tuple(tuple(x) for x in m["grid"]))
        if maps.get(key) == want:
            real_path = rp
            break
    if real_path is None:
        print(f"no real game on {want}")
        return
    real = decode.decode(real_path)
    pan = "TEAM_A" if real["winner"] == "TEAM_A" else "TEAM_B"
    cores = {c.get("team", "TEAM_A"): c for c in real["map"]["cores"]}
    other = "TEAM_B" if pan == "TEAM_A" else "TEAM_A"
    print(f"{want}: Pantheon seat {pan} core {cores[pan]['pos']}, "
          f"enemy core {cores[other]['pos']}, map "
          f"{real['map']['width']}x{real['map']['height']}")

    out = f"{S}/trace_{want}.replay26"
    order = [ME, RIVAL] if pan == "TEAM_A" else [RIVAL, ME]
    subprocess.run(["fcode", "run", *order, f"{REPO}/maps/{want}.map26",
                    "--tle", "10", "--replay", out],
                   capture_output=True, text=True, cwd=REPO, timeout=600)
    mine = decode.decode(out)
    a, b = acts(real, pan, upto), acts(mine, pan, upto)
    first = None
    for rnd in range(upto):
        same = a.get(rnd) == b.get(rnd)
        if not same and first is None:
            first = rnd
        mark = "  " if same else ">>"
        print(f"{mark} r{rnd:<2}")
        print(f"     real: {a.get(rnd)}")
        if not same:
            print(f"     ours: {b.get(rnd)}")
    print(f"\nfirst divergence: {'none' if first is None else 'r%d' % first}")


main()
