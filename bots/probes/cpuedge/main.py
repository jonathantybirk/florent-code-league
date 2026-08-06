"""Task 1.5 -- bracket the exact per-unit CPU limit and identify the penalty.

The Core burns CPU until ct.get_cpu_time_elapsed() reaches a target, then issues one observable
action (convert_ammo(1)). The NEXT round it checks whether global ammo actually rose. If the engine
voids everything a unit does after the limit, the action is silently lost -- that is the signal.

Reporting: on Linux print() reaches the replay as BotOutput.stdout, so every line is emitted at the
TOP of a round, BEFORE any burning, so the report itself can never be truncated by the limit.
resign() at the end carries a compact summary for the Windows path (where stdout is not recorded).

Round layout:
  0,1              warm-up
  2 + i            burn to TARGETS[i] us of CPU, then act
  after TARGETS    SLEEP_ROUNDS: time.sleep() instead of burning -- distinguishes a
                   wall-clock limit from a CPU-time limit
  final            resign (unburned round, so the resign cannot itself be voided)
"""

import time

from fcode import Controller, EntityType

TARGETS = [1000, 2000, 5000, 8000, 9000, 9500, 9800, 9900, 9950,
           10000, 10050, 10100, 10200, 10500, 11000, 12000, 20000, 50000]

SLEEPS = [0.05, 0.30]      # seconds of wall clock with (almost) no CPU
WARMUP = 2


class Player:
    def __init__(self):
        self.pending = None      # (label, cpu_at_action, ammo_before)
        self.rows = []           # (label, cpu_at_action, landed)
        self.entry_cpu = []
        self.stage = 0
        self.done = False
        self.err = []

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:  # noqa: BLE001
            self.err.append("%s:%s" % (type(exc).__name__, str(exc)[:50]))

    def _run(self, ct: Controller) -> None:
        if ct.get_entity_type() is not EntityType.CORE:
            return
        r = ct.get_current_round()

        # ---- report the PREVIOUS round's outcome first, before any burning ----
        if self.pending is not None:
            label, cpu_at, before = self.pending
            landed = ct.get_global_ammo() > before
            self.rows.append((label, cpu_at, landed))
            print("EDGE|%s|cpu_at_action=%d|landed=%d|ammo=%d" % (label, cpu_at, landed, ct.get_global_ammo()))
            self.pending = None

        idx = r - WARMUP
        if idx < 0:
            return

        self.entry_cpu.append(ct.get_cpu_time_elapsed())

        if idx < len(TARGETS):
            tgt = TARGETS[idx]
            cpu_at = self._burn_to(ct, tgt)
            self._act(ct, "burn%d" % tgt, cpu_at)
            return

        j = idx - len(TARGETS)
        if j < len(SLEEPS):
            s = SLEEPS[j]
            t0 = time.perf_counter()
            try:
                time.sleep(s)
            except Exception as exc:  # noqa: BLE001
                self.err.append("sleep:%s" % type(exc).__name__)
            wall = (time.perf_counter() - t0) * 1e6
            cpu_at = ct.get_cpu_time_elapsed()
            self._act(ct, "sleep%dms_wall%dus" % (int(s * 1000), int(wall)), cpu_at)
            return

        if not self.done:
            self.done = True
            ok = [lb for (lb, c, l) in self.rows if l]
            bad = [(lb, c) for (lb, c, l) in self.rows if not l]
            hi_ok = max([c for (lb, c, l) in self.rows if l] or [-1])
            lo_bad = min([c for (lb, c, l) in self.rows if not l] or [-1])
            msg = ("EDGE n=%d landed=%d voided=%d | max_cpu_landed=%d | min_cpu_voided=%d | "
                   "voided=%s | entry_cpu=%s | hp=%d units=%d | err=%s") % (
                len(self.rows), len(ok), len(bad), hi_ok, lo_bad,
                ",".join(lb for lb, _ in bad)[:220], sorted(set(self.entry_cpu))[:6],
                ct.get_hp(), ct.get_unit_count(), ";".join(self.err[:4]))
            print("SUMMARY|" + msg)
            ct.resign(msg)

    # ------------------------------------------------------------------
    def _burn_to(self, ct, target_us):
        """Busy-loop until the engine's own CPU clock reaches target_us. Returns that reading.

        On Windows get_cpu_time_elapsed() is stuck at 0, so fall back to perf_counter and treat
        target_us as wall microseconds; the returned value is then flagged negative.
        """
        acc = 0
        c = ct.get_cpu_time_elapsed()
        if c == 0:
            t0 = time.perf_counter()
            while (time.perf_counter() - t0) * 1e6 < target_us:
                for i in range(200):
                    acc = (acc + i * 7) & 0xFFFFFF
            return -int((time.perf_counter() - t0) * 1e6)
        while c < target_us:
            for i in range(100):
                acc = (acc + i * 7) & 0xFFFFFF
            c = ct.get_cpu_time_elapsed()
        return c

    def _act(self, ct, label, cpu_at):
        before = ct.get_global_ammo()
        try:
            if ct.can_convert_ammo(1):
                ct.convert_ammo(1)
                self.pending = (label, cpu_at, before)
            else:
                self.err.append("cannot_convert@" + label)
        except Exception as exc:  # noqa: BLE001
            self.err.append("%s@%s" % (type(exc).__name__, label))
