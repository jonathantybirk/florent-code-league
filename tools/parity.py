"""Parity: prove two builds are the SAME BOT, game for game.

Matching win/loss over a sweep is weak evidence -- two builds can disagree on a hundred actions
and still split the same 30 games. The engine is deterministic (G26) and the replay records every
spawn, move, fire, destroy and hit-point delta, so the real test is whether the two ACTION
STREAMS are identical.

They cannot be compared as raw bytes, because the replay also snapshots the 16 store slots each
time a unit writes one (event kind 6), and the posture refactor deliberately repurposes two of
those slots -- slot 3 grows a posture field beside the alarm bit, slot 11 grows the evidence word
above the symmetry mask. Those values differ by design and change no action. So this compares:

    ACTIONS   every event except kind 6, in order, byte for byte
    STORE     kind 6 decoded slot by slot; reports WHICH slot indices ever differ

Exact parity therefore means: identical actions, and store differences confined to the slots the
refactor is allowed to touch.

Runs inside its own sandbox so it cannot collide with the other agents live in the repo.

usage:  python parity.py <botA> <botB> <known|unseen|both> [opponents...]
"""
import hashlib
import os
import pathlib
import shutil
import sys

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
sys.dont_write_bytecode = True

import fcode
from fcode.fcode_engine import run_game
from mapio import fields

REPO = pathlib.Path(r"c:\Users\edlun\Desktop\lucky shots\Hackathons\florent-code-league")
HERE = pathlib.Path(__file__).resolve().parent
ISO = HERE / os.environ.get("FF_ISO", "_iso")
ENGINE = str(pathlib.Path(fcode.__file__).resolve().parent)

PANEL = ["idle", "starter_fixed", "luc1", "lockin", "jonbot", "vanguard"]
STORE_EV = 6            # per-round team-state snapshot carrying both teams' 16 store slots
ALLOWED_SLOTS = {3, 11}  # S_STATE (alarm+posture) and S_SYMMETRY (mask+evidence)


def scrub():
    for pc in ISO.rglob("__pycache__"):
        shutil.rmtree(pc, ignore_errors=True)


def resolve(bot):
    p = ISO / bot
    if not p.exists():
        p = pathlib.Path(bot)
        if not p.is_absolute():
            p = REPO / bot
    return str(p / "main.py") if p.is_dir() else str(p)


def varints(blob):
    out, cur, sh = [], 0, 0
    for byte in blob:
        cur |= (byte & 0x7F) << sh
        if byte & 0x80:
            sh += 7
        else:
            out.append(cur)
            cur, sh = 0, 0
    return out


def unwrap(v):
    """Peel the single-field-1 wrappers the replay nests events in."""
    while True:
        fs = fields(v)
        if len(fs) == 1 and fs[0][0] == 1 and fs[0][1] == 2:
            v = fs[0][2]
            continue
        return fs


def split(path):
    """(action-stream digest, {(team, slot): set of values ever held}) for one replay.

    Event kind 6 is a per-round TEAM STATE snapshot carrying BOTH teams:
        ev6 { 1 { 1 {1:titanium, 6:<16 packed varints>, 7:scale}     <- team A
                  2 {1:titanium, 6:<16 packed varints>} } }          <- team B
    Comparing snapshots POSITIONALLY is wrong -- if the two builds publish different numbers of
    them the tail is silently dropped -- so collect the SET of values each slot ever holds and
    compare the sets.
    """
    data = pathlib.Path(path).read_bytes()
    h = hashlib.sha256()
    slots = {}
    for fn, wt, v in fields(data):
        if fn != 3:
            h.update(b"|T%d|" % fn)
            h.update(v if isinstance(v, bytes) else str(v).encode())
            continue
        for f2, w2, v2 in fields(v):
            if f2 != 1:
                continue
            for k, kw, kv in fields(v2):
                if k == STORE_EV:
                    for team, tw, tv in unwrap(kv):
                        if not isinstance(tv, bytes):
                            continue
                        for f4, w4, v4 in fields(tv):
                            if f4 == 6 and isinstance(v4, bytes):
                                for i, val in enumerate(varints(v4)):
                                    slots.setdefault((team, i), set()).add(val)
                    continue
                h.update(b"|%d|" % k)
                h.update(kv if isinstance(kv, bytes) else str(kv).encode())
    return h.hexdigest()[:16], slots


