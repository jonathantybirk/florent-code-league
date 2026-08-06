"""Does module-body (import-time) CPU count against the first turn's budget?

40 ms is burned at module scope, then every round runs the same API-polled loop vcut3 uses. If
import CPU were charged to round 0, round 0 would be cut at ~0 chunks. If it is outside the budget,
round 0 is cut at the same ~509 chunks as every other round.
"""

import time

from fcode import Controller, EntityType

CHUNK = 500
CHUNKS = 6000
STOP = 8

_t0 = time.process_time()
_acc = 0
while (time.process_time() - _t0) < 0.040:
    for _i in range(1000):
        _acc = (_acc + _i * 7) & 0xFFFFFF
MODULE_US = int((time.process_time() - _t0) * 1e6)


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
            print("VCUT6|prev=%d|chunks=%d|fin=%d|module_us=%d"
                  % (self.cur[0], self.cur[1], self.cur[2], MODULE_US))
            self.cur = None

        if r >= STOP:
            msg = ("VCUT6 module_us=%d n=%d finished=%d chunks=%s err=%s"
                   % (MODULE_US, len(self.rows), sum(x[2] for x in self.rows),
                      [x[1] for x in self.rows], ";".join(self.err[:3])))
            print("SUMMARY|" + msg)
            ct.resign(msg)
            return

        row = [r, 0, 0]
        self.cur = row

        acc = 0
        for c in range(CHUNKS):
            for i in range(CHUNK):
                acc = (acc + i * 7) & 0xFFFFFF
            row[1] = c + 1
            ct.get_current_round()
        row[2] = 1
