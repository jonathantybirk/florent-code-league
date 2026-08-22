"""Run one local match and report what our side actually DID with its titanium.

Win rate hides the failure that mattered most here: an economy that mines, banks the income and
never converts it into either healing or ammunition. That shows up as a flat titanium curve with
zero heals, and no scoreboard column will tell you.
"""
import os, pathlib, shutil, sys
sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
import fcode
from fcode.fcode_engine import run_game
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from diag.replay import load_replay

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENGINE = str(pathlib.Path(fcode.__file__).resolve().parent)


def main():
    us, foe, mapname = sys.argv[1], sys.argv[2], sys.argv[3]
    for pc in ROOT.rglob("__pycache__"):
        if ".venv" not in pc.parts:
            shutil.rmtree(pc, ignore_errors=True)
    out = ROOT / "replays" / "spend.replay26"
    out.parent.mkdir(parents=True, exist_ok=True)
    res = run_game(str(ROOT / us / "main.py"), str(ROOT / foe / "main.py"), ENGINE,
                   str(ROOT / "maps" / (mapname + ".map26")), str(out), 1, 0)
    r = load_replay(str(out))
    heals = fires = 0
    built = {}
    curve = []
    for t, st, ta in r.iter_states():
        for eid in ta.heals:
            e = st.entities.get(eid)
            if e is not None and e.team == "a":
                heals += 1
        for e in ta.placed:
            if e.team == "a":
                built[e.kind] = built.get(e.kind, 0) + 1
        for frm, _to in ta.fires:
            for x in st.entities.values():
                if (x.x, x.y) == frm and x.team == "a" and x.kind in ("gunner", "sentinel"):
                    fires += 1
                    break
        if t % 50 == 0:
            curve.append((t, st.players["a"].titanium, st.players["a"].ammo))
    print("%s on %s: winner=%s turns=%s (%s)" % (us, mapname, res["winner"], res["turns"],
                                                 res["win_condition"]))
    print("  we built : %s" % built)
    print("  heals=%d  shots=%d" % (heals, fires))
    print("  (round, titanium, ammo): %s" % curve[:8])


main()
