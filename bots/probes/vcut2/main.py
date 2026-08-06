"""Can a unit act AFTER blowing the CPU budget, if its burn loop never touches the API?

vcut showed a 110 ms API-free burn is not interrupted at turn_timeout_ms=10. The question that
decides whether the budget binds in practice: once over budget, does the first Controller call
still work, and does the action it issues actually land?

Round layout: burn BURN_CHUNKS with no API calls at all, then call a read API, then convert_ammo.
The next round reports whether each stage was reached and whether global ammo actually rose.
"""

from fcode import Controller, EntityType

CHUNK = 500
BURN_CHUNKS = 3000          # ~55 ms on this machine: 5x the 10 ms budget
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
            row = self.cur
            row[6] = 1 if ct.get_global_ammo() > row[5] else 0
            self.rows.append(row)
            print("VCUT2|prev=%d|chunks=%d|api_ok=%d|acted=%d|cpu_after=%d|ammo_rose=%d|ammo_now=%d"
                  % (row[0], row[1], row[2], row[3], row[4], row[6], ct.get_global_ammo()))
            self.cur = None

        if r >= STOP:
            landed = sum(x[6] for x in self.rows)
            msg = ("VCUT2 n=%d api_ok=%d acted=%d ammo_rose=%d ammo=%d chunks=%s cpu_after=%s err=%s"
                   % (len(self.rows), sum(x[2] for x in self.rows), sum(x[3] for x in self.rows),
                      landed, ct.get_global_ammo(), sorted(set(x[1] for x in self.rows)),
                      sorted(set(x[4] for x in self.rows))[:5], ";".join(self.err[:3])))
            print("SUMMARY|" + msg)
            ct.resign(msg)
            return
        if r < 2:
            return

        # [round, chunks, api_ok, acted, cpu_after, ammo_before, ammo_rose]
        row = [r, 0, 0, 0, -1, ct.get_global_ammo(), 0]
        self.cur = row

        acc = 0
        for c in range(BURN_CHUNKS):
            for i in range(CHUNK):
                acc = (acc + i * 7) & 0xFFFFFF
            row[1] = c + 1

        row[4] = ct.get_cpu_time_elapsed()      # first API touch after the overrun
        row[2] = 1
        try:
            if ct.can_convert_ammo(1):
                ct.convert_ammo(1)
                row[3] = 1
            else:
                self.err.append("cannot_convert")
        except Exception as exc:  # noqa: BLE001
            self.err.append("cv:%s" % type(exc).__name__)
