"""Why did THIS game go wrong? A per-game post-mortem that names the failure mode.

A 3-2 match result tells you nothing about the two games you threw away, and win rate averages
exactly the information you need to fix them. This reads a replay and reports, for our side, the
decisive facts: when the ring went up, when units died, when the ammunition ran out, what the two
Cores' health did, and -- the one that is otherwise invisible -- which units RAN and did NOTHING.

The idle detector is the point. The replay records a BotOutput for every unit that executed each
round, and separately records moves, builds, heals, attacks and shots. A unit that appears in the
first and in none of the second was alive, was asked to decide, and decided to do nothing. Every
serious bug this bot has had looked like that from the outside: the Builder that reached its stand
tile on round 16 and sat there for 984 rounds, the one that read a conveyor as a free firing spot,
the Sentinels that aimed at empty ground. None of them showed up in a win rate.

Usage
    python tools/autopsy.py replays/x.replay26 [--team a|b]
    python tools/autopsy.py --match <match-id>            every game of a ladder match
    python tools/autopsy.py --local <botA> <botB> <map>   play one and dissect it
"""

import os
import pathlib
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import fcode                                            # noqa: E402
from fcode.fcode_engine import run_game                 # noqa: E402
from diag.replay import load_replay                     # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENGINE = str(pathlib.Path(fcode.__file__).resolve().parent)
FCODE = str(ROOT / ".venv" / "Scripts" / "fcode.exe")
US_NAME = "Powered by SmartFridge"

IDLE_ALARM = 8          # consecutive do-nothing rounds worth reporting
DRY_ALARM = 20          # consecutive rounds at zero ammo worth reporting


def scrub():
    for pc in ROOT.rglob("__pycache__"):
        if ".venv" not in pc.parts:
            shutil.rmtree(pc, ignore_errors=True)


def dissect(path, team="a", label=""):
    r = load_replay(str(path))
    foe = "b" if team == "a" else "a"
    cores = {t: (x, y) for _i, t, x, y in r.cores}

    built = []
    deaths = []
    idle_run = {}
    idle_worst = {}
    dry_from = None
    dry_runs = []
    hp_ours, hp_theirs = [], []
    foe_low, foe_last = None, None
    shots = heals = 0

    for t, st, ta in r.iter_states():
        acted = set(ta.moves) | set(ta.builds) | set(ta.heals) | set(ta.attacks)
        for frm, _to in ta.fires:
            for e in st.entities.values():
                if (e.x, e.y) == frm:
                    acted.add(e.id)
                    if e.team == team:
                        shots += 1
                    break
        for eid in ta.heals:
            e = st.entities.get(eid)
            if e is not None and e.team == team:
                heals += 1

        for uid in ta.ran:
            e = st.entities.get(uid)
            if e is None or e.team != team or e.kind == "core":
                continue
            if uid in acted:
                if idle_run.get(uid, 0) >= IDLE_ALARM:
                    idle_worst[uid] = max(idle_worst.get(uid, 0), idle_run[uid])
                idle_run[uid] = 0
            else:
                idle_run[uid] = idle_run.get(uid, 0) + 1
                if idle_run[uid] > idle_worst.get(uid, 0):
                    idle_worst[uid] = idle_run[uid]

        for e in ta.placed:
            if e.team == team and e.kind != "core":
                built.append((t, e.kind, (e.x, e.y)))
        for rid in ta.removed:
            e = st.entities.get(rid)
            if e is not None and e.team == team and e.kind != "core":
                deaths.append((t, e.kind, rid))

        ammo = st.players[team].ammo
        if ammo <= 0:
            dry_from = t if dry_from is None else dry_from
        elif dry_from is not None:
            if t - dry_from >= DRY_ALARM:
                dry_runs.append((dry_from, t))
            dry_from = None

        for e in st.entities.values():
            if e.kind != "core":
                continue
            if e.team == team and t % 40 == 0:
                hp_ours.append((t, e.hp))
            if e.team == foe:
                foe_last = e.hp
                foe_low = e.hp if foe_low is None else min(foe_low, e.hp)
                if t % 40 == 0:
                    hp_theirs.append((t, e.hp))
    if dry_from is not None and r.total_turns - dry_from >= DRY_ALARM:
        dry_runs.append((dry_from, r.total_turns))

    won = r.winner == team
    verdict = classify(won, foe_low, foe_last, built, deaths, dry_runs, idle_worst, r.total_turns)

    print("%s  %dx%d  %s at turn %d" % (label or path.name, r.width, r.height,
                                        "WON" if won else "LOST", r.total_turns))
    print("   VERDICT: %s" % verdict)
    ring = [(t, p) for t, k, p in built if k in ("sentinel", "gunner")]
    print("   turrets up   : %s" % (["r%d%s" % (t, p) for t, p in ring][:6] or "NONE"))
    others = {}
    for _t, k, _p in built:
        if k not in ("sentinel", "gunner"):
            others[k] = others.get(k, 0) + 1
    print("   also built   : %s" % (others or "nothing"))
    print("   their Core   : low=%s  final=%s   %s" % (foe_low, foe_last, hp_theirs[:7]))
    print("   our Core     : %s" % hp_ours[:7])
    print("   shots=%d heals=%d   ammo dry: %s" % (
        shots, heals, ["r%d-%d" % ab for ab in dry_runs[:3]] or "never"))
    if deaths:
        print("   we lost      : %s" % ["r%d %s" % (t, k) for t, k, _ in deaths[:6]])
    bad = sorted(((v, k) for k, v in idle_worst.items() if v >= IDLE_ALARM), reverse=True)
    if bad:
        print("   IDLE UNITS   : %s" % ["#%d did nothing %d rounds" % (k, v) for v, k in bad[:4]])
    print()
    return verdict


