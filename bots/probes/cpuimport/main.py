"""Task 1.5 -- does time spent in the MODULE BODY count against the per-unit CPU limit?

Each unit re-executes this module in its own sub-interpreter, so a precompute placed at module level
runs once per unit. The question is whether the engine's per-turn clock is already running while it
does. Burn MODULE_BURN_MS of CPU at import time, then report round 0's execTimeUs from the replay:

  execTimeUs(round 0) ~= MODULE_BURN     -> module body is inside the budget
  execTimeUs(round 0) ~= a few hundred us -> module body is free
"""

import time

MODULE_BURN_MS = 40.0

_t0 = time.process_time()
_acc = 0
while (time.process_time() - _t0) * 1000.0 < MODULE_BURN_MS:
    for _i in range(500):
        _acc = (_acc + _i * 7) & 0xFFFFFF
MODULE_CPU_MS = (time.process_time() - _t0) * 1000.0

from fcode import Controller, EntityType  # noqa: E402


class Player:
    def run(self, ct: Controller) -> None:
        try:
            r = ct.get_current_round()
            print("IMP|round=%d|module_cpu_ms=%.2f|turn_cpu_us=%d|acc=%d"
                  % (r, MODULE_CPU_MS, ct.get_cpu_time_elapsed(), _acc))
            if ct.get_entity_type() is EntityType.CORE and r >= 4:
                ct.resign("cpuimport module_cpu_ms=%.2f turn_cpu_us=%d"
                          % (MODULE_CPU_MS, ct.get_cpu_time_elapsed()))
        except Exception:  # noqa: BLE001
            pass
