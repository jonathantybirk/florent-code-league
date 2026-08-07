#!/usr/bin/env python3
"""Standalone checks for the parts of lib/ that need no engine.

    uv run python bots/modulah/selftest.py

The packing layer is worth testing here rather than in a match because a
silent field collision produces plausible-looking numbers rather than a crash,
and a match would never tell you. Anything needing a live Controller (econ,
threat) is exercised by the in-match probe instead -- see README.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

import comms  # noqa: E402

FAILS: list[str] = []


def check(label: str, got, want) -> None:
    if got != want:
        FAILS.append(f"{label}: got {got!r}, want {want!r}")


def test_field_roundtrip() -> None:
    f = comms.Field(4, 6, signed=True)
    for v in (-32, -7, 0, 5, 31):
        check(f"signed {v}", f.unpack(f.pack(0, v)), v)
    u = comms.Field(0, 3)
    for v in (0, 3, 7):
        check(f"unsigned {v}", u.unpack(u.pack(0, v)), v)


def test_clamping_not_wrapping() -> None:
    """Over-range values must saturate. A wrapped field reads as a plausible
    wrong answer; a clamped one reads as 'at least this much'."""
    u = comms.Field(0, 3)
    check("clamp high", u.unpack(u.pack(0, 99)), 7)
    check("clamp low", u.unpack(u.pack(0, -5)), 0)
    s = comms.Field(0, 6, signed=True)
    check("clamp signed high", s.unpack(s.pack(0, 500)), 31)
    check("clamp signed low", s.unpack(s.pack(0, -500)), -32)


def test_fields_do_not_collide() -> None:
    """Every schema must be injective across all its fields at once."""
    word = comms.pack_threat(hp=376, dhp=-9, burst=41, round_no=7)
    got = comms.unpack_threat(word)
    check("threat hp", got["hp"], 376)
    check("threat dhp", got["dhp"], -9)
    check("threat burst", got["burst"], 41)

    sched = [7, 0, 3, 1, 5]
    check("econ", comms.unpack_econ(comms.pack_econ(sched, 3)), sched)

    recs = [(-8, 7, True, 5), (3, -2, False, 0)]
    got = comms.unpack_turrets(comms.pack_turrets(recs, 9))
    check("turret count", len(got), 2)
    check("turret dx", got[0]["dx"], -8)
    check("turret dy", got[0]["dy"], 7)
    check("turret kind", got[0]["is_sentinel"], True)
    check("turret facing", got[0]["facing"], 5)
    check("turret2 dx", got[1]["dx"], 3)
    check("turret2 sentinel", got[1]["is_sentinel"], False)

    b = comms.unpack_builder(comms.pack_builder(comms.ACT_HEAL_CORE, 28, 5, target=(19, 4)))
    check("builder action", b["action"], comms.ACT_HEAL_CORE)
    check("builder target", b["target"], (19, 4))


def test_hp_bins_keep_low_end_usable() -> None:
    """2-hp bins, not 4. Damage comes in 2 / 7 / 18, whose gcd with 4 is 1, so
    core hp lands on every residue -- and the low end is where it decides
    whether you survive a round."""
    for hp in (500, 493, 12, 7, 2, 0):
        got = comms.unpack_threat(comms.pack_threat(hp, 0, 0, 0))["hp"]
        if abs(got - hp) > 1:
            FAILS.append(f"hp bin {hp}: got {got}, off by {abs(got - hp)}")


def test_arrivals_re_anchor_to_absolute_rounds() -> None:
    """A reader is always behind the writer, so bucket index is not "rounds
    from now". Re-anchoring via the heartbeat is what keeps consumers honest.

    Live evidence for the shift this corrects: the Core computed [1,0,0,0,0]
    at round R while Builders read [0,1,0,0,0] from the R-1 write.
    """
    word = comms.pack_econ([2, 0, 0, 0, 3], round_no=40)
    # Read in the same round the Core wrote: buckets land at +2 and +6.
    check("same-round anchor", comms.arrivals_from_now(word, 40), {42: 2, 46: 3})
    # Read one round later -- the real case. Same absolute rounds, not shifted.
    check("next-round anchor", comms.arrivals_from_now(word, 41), {42: 2, 46: 3})
    # A bucket that has already landed is dropped rather than double-counted.
    check("landed dropped", comms.arrivals_from_now(word, 43), {46: 3})


def test_staleness() -> None:
    """A slot must read stale once its owner stops writing, and an untouched
    zero word must never read as live."""
    w = comms.pack_threat(400, 0, 0, round_no=10)
    check("fresh same round", comms.is_fresh(w, 10), True)
    check("fresh +3", comms.is_fresh(w, 13), True)
    check("stale +9", comms.is_fresh(w, 19), False)
    check("zero word never fresh", comms.is_fresh(0, 4), False)


def test_all_words_fit_u32() -> None:
    words = [
        comms.pack_econ([7] * comms.ECON_HORIZON, 15),
        comms.pack_threat(510, -32, 63, 15),
        comms.pack_turrets([(-8, -8, True, 7)] * 2, 15),
        comms.pack_builder(7, 60, 15, target=(63, 63)),
    ]
    for i, w in enumerate(words):
        if not (0 <= w <= 0xFFFFFFFF):
            FAILS.append(f"word {i} outside u32: {w}")


def main() -> int:
    for fn in list(globals().values()):
        if callable(fn) and getattr(fn, "__name__", "").startswith("test_"):
            fn()
    if FAILS:
        print("FAILED:\n  " + "\n  ".join(FAILS))
        return 1
    print("selftest: all packing checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
