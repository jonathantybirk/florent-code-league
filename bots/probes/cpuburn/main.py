"""Task 1.5 -- find the real per-unit CPU budget by burning wall-clock time.

The Core burns an escalating amount of wall-clock time each round with a busy loop, then issues
one observable action (convert_ammo(1)). The NEXT round it checks whether global ammo actually
went up. If the engine truncates a unit's turn at a threshold, the post-burn action is voided and
the check fails -- that is the signal.

Also microbenchmarks the operations a real bot spends its round on, so a budget expressed in
milliseconds converts into a usable "how many of X per round" number.

Reports through resign() -- print() does not reach the result dict.

Schedule (round -> target burn, ms):
  0,1        warm-up, no burn
  2..        BURNS list, one per round
  then       microbenchmarks, then resign
"""

import time

from fcode import Controller, EntityType

BURNS = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 5.0, 8.0, 9.5, 10.0, 10.5,
         12.0, 15.0, 20.0, 30.0, 50.0, 100.0, 200.0, 500.0, 1000.0]

WARMUP = 2


def burn_ms(target_ms):
    """Busy-loop until target_ms of wall clock has elapsed. Returns actual ms burned."""
    t0 = time.perf_counter()
    if target_ms <= 0:
        return 0.0
    limit = target_ms / 1000.0
    acc = 0
    while True:
        # a chunk of real work so the loop cannot be optimised into a sleep
        for i in range(200):
            acc = (acc + i * 7) & 0xFFFFFF
        if time.perf_counter() - t0 >= limit:
            break
    return (time.perf_counter() - t0) * 1000.0


class Player:
    def __init__(self):
        self.rows = []          # (target_ms, actual_ms, landed)
        self.pending = None     # (target, actual, ammo_before)
        self.bench = []
        self.cpu_seen = set()
        self.err = []
        self.done = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:  # noqa: BLE001
            self.err.append("%s:%s" % (type(exc).__name__, str(exc)[:60]))

    # ------------------------------------------------------------------
    def _run(self, ct: Controller) -> None:
        if ct.get_entity_type() is not EntityType.CORE:
            return
        r = ct.get_current_round()

        # resolve the previous round's experiment first
        if self.pending is not None:
            tgt, act, before = self.pending
            landed = ct.get_global_ammo() > before
            self.rows.append((tgt, act, landed))
            self.pending = None

        idx = r - WARMUP
        if idx < 0:
            return

        if idx < len(BURNS):
            tgt = BURNS[idx]
            actual = burn_ms(tgt)
            self.cpu_seen.add(ct.get_cpu_time_elapsed())
            before = ct.get_global_ammo()
            try:
                if ct.can_convert_ammo(1):
                    ct.convert_ammo(1)
                    self.pending = (tgt, actual, before)
                else:
                    self.rows.append((tgt, actual, None))
            except Exception as exc:  # noqa: BLE001
                self.err.append("cv@%.1f %s" % (tgt, type(exc).__name__))
            return

        if not self.done:
            self.done = True
            self._benchmark(ct)
            ct.resign(self._report(ct))

    # ------------------------------------------------------------------
    def _benchmark(self, ct: Controller) -> None:
        def timeit(label, fn, n):
            t0 = time.perf_counter_ns()
            for _ in range(n):
                fn()
            dt = time.perf_counter_ns() - t0
            per_us = dt / n / 1000.0
            # how many fit in 1 ms and in 10 ms
            self.bench.append("%s=%.3fus(%d/ms)" % (label, per_us, int(1000.0 / per_us) if per_us else -1))

        acc = [0]

        def pyloop():
            a = 0
            for i in range(1000):
                a += i
            acc[0] = a

        timeit("py1k_add", pyloop, 200)
        timeit("get_position", lambda: ct.get_position(), 2000)
        timeit("get_current_round", lambda: ct.get_current_round(), 5000)
        timeit("is_tile_passable", lambda: ct.is_tile_passable(ct.get_position()), 2000)
        timeit("get_nearby_tiles", lambda: ct.get_nearby_tiles(), 200)
        timeit("get_nearby_entities", lambda: ct.get_nearby_entities(), 500)
        timeit("get_tile_env", lambda: ct.get_tile_env(ct.get_position()), 2000)
        timeit("read_store", lambda: ct.read_store(0), 5000)
        timeit("get_hp", lambda: ct.get_hp(), 2000)

    # ------------------------------------------------------------------
    def _report(self, ct: Controller) -> str:
        parts = []
        ok = [t for (t, a, l) in self.rows if l is True]
        bad = [(t, a) for (t, a, l) in self.rows if l is False]
        na = [t for (t, a, l) in self.rows if l is None]
        parts.append("BURNS n=%d landed=%d voided=%d na=%d" % (len(self.rows), len(ok), len(bad), len(na)))
        parts.append("maxlanded=%.1fms" % (max(ok) if ok else -1))
        if bad:
            parts.append("VOIDED_AT=" + ",".join("%.1f" % t for t, _ in bad))
        # accuracy of the burn: target vs actual
        parts.append("burn_acc=" + ";".join("%.1f/%.2f" % (t, a) for (t, a, _) in self.rows[:6]))
        parts.append("burn_hi=" + ";".join("%.0f/%.1f" % (t, a) for (t, a, _) in self.rows if t >= 10))
        parts.append("cpu_us_values=%s" % sorted(self.cpu_seen))
        parts.append("alive_hp=%d/%d round=%d units=%d" % (ct.get_hp(), ct.get_max_hp(),
                                                           ct.get_current_round(), ct.get_unit_count()))
        parts.append("BENCH " + " ".join(self.bench))
        if self.err:
            parts.append("ERR " + ";".join(self.err[:6]))
        return " | ".join(parts)
