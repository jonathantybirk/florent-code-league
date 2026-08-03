"""NN-1: which clocks survive inside the sandbox, and is the module body per-unit?

Reports from the CORE via resign(). Cross-unit facts travel through the store:
  slot 10  number of units that have run at least once
  slot 11  max len(SHARED) any unit observed  -> >1 means the module object is
           shared between units; ==1 means each unit re-execs the module body
  slot 12  module-body elapsed, microseconds (whatever clock works), x1000
"""

import os
import time

from fcode import Controller, EntityType, Position

# --- module-level: a mutable that would be shared iff the module object is shared
SHARED = []

# --- module-level: probe every clock the sandbox might have left alive
CLOCKS = {}
for _name in ("time", "monotonic", "perf_counter", "process_time", "thread_time"):
    _f = getattr(time, _name, None)
    CLOCKS[_name] = _f() if _f else "absent"
for _name in ("time_ns", "monotonic_ns", "perf_counter_ns", "process_time_ns",
              "thread_time_ns"):
    _f = getattr(time, _name, None)
    CLOCKS[_name] = _f() if _f else "absent"

OS_TIMES = "absent"
if hasattr(os, "times"):
    OS_TIMES = tuple(round(v, 6) for v in os.times())

# does a busy loop advance any of them?
_t0 = {k: v for k, v in CLOCKS.items()}
_acc = 0
for _i in range(200000):
    _acc += _i * 3
ADVANCED = []
for _name in list(CLOCKS):
    _f = getattr(time, _name, None)
    if _f is None:
        continue
    _v = _f()
    if _v != _t0[_name]:
        ADVANCED.append("%s+%s" % (_name, _v - _t0[_name]))
if hasattr(os, "times"):
    _ot = os.times()
    if OS_TIMES != "absent" and _ot[0] != OS_TIMES[0]:
        ADVANCED.append("os.times.user+%.6f" % (_ot[0] - OS_TIMES[0]))

MOD_TOKEN = id(SHARED) & 0xFFFFFF


class Player:
    def __init__(self):
        self.first = True
        self.notes = []

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.notes.append("E:" + type(exc).__name__ + ":" + str(exc)[:40])

    def _run(self, ct):
        rnd = ct.get_current_round()
        et = ct.get_entity_type()

        if self.first:
            self.first = False
            SHARED.append(ct.get_id())
            ct.write_store(10, ct.read_store(10) + 1)
            seen = ct.read_store(11)
            if len(SHARED) > seen:
                ct.write_store(11, len(SHARED))

        if et == EntityType.CORE:
            if rnd < 6:
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1)):
                    p = Position(ct.get_position().x + dx, ct.get_position().y + dy)
                    if ct.can_spawn(p):
                        ct.spawn_builder(p)
                        break
            if rnd == 12:
                out = []
                out.append("advanced=" + (";".join(ADVANCED) if ADVANCED else "NONE"))
                out.append("cpu_us=%s" % ct.get_cpu_time_elapsed())
                out.append("units_run=%s len_SHARED_max=%s my_len=%s"
                           % (ct.read_store(10), ct.read_store(11), len(SHARED)))
                out.append("unit_count=%s tok=%s" % (ct.get_unit_count(), MOD_TOKEN))
                out.append("notes=%s" % (self.notes,))
                ct.resign("|".join(out)[:499])
