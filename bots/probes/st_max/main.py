"""How large does an ENTITY ID get?  The packing budget for an (owner_id, round) lease word.

The lease word is `(owner_id + 1) << 10 | round`, so it overflows a u32 once `owner_id` passes
4 194 302.  Ids are handed out sequentially to every entity ever created -- units, buildings, and
every individual titanium resource -- so the question is the CHURN RATE, not the unit cap.

This probe drives the churn as hard as the economy allows: three builders each build and destroy a
barrier every round (a build mints a fresh id, a destroy frees the tile but never recycles the id).
The Core reports the highest id it has ever seen in vision, and the ids-per-round rate, so the
1000-round worst case can be extrapolated.  Arena `scal`.
"""

from fcode import Controller, Direction, EntityType, Position

S_MAX = 0
LAST = 300
CHURN_EVERY = 1     # 1 = churn flat out; >1 = just SAMPLE the global id counter


class Player:
    def __init__(self):
        self.done = False
        self.maxid = 0
        self.first = None
        self.built = None

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception:
            pass

    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            self._core(ct)
        elif et == EntityType.BUILDER_BOT:
            self._churn(ct)

    def _core(self, ct):
        if self.done:
            return
        r = ct.get_current_round()
        if r <= 2:
            p = ct.get_position()
            for dx, dy in ((2, 0), (2, 1), (0, -1), (1, -1), (-1, 0), (-1, 1), (0, 2), (1, 2)):
                q = Position(p.x + dx, p.y + dy)
                try:
                    if ct.can_spawn(q):
                        ct.spawn_builder(q)
                        break
                except Exception:
                    continue
            return

        for i in ct.get_nearby_entities():
            if i > self.maxid:
                self.maxid = i
        if r == 10:
            self.first = self.maxid
        if r == LAST:
            span = LAST - 10
            rate = (self.maxid - (self.first or 0)) / float(span)
            self.done = True
            ct.resign("STMAX|r10=%d r%d=%d rate=%.2f/round proj1000=%d ti=%d bcost=%d" % (
                self.first or 0, LAST, self.maxid, rate,
                int(self.maxid + rate * (1000 - LAST)),
                ct.get_global_resources(), ct.get_barrier_cost()))

    def _churn(self, ct):
        if ct.get_current_round() % CHURN_EVERY:
            return
        pos = ct.get_position()
        if self.built is not None:
            try:
                ct.destroy(self.built)
            except Exception:
                pass
            self.built = None
        for d in (Direction.EAST, Direction.NORTH, Direction.SOUTH, Direction.WEST):
            q = pos.add(d)
            try:
                if ct.can_build_barrier(q):
                    ct.build_barrier(q)
                    self.built = q
                    return
            except Exception:
                continue
