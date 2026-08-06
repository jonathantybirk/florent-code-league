"""Task 1.5 -- when a unit is cut off by the CPU limit, is the work it already did kept?

Each round the Core acts FIRST (convert_ammo(1)) and only then burns far past the limit. If actions
issued before the cut-off survive, global ammo rises by one every round even though every round is
flagged tled. If the engine instead voids the whole turn, ammo never moves.

Python state is checked too: self.tick is incremented before the burn, so if the sub-interpreter were
reset each time the counter would not advance.

Prints happen at the TOP of the round, before any burning, so the report is never lost.
"""

import time

from fcode import Controller, EntityType

BURN_US = 50000
WARMUP = 2
STOP_ROUND = 12


def burn(ct, target_us):
    acc = 0
    c = ct.get_cpu_time_elapsed()
    if c == 0:
        t0 = time.perf_counter()
        while (time.perf_counter() - t0) * 1e6 < target_us:
            for i in range(200):
                acc = (acc + i * 7) & 0xFFFFFF
        return -1
    while c < target_us:
        for i in range(100):
            acc = (acc + i * 7) & 0xFFFFFF
        c = ct.get_cpu_time_elapsed()
    return c


class Player:
    def __init__(self):
        self.tick = 0
        self.acted = 0
        self.reached = []
        self.err = []

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:  # noqa: BLE001
            self.err.append("%s:%s" % (type(exc).__name__, str(exc)[:40]))

    def _run(self, ct: Controller) -> None:
        if ct.get_entity_type() is not EntityType.CORE:
            return
        r = ct.get_current_round()

        print("KEEP|round=%d|ammo=%d|tick=%d|acted=%d|reached=%s|err=%s"
              % (r, ct.get_global_ammo(), self.tick, self.acted, self.reached[-3:], self.err[:2]))

        if r < WARMUP:
            return
        if r >= STOP_ROUND:
            ct.resign("cpukeep ammo=%d tick=%d acted=%d reached=%s err=%s"
                      % (ct.get_global_ammo(), self.tick, self.acted, self.reached[-4:], self.err[:2]))
            return

        self.tick += 1
        try:
            if ct.can_convert_ammo(1):
                ct.convert_ammo(1)
                self.acted += 1
        except Exception as exc:  # noqa: BLE001
            self.err.append("cv:%s" % type(exc).__name__)

        self.reached.append(burn(ct, BURN_US))   # never reached if the engine cuts us off
