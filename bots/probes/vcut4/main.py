"""Is the deadline checked on ANY Python function call, or only on a Controller API call?

vcut  (no calls at all in the loop)            -> ran 110 ms uncut at turn_timeout_ms=10
vcut3 (ct.get_current_round() per chunk)       -> cut at ~509 chunks (~10 ms)
vcut4 (a pure-Python no-op call per chunk)     -> this probe

If vcut4 is cut like vcut3, the check rides on the interpreter's call path and any ordinary bot is
fully pre-empted. If vcut4 runs to completion like vcut, only Controller entry points check.
"""

from fcode import Controller, EntityType

CHUNK = 500
CHUNKS = 6000
STOP = 13


def nop(x):
    return x


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
            print("VCUT4|prev=%d|chunks=%d|fin=%d" % (self.cur[0], self.cur[1], self.cur[2]))
            self.cur = None

        if r >= STOP:
            msg = ("VCUT4 n=%d finished=%d chunks=%s err=%s"
                   % (len(self.rows), sum(x[2] for x in self.rows),
                      [x[1] for x in self.rows], ";".join(self.err[:3])))
            print("SUMMARY|" + msg)
            ct.resign(msg)
            return
        if r < 2:
            return

        row = [r, 0, 0]
        self.cur = row

        acc = 0
        for c in range(CHUNKS):
            for i in range(CHUNK):
                acc = (acc + i * 7) & 0xFFFFFF
            row[1] = c + 1
            acc = nop(acc)                  # ordinary Python call, no Controller involved
        row[2] = 1
