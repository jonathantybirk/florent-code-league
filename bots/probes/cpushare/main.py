"""Task 1.5 -- is the CPU budget per UNIT or shared across the TEAM?

The Core spawns builder bots up to TARGET_UNITS, and EVERY unit (Core included) burns BURN_US of
CPU each round before doing anything else. With a per-unit budget of 10 ms, a team of N units burns
N x 8 ms and nothing is ever flagged. With a per-team budget, everything after the first unit or two
is killed.

Read the answer straight out of the replay: BotOutput.tled is recorded per unit per round.
No self-reporting needed -- but the Core resigns at the end so the run terminates cleanly.
"""

import time

from fcode import Controller, Direction, EntityType, Position

BURN_US = 8000
TARGET_UNITS = 6
STOP_ROUND = 14

DIRECTIONS = [d for d in Direction if d != Direction.CENTRE]


def burn(ct, target_us):
    acc = 0
    c = ct.get_cpu_time_elapsed()
    if c == 0:                      # Windows: clock is dead, fall back to wall clock
        t0 = time.perf_counter()
        while (time.perf_counter() - t0) * 1e6 < target_us:
            for i in range(200):
                acc = (acc + i * 7) & 0xFFFFFF
        return
    while c < target_us:
        for i in range(100):
            acc = (acc + i * 7) & 0xFFFFFF
        c = ct.get_cpu_time_elapsed()


class Player:
    def __init__(self):
        self.err = []

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:  # noqa: BLE001
            self.err.append("%s:%s" % (type(exc).__name__, str(exc)[:50]))

    def _run(self, ct: Controller) -> None:
        r = ct.get_current_round()
        is_core = ct.get_entity_type() is EntityType.CORE

        # Spawn first (cheap, before any burning) so the unit count grows fast.
        if is_core and ct.get_unit_count() < TARGET_UNITS:
            here = ct.get_position()
            for d in DIRECTIONS:
                try:
                    p = here.add(d)
                    if ct.can_spawn(p):
                        ct.spawn_builder(p)
                        break
                except Exception:  # noqa: BLE001
                    continue

        if r >= 2:
            burn(ct, BURN_US)

        if is_core and r >= STOP_ROUND:
            ct.resign("cpushare units=%d round=%d cpu=%d err=%s"
                      % (ct.get_unit_count(), r, ct.get_cpu_time_elapsed(), ";".join(self.err[:4])))
