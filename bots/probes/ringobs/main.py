"""Q3/Q4/Q8 defender: does a bricked ring actually stop the Core spawning?

Phase 1 (rounds 0..SPAWN_FROM-1): completely passive.  Nothing this bot does may close one of its
own ring tiles, so every closure observed is the attacker's work.  Samples, every 20 rounds, how
many of its own ring tiles still return can_spawn and how many hold a building.

Phase 2 (rounds SPAWN_FROM..REPORT): tries spawn_builder on every ring tile, every round, and
counts what gets through.  Spawned builders are told to sit, so they also occupy ring tiles: this
is the partial-denial measurement -- with k tiles bricked, how many bodies can the Core emit
before it jams itself?  The exact GameError text of a refused spawn is captured once.

Also asks, at both phase boundaries, whether ANY tile in the 8x8 block around the anchor outside
the 12-tile ring has become spawnable ("does it spawn further out?"), and reports get_unit_count()
so a trapped unit can be checked against the 50-unit cap.

Reported by the CORE (M07) through resign (G29/M06) at round REPORT.
"""

from fcode import Controller, EntityType, GameError, Position

FOOT = ((0, 0), (1, 0), (0, 1), (1, 1))
SPAWN_FROM = 120
REPORT = 200


class Player:
    def __init__(self):
        self.n = []
        self.ring = None
        self.wide = None
        self.locked = -1
        self.ok_hist = []
        self.spawn_ok = 0
        self.spawn_fail = 0
        self.err = ""
        self.wide_hits = 0

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.n.append("TOP:" + type(exc).__name__)

    def _run(self, ct):
        if ct.get_entity_type() != EntityType.CORE:
            return
        r = ct.get_current_round()
        a = ct.get_position()
        w, h = ct.get_map_width(), ct.get_map_height()

        if self.ring is None:
            self.ring = []
            self.wide = []
            for dy in range(-3, 5):
                for dx in range(-3, 5):
                    x, y = a.x + dx, a.y + dy
                    if not (0 <= x < w and 0 <= y < h):
                        continue
                    inner = -1 <= dx <= 2 and -1 <= dy <= 2
                    if inner and (dx, dy) in FOOT:
                        continue
                    (self.ring if inner else self.wide).append(Position(x, y))
            self.n.append("ring=%d" % len(self.ring))

        ok = 0
        occ = 0
        for t in self.ring:
            try:
                if ct.can_spawn(t):
                    ok += 1
                if ct.get_tile_building_id(t) is not None:
                    occ += 1
            except GameError:
                continue
        if ok == 0 and self.locked < 0:
            self.locked = r
        if r % 20 == 0 and r <= REPORT:
            self.ok_hist.append("%d:%d/%d" % (r, ok, occ))

        if r in (SPAWN_FROM - 1, REPORT - 1):
            n = 0
            for t in self.wide:
                try:
                    if ct.can_spawn(t):
                        n += 1
                except GameError:
                    continue
            self.wide_hits += n
            self.n.append("wide@%d=%d/%d" % (r, n, len(self.wide)))

        if SPAWN_FROM <= r < REPORT:
            for t in self.ring:
                try:
                    if ct.can_spawn(t):
                        ct.spawn_builder(t)
                        self.spawn_ok += 1
                        return
                except GameError:
                    continue
            # nothing was spawnable: take the raw error off the first ring tile, once
            if not self.err:
                try:
                    ct.spawn_builder(self.ring[0])
                except Exception as exc:
                    self.err = str(exc)[:24]
            self.spawn_fail += 1

        if r == REPORT:
            self.n.append("hist[%s]" % " ".join(self.ok_hist))
            self.n.append("LOCK=%d spOK=%d spFAIL=%d err=%s uc=%d ti=%d hp=%d" % (
                self.locked, self.spawn_ok, self.spawn_fail, self.err or "-",
                ct.get_unit_count(), ct.get_global_resources(), ct.get_hp()))
            ct.resign(("OBS|" + " ".join(self.n))[:495])
