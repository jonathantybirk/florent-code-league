"""Build a *shadow* of an arbitrary bot that logs every unit's decision to disk.

The shadow is a byte-for-byte copy of the original bot directory plus one extra
file, `_shadow.py`, and a rewritten `main.py`. The original bot is never
touched and never edited: its `main.py` is copied to `_origmain.py` and imported
from there, so its sibling imports (`import builder`, `import core`, ...) keep
resolving exactly as before.

What gets logged, one JSON object per (round, unit) decision:

    {"r": round, "id": entity_id, "ty": entity_type, "tm": team,
     "x":, "y":, "hp":, "acd": action_cooldown, "mcd": move_cooldown,
     "ti": titanium, "am": ammo, "sc": scale_percent, "nu": unit_count,
     "st": [16 store slots read at the start of the turn],
     "w": [[slot, value], ...]   # store writes this unit issued
     "a": [[method, arg, ...], ...]}   # every mutating call, in order

The store vector is the thing a replay cannot give you: no update message in
the `.replay26` schema carries a store write, so a policy that has to condition
on team coordination state can only get it here.

Correctness contract: the shadow must be behaviourally identical to the
original. It only observes -- it never changes an argument or a return value,
and every wrapper method returns the real controller's return value unchanged.
`verify()` below plays the same match with and without the shadow and asserts
the engine's result dict matches.

Usage::

    python shadow.py make bots/rivals/mistral  <outdir>  <logfile>
    python shadow.py verify bots/rivals/mistral --map sprint --vs bots/rivals/vanguard
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]

# --------------------------------------------------------------------------
# the runtime half -- written verbatim into the shadow directory
# --------------------------------------------------------------------------

_SHADOW_RUNTIME = r'''"""Recording proxy around the engine Controller. Generated -- do not edit."""

import json
import os

from fcode import GameError

_BASE = os.environ.get("FCL_SHADOW_LOG") or __LOG_DEFAULT__
# One file per worker PROCESS. Arena workers are separate processes appending to
# the same path, and interleaved appends tear lines -- measured as a 15-line
# drift across two identical 6-match runs. Sub-interpreters inside one worker
# share a pid and run sequentially under the shared GIL, so per-pid is exactly
# the right granularity. Matches within a file are split on the round counter
# resetting to 0.
LOG_PATH = _BASE + "." + str(os.getpid()) + ".jsonl"

# Every mutating entry point in the Controller API. `destroy` is here even
# though it costs no cooldown, and `write_store` is here because the store is
# the only cross-unit channel and is absent from the replay.
MUTATORS = (
    "move", "heal", "destroy", "self_destruct", "fire", "rotate", "launch",
    "spawn_builder", "convert_ammo", "write_store", "resign",
    "build", "build_conveyor", "build_splitter", "build_harvester",
    "build_barrier", "build_gunner", "build_sentinel", "build_launcher",
)


def _plain(v):
    """Reduce an engine value to something json can hold, without touching it."""
    if v is None or isinstance(v, (int, float, str, bool)):
        return v
    x = getattr(v, "x", None)
    if x is not None and hasattr(v, "y"):
        return [x, v.y]
    val = getattr(v, "value", None)
    if isinstance(val, str):
        return val
    return str(v)


class Recorder:
    """Forwards everything to the real controller and remembers the mutations."""

    def __init__(self, ct):
        self._ct = ct
        self.acts = []
        self.writes = []

    def __getattr__(self, name):
        target = getattr(self._ct, name)
        if name not in MUTATORS:
            return target

        def wrapped(*args, **kwargs):
            out = target(*args, **kwargs)
            rec = [name] + [_plain(a) for a in args]
            if kwargs:
                rec.append({k: _plain(v) for k, v in kwargs.items()})
            self.acts.append(rec)
            if name == "write_store" and len(args) >= 2:
                self.writes.append([args[0], args[1]])
            return out

        return wrapped


FAT = os.environ.get("FCL_SHADOW_FAT") == "1"

# Vision radius squared by entity type, from GameConstants.
VIS = {"core": 36, "builder_bot": 20, "gunner": 13, "sentinel": 32, "launcher": 26}

_ENV = {"empty": 0, "wall": 1, "ore_titanium": 2}
_KIND = {"builder_bot": 1, "core": 2, "gunner": 3, "sentinel": 4, "launcher": 5,
         "conveyor": 6, "splitter": 7, "harvester": 8, "barrier": 9}
_DIR = {"centre": 0, "north": 1, "northeast": 2, "east": 3, "southeast": 4,
        "south": 5, "southwest": 6, "west": 7, "northwest": 8}


def observe(ct):
    """The unit's ACTUAL local observation, as the engine would answer it.

    Vision is a raw euclidean disc with no occlusion, so this is exactly the
    set of tiles the unit can interrogate. Emitted as two parallel flat lists
    so the JSON stays small:

      "tiles": [dx, dy, env, ...]                       for every visible tile
      "ents":  [dx, dy, kind, mine, hp, facing, ...]    for every visible entity

    dx/dy are relative to the unit, so the record is already egocentric.
    """
    me = ct.get_position()
    mine_team = ct.get_team()
    tiles = []
    for p in ct.get_nearby_tiles():
        tiles.append(p.x - me.x)
        tiles.append(p.y - me.y)
        tiles.append(_ENV.get(ct.get_tile_env(p).value, 0))
    ents = []
    for eid in ct.get_nearby_entities():
        p = ct.get_position(eid)
        kind = ct.get_entity_type(eid).value
        facing = 0
        if kind in ("conveyor", "splitter", "gunner", "sentinel"):
            try:
                facing = _DIR.get(ct.get_direction(eid).value, 0)
            except GameError:
                facing = 0
        ents.append(p.x - me.x)
        ents.append(p.y - me.y)
        ents.append(_KIND.get(kind, 0))
        ents.append(1 if ct.get_team(eid) == mine_team else 0)
        ents.append(ct.get_hp(eid))
        ents.append(facing)
    return tiles, ents


def snapshot(ct):
    """The part of the observation the replay cannot reconstruct, plus keys."""
    row = {
        "r": ct.get_current_round(),
        "id": ct.get_id(),
        "ty": ct.get_entity_type().value,
        "tm": ct.get_team().value,
        "ti": ct.get_global_resources(),
        "am": ct.get_global_ammo(),
        "sc": ct.get_scale_percent(),
        "nu": ct.get_unit_count(),
        "hp": ct.get_hp(),
        "acd": ct.get_action_cooldown(),
        "mcd": ct.get_move_cooldown(),
        "st": [ct.read_store(i) for i in range(16)],
    }
    p = ct.get_position()
    row["x"], row["y"] = p.x, p.y
    row["mw"], row["mh"] = ct.get_map_width(), ct.get_map_height()
    if FAT:
        row["tiles"], row["ents"] = observe(ct)
    return row


def emit(row):
    fh = open(LOG_PATH, "a", encoding="utf-8")
    fh.write(json.dumps(row, separators=(",", ":")) + "\n")
    fh.close()
'''

_SHADOW_MAIN = r'''"""Shadowed entry point. Generated -- do not edit."""

import _origmain
import _shadow


class Player:
    """Wraps the original Player and records what it decides."""

    def __init__(self):
        self._inner = _origmain.Player()

    def run(self, ct):
        row = _shadow.snapshot(ct)
        rec = _shadow.Recorder(ct)
        # An uncaught exception permanently deletes the unit (G23), so the
        # original exception must propagate unchanged -- hence the duplicated
        # emit rather than a `finally`, which the engine's AST validator bans.
        try:
            self._inner.run(rec)
        except Exception as exc:
            row["a"] = rec.acts
            row["w"] = rec.writes
            row["e"] = type(exc).__name__ + ": " + str(exc)
            _shadow.emit(row)
            raise
        row["a"] = rec.acts
        row["w"] = rec.writes
        _shadow.emit(row)
'''


def make_shadow(bot_dir: Path, out_dir: Path, log_path: Path) -> Path:
    """Copy `bot_dir` to `out_dir` and install the recorder. Returns main.py."""
    bot_dir = Path(bot_dir).resolve()
    out_dir = Path(out_dir).resolve()
    if out_dir.exists():
        shutil.rmtree(out_dir)
    shutil.copytree(
        bot_dir, out_dir,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    (out_dir / "main.py").rename(out_dir / "_origmain.py")
    runtime = _SHADOW_RUNTIME.replace("__LOG_DEFAULT__", json.dumps(str(log_path)))
    (out_dir / "_shadow.py").write_text(runtime, encoding="utf-8", newline="\n")
    (out_dir / "main.py").write_text(_SHADOW_MAIN, encoding="utf-8", newline="\n")
    return out_dir / "main.py"


# --------------------------------------------------------------------------
# verification
# --------------------------------------------------------------------------

def verify(bot: str, opponent: str, maps: list[str], workers: int = 4) -> dict:
    """Play each map twice -- plain and shadowed -- and diff the engine result.

    The engine is deterministic, so any difference is the wrapper's fault.
    """
    sys.path.insert(0, str(REPO))
    from arena import resolve_bot, resolve_map            # noqa: PLC0415
    from arena.runner import run_matches                  # noqa: PLC0415

    tmp = Path(os.environ.get("TEMP", ".")) / "fcl_shadow_verify"
    tmp.mkdir(parents=True, exist_ok=True)
    for old in tmp.glob("verify.log*.jsonl"):
        old.unlink()
    logf = tmp / "verify.log"

    plain = resolve_bot(bot)
    opp = resolve_bot(opponent)
    shadowed = make_shadow(plain.parent, tmp / ("sh_" + plain.parent.name), logf)

    specs = []
    for m in maps:
        mp = str(resolve_map(m))
        specs.append({"a": str(plain), "b": str(opp), "map": mp, "seed": 1})
        specs.append({"a": str(shadowed), "b": str(opp), "map": mp, "seed": 1})
    results, stats = run_matches(specs, workers=workers)

    keys = ("winner", "turns", "win_condition", "a_titanium", "a_titanium_collected",
            "a_units", "a_buildings", "b_titanium", "b_titanium_collected",
            "b_units", "b_buildings")
    report = {"maps": {}, "identical": True, "log_lines": 0,
              "plain_seconds": 0.0, "shadow_seconds": 0.0}
    for i, m in enumerate(maps):
        p, s = results[2 * i], results[2 * i + 1]
        same = all(p[k] == s[k] for k in keys)
        report["identical"] &= same
        report["plain_seconds"] += p["elapsed"]
        report["shadow_seconds"] += s["elapsed"]
        report["maps"][m] = {
            "identical": same,
            "plain": {k: p[k] for k in keys},
            "shadow": {k: s[k] for k in keys},
        }
    parts = sorted(tmp.glob("verify.log*.jsonl"))
    bad = 0
    for part in parts:
        with open(part, encoding="utf-8") as fh:
            for line in fh:
                report["log_lines"] += 1
                try:
                    json.loads(line)
                except json.JSONDecodeError:
                    bad += 1
    report["log_bytes"] = sum(p.stat().st_size for p in parts)
    report["log_files"] = len(parts)
    report["torn_lines"] = bad
    report["stats"] = stats
    return report


def _cli(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    mk = sub.add_parser("make")
    mk.add_argument("bot")
    mk.add_argument("out")
    mk.add_argument("log")

    vf = sub.add_parser("verify")
    vf.add_argument("bot")
    vf.add_argument("--vs", default="bots/rivals/vanguard")
    vf.add_argument("--maps", nargs="*", default=["sprint", "duel", "fjord"])
    args = ap.parse_args(argv)

    if args.cmd == "make":
        p = make_shadow(Path(args.bot), Path(args.out), Path(args.log))
        print(p)
        return 0

    rep = verify(args.bot, args.vs, args.maps)
    print(json.dumps(rep, indent=1))
    return 0 if rep["identical"] else 1


if __name__ == "__main__":
    raise SystemExit(_cli(sys.argv[1:]))
