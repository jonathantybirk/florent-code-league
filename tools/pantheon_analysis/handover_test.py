"""Run the puppet with a scripted prefix and diff what it does after handover.

Usage: handover_test.py <map> <handover_round> [rounds_to_show]
"""
import glob, os, subprocess, sys
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
    per, posn, owner = {}, {}, {}
    for c in replay["map"]["cores"]:
        posn[c["id"]] = c["pos"]
        owner[c["id"]] = c.get("team", "TEAM_A")
    for rnd, ups in enumerate(replay["turns"]):
        if rnd >= hi:
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
        if rnd >= lo:
            per[rnd] = out
    return per


def main():
    want = sys.argv[1]
    handover = int(sys.argv[2])
    show = int(sys.argv[3]) if len(sys.argv) > 3 else 10

    subprocess.run([sys.executable, f"{REPO}/tools/pantheon_analysis/make_script.py",
                    want], capture_output=True, text=True,
                   cwd=f"{REPO}/tools/pantheon_analysis")
    with open(f"{PUPPET}/handover.py", "w") as fh:
        fh.write(f"HANDOVER_ROUND = {handover}\n")

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

    out = f"{S}/handover_{want}_{handover}.replay26"
    order = [PUPPET, RIVAL] if pan == "TEAM_A" else [RIVAL, PUPPET]
    subprocess.run(["fcode", "run", *order, f"{REPO}/maps/{want}.map26",
                    "--tle", "10", "--replay", out],
                   capture_output=True, text=True, cwd=REPO, timeout=600)
    if not os.path.exists(out):
        print("local run produced no replay")
        return
    mine = decode.decode(out)
    hi = handover + show
    a, b = acts(real, pan, handover, hi), acts(mine, pan, handover, hi)
    print(f"{want}: seat {pan}, handover at r{handover}")
    agree = 0
    for rnd in range(handover, hi):
        same = a.get(rnd) == b.get(rnd)
        agree += same
        print(f"{'  ' if same else '>>'} r{rnd:<3} real: {a.get(rnd)}")
        if not same:
            print(f"      ours: {b.get(rnd)}")
    print(f"\nagreement after handover: {agree}/{show}")


main()