def play(me, foe, mp, side, dest):
    scrub()
    a, b = (me, foe) if side == "a" else (foe, me)
    res = run_game(resolve(a), resolve(b), ENGINE, str(mp), str(dest), 1, 0)
    scrub()
    won = (res["winner"] == "A") if side == "a" else (res["winner"] == "B")
    raw = hashlib.sha256(pathlib.Path(dest).read_bytes()).hexdigest()[:16]
    act, stores = split(dest)
    return won, res["win_condition"], res["turns"], raw, act, stores


def main():
    a_bot, b_bot = sys.argv[1], sys.argv[2]
    pools = ("known", "unseen") if sys.argv[3] == "both" else (sys.argv[3],)
    opponents = sys.argv[4:] or PANEL

    da = HERE / ("_pa_%d.replay26" % os.getpid())
    db = HERE / ("_pb_%d.replay26" % os.getpid())
    n = raw_same = act_same = res_same = 0
    slotdiff = {}
    bad = []
    print("=== PARITY  %s  vs  %s   (fcode %s) ===" % (a_bot, b_bot, fcode.__version__))
    for pool in pools:
        maps = sorted((REPO / "maps").glob("*.map26")) if pool == "known" \
            else sorted((REPO / "maps" / "generated").glob("*.map26"))
        for foe in opponents:
            rec = [0, 0]
            for mp in maps:
                for side in ("a", "b"):
                    wa, ca, ta, ra, aa, sa = play(a_bot, foe, mp, side, da)
                    wb, cb, tb, rb, ab, sb = play(b_bot, foe, mp, side, db)
                    n += 1
                    rec[0 if wa else 1] += 1
                    if ra == rb:
                        raw_same += 1
                    if (wa, ca, ta) == (wb, cb, tb):
                        res_same += 1
                    if aa == ab:
                        act_same += 1
                    else:
                        bad.append("  ACTIONS DIFFER  %-8s %-14s %-22s %s   A=%s/%s/%s B=%s/%s/%s"
                                   % (pool, foe, mp.stem[:21], side,
                                      "W" if wa else "L", ca, ta,
                                      "W" if wb else "L", cb, tb))
                    for key in set(sa) | set(sb):
                        if sa.get(key, set()) != sb.get(key, set()):
                            slotdiff[key] = slotdiff.get(key, 0) + 1
            print("  %-8s %-16s A record %d-%d   (%d games)"
                  % (pool, foe, rec[0], rec[1], rec[0] + rec[1]))
    for f in (da, db):
        if f.exists():
            f.unlink()

    print("\n--- %d game pairs ---" % n)
    print("  identical RESULT   (win/cond/turns)   %d / %d" % (res_same, n))
    print("  identical ACTIONS  (all non-store)    %d / %d" % (act_same, n))
    print("  identical RAW BYTES                   %d / %d" % (raw_same, n))
    print("  store slots that ever differ: %s"
          % (", ".join("team%d/slot%d (%dx)" % (k[0], k[1], v)
                       for k, v in sorted(slotdiff.items())) or "none"))
    outside = sorted({k[1] for k in slotdiff} - ALLOWED_SLOTS)
    print("  ...OUTSIDE the slots the refactor repurposes %s: %s"
          % (sorted(ALLOWED_SLOTS), outside if outside else "NONE"))
    for b in bad[:40]:
        print(b)
    ok = act_same == n and res_same == n and not outside
    print("\n%s" % ("EXACT PARITY -- identical actions on every game; store differs only in the "
                    "slots the refactor repurposes" if ok else "NOT PARITY"))


if __name__ == "__main__":
    main()
