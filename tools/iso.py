"""Build an ISOLATED sandbox under e10/_iso so this agent's runs cannot collide with the two
other agents that are live in the repo right now.

Both they and I call run_game, and every run_game scrubs `bots/__pycache__` recursively. If we
scrub each other's trees mid-load the victim's bot goes inert (G30) and the sweep silently
measures garbage -- the exact failure mode the brief warns about. So: copy every bot I need into
my own tree once, and never touch the repo's copies again.

usage:  python iso.py [name=srcdir ...]
"""
import pathlib
import shutil
import sys

REPO = pathlib.Path(r"c:\Users\edlun\Desktop\lucky shots\Hackathons\florent-code-league")
HERE = pathlib.Path(__file__).resolve().parent
ISO = HERE / "_iso"

OPPONENTS = {
    "idle": "bots/zoo/idle",
    "starter_fixed": "bots/zoo/starter_fixed",
    "jonbot": "bots/rivals/jonbot",
    "vanguard": "bots/rivals/vanguard",
    "luc1": "bots/rivals/luc1",
    "lockin": "bots/rivals/lockin",
}


def cp(name, src):
    src = pathlib.Path(src)
    if not src.is_absolute():
        src = REPO / src
    dst = ISO / name
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    n = len(list(dst.rglob("*.py")))
    print("  %-16s <- %-32s %d files" % (name, src.name, n))
    return dst


def main():
    ISO.mkdir(parents=True, exist_ok=True)
    print("sandbox %s" % ISO)
    pairs = dict(OPPONENTS)
    for arg in sys.argv[1:]:
        k, _, v = arg.partition("=")
        pairs[k] = v
    for name, src in sorted(pairs.items()):
        cp(name, src)
    for pc in ISO.rglob("__pycache__"):
        shutil.rmtree(pc, ignore_errors=True)
    print("done")


if __name__ == "__main__":
    main()
