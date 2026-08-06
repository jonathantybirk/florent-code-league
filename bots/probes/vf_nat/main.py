"""How long is the role ACTUALLY vacant when the owner is killed by a RIVAL rather than by
self_destruct()?

st_hb and vf_lease both kill the owner on a fixed round with self_destruct().  That is a
cooperative suicide taken during the unit's own turn, with a full pool of healthy challengers
standing by.  The number it produces (2 vacant rounds) is the BEST case.  Under fire the challenge
winner can itself be dead before it confirms, and then the whole 2-round cycle repeats.

This probe removes every scheduled kill.  The Core keeps a pool of builders topped up, the role is
"march east into the enemy", and every owner dies for real.  It reports the full HISTOGRAM of
vacancy lengths, not just the mean, plus the two direct alarms (a living unit that skipped a turn,
and an owner evicted while alive).

Slots as in vf_lease; S_SKIP/S_EVICT are the alarms, 8..15 are the per-builder concurrency reports.
"""

from fcode import Controller, Direction, EntityType, Position

S_LEASE, S_ACTED, S_SKIP, S_SKIPN, S_EVICT, S_ALIVE, S_ECHO, S_MAXID = range(8)
S_REP = 8

STALE = 2
POOL = 9              # builders the Core tries to keep alive
LAST = 400


def pack(uid, r):
    return ((uid + 1) << 10) | r


class Player:
    def __init__(self):
        self.n = []
        self.done = False
        self.owner = False
        self.prev = None
        self.skips = 0
        self.acted = []
        self.last_ar = -1
        self.nown = 0
        self.last_ow = -1
        self.hist = {}
        self.maxconc = 0
        self.spawned = 0

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.n.append("TOP:" + type(exc).__name__ + ":" + str(exc)[:25])

    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            self._core(ct)
        elif et == EntityType.BUILDER_BOT:
            self._builder(ct)

    def _core(self, ct):
        if self.done:
            return
        r = ct.get_current_round()

        if ct.get_unit_count() < POOL + 1:
            self._spawn(ct)

        w = ct.read_store(S_ACTED)
        if w:
            ar, ow = w & 1023, (w >> 10) - 1
            if ar != self.last_ar:
                if self.last_ar >= 0 and ar - self.last_ar > 1:
                    g = ar - self.last_ar - 1
                    self.hist[g] = self.hist.get(g, 0) + 1
                self.acted.append(ar)
                self.last_ar = ar
                if ow != self.last_ow:
                    self.nown += 1
                    self.last_ow = ow

        c = sum(1 for i in range(8) if ct.read_store(S_REP + i) == r - 1)
        if c > self.maxconc:
            self.maxconc = c

        if r == LAST or ct.get_hp() < 170:
            sk, ev = ct.read_store(S_SKIP), ct.read_store(S_EVICT)
            hh = sorted(self.hist.items())
            self.n.append("end=%d spawned=%d acts=%d span=%s..%s" % (
                r, self.spawned, len(self.acted),
                self.acted[0] if self.acted else -1, self.acted[-1] if self.acted else -1))
            self.n.append("owners=%d vac=%s" % (
                self.nown, ",".join("%dr:x%d" % (g, c) for g, c in hh) or "NONE"))
            self.n.append("vacrounds=%d" % sum(g * c for g, c in hh))
            self.n.append("A1 skip=%s(u%d,r%d)" % (
                "YES" if sk else "none", (sk >> 10) - 1 if sk else 0, sk & 1023))
            self.n.append("A2 evict=%s(u%d,r%d)" % (
                "YES" if ev else "none", (ev >> 10) - 1 if ev else 0, ev & 1023))
            self.n.append("conc=%d stale=%d pool=%d" % (self.maxconc, STALE, POOL))
            self.done = True
            ct.resign("VFN|" + "|".join(self.n))

    def _spawn(self, ct):
        p = ct.get_position()
        for dx, dy in ((2, 0), (2, 1), (0, -1), (1, -1), (-1, 0), (-1, 1),
                       (0, 2), (1, 2), (2, 2), (-1, -1), (2, -1), (-1, 2)):
            q = Position(p.x + dx, p.y + dy)
            try:
                if ct.can_spawn(q):
                    ct.spawn_builder(q)
                    self.spawned += 1
                    return
            except Exception:
                continue

    def _builder(self, ct):
        r = ct.get_current_round()
        mine = ct.get_id()

        if self.prev is not None and r - self.prev > 1:
            self.skips += 1
            try:
                if ct.read_store(S_SKIP) == 0:
                    ct.write_store(S_SKIP, pack(mine, r))
            except Exception:
                pass
        self.prev = r

        raw = ct.read_store(S_LEASE)
        stamp = raw & 1023
        held = (raw >> 10) - 1
        fresh = raw != 0 and (r - stamp) < STALE

        if raw and held == mine:
            self.owner = True
        elif fresh:
            if self.owner:
                try:
                    if ct.read_store(S_EVICT) == 0:
                        ct.write_store(S_EVICT, pack(mine, r))
                except Exception:
                    pass
            self.owner = False

        if self.owner:
            ct.write_store(S_LEASE, pack(mine, r))
            ct.write_store(S_ACTED, pack(mine, r))
            ct.write_store(S_REP + (mine % 8), r)
            try:
                if ct.can_move(Direction.EAST):
                    ct.move(Direction.EAST)
            except Exception:
                pass
            return

        if not fresh:
            ct.write_store(S_LEASE, pack(mine, r))
