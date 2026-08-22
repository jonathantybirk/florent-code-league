import os, pathlib, sys, shutil
sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
import fcode
from fcode.fcode_engine import run_game
ROOT = pathlib.Path(".").resolve()
E = str(pathlib.Path(fcode.__file__).resolve().parent)
for pc in ROOT.rglob("__pycache__"):
    if ".venv" not in pc.parts: shutil.rmtree(pc, ignore_errors=True)
a, b, m = sys.argv[1], sys.argv[2], sys.argv[3]
r = run_game(str(ROOT/a/"main.py"), str(ROOT/b/"main.py"), E, str(ROOT/"maps"/(m+".map26")), os.devnull, 1, 0)
print("winner=%s turns=%s cond=%s" % (r["winner"], r["turns"], r["win_condition"]))
print(r.get("resign_message") or "(none)")
