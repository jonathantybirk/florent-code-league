"""Independent re-derivation of the per-unit CPU cut-off (verification of the 10 ms claim).

Design goal: nothing inside the bot may terminate the burn. The loop runs a FIXED number of
chunks of pure-Python arithmetic and never consults ct.get_cpu_time_elapsed(), so the only thing
that can stop it is the engine. `chunks` records how far it got.

That gives a budget measurement that does not trust the replay's execTimeUs at all:
  * a tle=0 run completes the loop and reports the total CPU it cost -> microseconds per chunk
  * a tle=N run is cut after K chunks -> budget ~= K * (us per chunk)
Compare K across N to see whether the cut scales with turn_timeout_ms.

Phase A (rounds 2..11): burn every round, so any banked spare time stays drained.
Phase B (rounds 12..31): burn only on even rounds; the idle odd rounds should refill the
documented 5% bank, so the cut on a phase-B round should land later if banking is real.

Prints go out at the TOP of the round, describing the PREVIOUS round, so a cut can never eat the
report. resign() carries the summary for the Windows path.
"""

from fcode import Controller, EntityType

CHUNK = 500          # pure-python adds per chunk
CHUNKS = 6000        # total chunks: far more work than any plausible budget
PHASE_A_END = 12
PHASE_B_END = 32
STOP = 33


class Player:
    def __init__(self):
        self.rows = []          # [round, chunks, acted, finished, cpu_at_entry, cpu_at_end]
        self.cur = None
        self.err = []

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:  # noqa: BLE001
            self.err.append("%s:%s" % (type(exc).__name__, str(exc)[:30]))

    def _run(self, ct: Controller) -> None:
        if ct.get_entity_type() is not EntityType.CORE:
            return
        r = ct.get_current_round()

        if self.cur is not None:
            self.rows.append(self.cur)
            print("VCUT|prev=%d|chunks=%d|acted=%d|fin=%d|entry_cpu=%d|end_cpu=%d|ammo_now=%d"
                  % (self.cur[0], self.cur[1], self.cur[2], self.cur[3], self.cur[4],
                     self.cur[5], ct.get_global_ammo()))
            self.cur = None

        if r >= STOP:
            self._resign(ct)
            return
        if r < 2:
            return

        burn = (r < PHASE_A_END) or (r < PHASE_B_END and r % 2 == 0)
        if not burn:
            return

        entry_cpu = ct.get_cpu_time_elapsed()

        acted = 0
        try:
            if ct.can_convert_ammo(1):
                ct.convert_ammo(1)
                acted = 1
        except Exception:  # noqa: BLE001
            self.err.append("cv")

        row = [r, 0, acted, 0, entry_cpu, 0]
        self.cur = row

        acc = 0
        for c in range(CHUNKS):
            for i in range(CHUNK):
                acc = (acc + i * 7) & 0xFFFFFF
            row[1] = c + 1
        row[3] = 1
        row[5] = ct.get_cpu_time_elapsed()

    def _resign(self, ct):
        a = [x for x in self.rows if x[0] < PHASE_A_END]
        b = [x for x in self.rows if x[0] >= PHASE_A_END]
        fin = [x for x in self.rows if x[3]]

        def brief(rs):
            return ",".join("%d:%d%s" % (x[0], x[1], "F" if x[3] else "") for x in rs)

        msg = ("VCUT n=%d finished=%d ammo=%d entry_cpu=%s | A=[%s] | B=[%s] | "
               "full_cost_us=%s | err=%s") % (
            len(self.rows), len(fin), ct.get_global_ammo(),
            sorted(set(x[4] for x in self.rows))[:4], brief(a), brief(b),
            [x[5] for x in fin][:4], ";".join(self.err[:3]))
        print("SUMMARY|" + msg)
        ct.resign(msg)
