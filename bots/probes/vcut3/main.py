"""Where is the CPU deadline actually checked? Variant: the burn loop calls a trivial Controller
API (ct.get_current_round()) once per chunk.

vcut (same loop, zero API calls inside it) ran 110 ms per round to completion at turn_timeout_ms=10.
If this variant is cut instead, the deadline is polled at Controller API boundaries, not pre-empted.

`chunks` is how far the loop got. With the microseconds-per-chunk figure from a tle=0 run, chunks
converts straight into the enforced budget without trusting execTimeUs.
"""

from fcode import Controller, EntityType

CHUNK = 500
CHUNKS = 6000
STOP = 13


class Player:
    def __init__(self):
        self.rows = []
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
            print("VCUT3|prev=%d|chunks=%d|acted=%d|fin=%d|ammo_now=%d"
                  % (self.cur[0], self.cur[1], self.cur[2], self.cur[3], ct.get_global_ammo()))
            self.cur = None

        if r >= STOP:
            fin = [x for x in self.rows if x[3]]
            msg = ("VCUT3 n=%d finished=%d ammo=%d chunks=%s full_cost_us=%s err=%s"
                   % (len(self.rows), len(fin), ct.get_global_ammo(),
                      [x[1] for x in self.rows], [x[4] for x in fin][:3],
                      ";".join(self.err[:3])))
            print("SUMMARY|" + msg)
            ct.resign(msg)
            return
        if r < 2:
            return

        acted = 0
        try:
            if ct.can_convert_ammo(1):
                ct.convert_ammo(1)
                acted = 1
        except Exception:  # noqa: BLE001
            self.err.append("cv")

        row = [r, 0, acted, 0, 0]
        self.cur = row

        acc = 0
        for c in range(CHUNKS):
            for i in range(CHUNK):
                acc = (acc + i * 7) & 0xFFFFFF
            row[1] = c + 1
            ct.get_current_round()          # the only difference from vcut
        row[3] = 1
        row[4] = ct.get_cpu_time_elapsed()