def classify(won, foe_low, foe_last, built, deaths, dry_runs, idle_worst, turns):
    """Name the failure, in the order that a fix would be attempted."""
    turrets = [t for t, k, _p in built if k in ("sentinel", "gunner")]
    worst_idle = max(idle_worst.values()) if idle_worst else 0
    if won and turns < 100:
        return "rush landed (turn %d)" % turns
    if won:
        return "won late (turn %d) -- the rush did not do it" % turns
    if not turrets:
        return "NO TURRETS EVER BUILT -- the Builder never got a ring up"
    if worst_idle >= 40:
        return "STALLED -- a unit stood idle for %d rounds" % worst_idle
    if foe_low is not None and foe_last is not None and foe_last > foe_low + 60:
        return ("OUTHEALED -- their Core reached %d then recovered to %d"
                % (foe_low, foe_last))
    if dry_runs and dry_runs[0][0] < turns * 0.6:
        return "AMMO DRY from r%d -- the ring fell silent" % dry_runs[0][0]
    if len([d for d in deaths if d[1] in ("sentinel", "gunner")]) >= 2:
        return "RING DESTROYED -- they killed the turrets"
    if len(turrets) < 4:
        return "RING INCOMPLETE -- only %d turret(s) went up" % len(turrets)
    return "lost with a full ring, no single cause stands out"


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return
    if args[0] == "--local":
        bot_a, bot_b, mapname = args[1], args[2], args[3]
        scrub()
        out = ROOT / "replays" / "autopsy.replay26"
        out.parent.mkdir(parents=True, exist_ok=True)
        run_game(str(ROOT / bot_a / "main.py"), str(ROOT / bot_b / "main.py"), ENGINE,
                 str(ROOT / "maps" / (mapname + ".map26")), str(out), 1, 0)
        scrub()
        dissect(out, "a", "%s vs %s on %s" % (bot_a, bot_b, mapname))
        return
    if args[0] == "--match":
        mid = args[1]
        dest = ROOT / "replays" / "ladder"
        dest.mkdir(parents=True, exist_ok=True)
        subprocess.run([FCODE, "match", "replay", mid], cwd=str(dest),
                       capture_output=True, text=True, timeout=300)
        info = subprocess.run([FCODE, "match", "info", mid], capture_output=True,
                              text=True, timeout=120).stdout
        team = "a" if ("Team A:  " + US_NAME) in info else "b"
        verdicts = {}
        for g in range(1, 6):
            path = dest / ("%s_game_%d.replay26" % (mid, g))
            if path.exists():
                v = dissect(path, team, "game %d" % g)
                verdicts[v.split(" --")[0].split(" (")[0]] = verdicts.get(
                    v.split(" --")[0].split(" (")[0], 0) + 1
        print("SUMMARY across the match:")
        for k, n in sorted(verdicts.items(), key=lambda kv: -kv[1]):
            print("   %2d x %s" % (n, k))
        return
    team = "a"
    if "--team" in args:
        team = args[args.index("--team") + 1]
    dissect(pathlib.Path(args[0]), team)


main()
