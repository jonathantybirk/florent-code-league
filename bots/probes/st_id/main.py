"""Can a unit tell whether a NAMED TEAMMATE is still alive?  And who wins a many-way slot collision?

Two questions that decide the shape of any role-claim protocol.

  C1  LIVENESS BY ID.  The Core names one builder in the store, that builder walks east one tile a
      round publishing its own x, and the Core calls get_hp(id) on it every round.  If the call
      starts raising while the builder is still demonstrably alive (its x keeps advancing), then
      "is the claimant alive?" CANNOT be answered by an id lookup -- vision gates it -- and the
      liveness signal has to be carried in the store itself.  The roamer self_destructs on round 40
      so we also see what a genuinely dead id looks like.
  C2  COLLISION, FOUR WRITERS.  On round 12 the Core (id 1) and every builder write their OWN id
      into slot 5.  If the survivor is always max(id), the rule is "highest entity id wins",
      i.e. units act in ascending id order and the last write of the round is the one that lands.
  C3  MAX ENTITY ID seen over the match -- the packing budget for an (id, round) pair in one u32.

Arena `scal` (24x20, our Core anchored at x=1, 22 tiles of clear walking room east).
"""

from fcode import Controller, Direction, EntityType, Position

S_ROAM = 0      # id of the builder that walks (0 = not chosen yet)
S_X = 1         # roamer's x + 1, republished every round
S_COLL = 5      # C2 collision slot
KILL_ROUND = 40
LAST = 46


class Player:
    def __init__(self):
        self.n = []
        self.done = False
        self.roam = None
        self.first_fail = None
        self.last_ok = None
        self.maxid = 0
        self.after_death = None

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.n.append("TOP:" + type(exc).__name__ + ":" + str(exc)[:30])

    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            self._core(ct)
        elif et == EntityType.BUILDER_BOT:
            self._builder(ct)

    # ---------------------------------------------------------------------- core
    def _core(self, ct):
        if self.done:
            return
        r = ct.get_current_round()

        if r <= 3:
            self._spawn(ct)
            return

        if r == 5:
            ids = [i for i in ct.get_nearby_units()
                   if ct.get_team(i) == ct.get_team() and i != ct.get_id()]
            ids.sort()
            self.n.append("ids=%s" % ids)
            if ids:
                self.roam = ids[0]
                ct.write_store(S_ROAM, self.roam)
            return

        if self.roam is None:
            return

        for i in ct.get_nearby_units():
            if i > self.maxid:
                self.maxid = i

        if 6 <= r <= LAST:
            x = ct.read_store(S_X) - 1
            try:
                hp = ct.get_hp(self.roam)
                self.last_ok = (r, x, hp)
                ok = True
            except Exception as exc:
                ok = False
                if self.first_fail is None:
                    self.first_fail = (r, x, type(exc).__name__[:4])
            if r == KILL_ROUND + 2 and not ok:
                self.after_death = (r, x)

        if r == 13:
            self.n.append("C2 collide=%d" % ct.read_store(S_COLL))
            return

        if r == LAST:
            self.n.append("C1 roam=%d lastok=%s firstfail=%s" % (
                self.roam, self.last_ok, self.first_fail))
            self.n.append("C1 xAtKill=%d maxid=%d" % (ct.read_store(S_X) - 1, self.maxid))
            self.done = True
            ct.resign("STID|" + "|".join(self.n))

    def _spawn(self, ct):
        p = ct.get_position()
        for dx, dy in ((2, 0), (2, 1), (0, -1), (1, -1), (-1, 0), (-1, 1), (0, 2), (1, 2)):
            q = Position(p.x + dx, p.y + dy)
            try:
                if ct.can_spawn(q):
                    ct.spawn_builder(q)
                    return
            except Exception:
                continue

    # ------------------------------------------------------------------- builder
    def _builder(self, ct):
        r = ct.get_current_round()
        mine = ct.get_id()

        if r == 12:
            ct.write_store(S_COLL, mine)        # C2: every unit writes its own id
            return

        if ct.read_store(S_ROAM) != mine:
            return

        if r == KILL_ROUND:
            ct.self_destruct()
            return
        pos = ct.get_position()
        ct.write_store(S_X, pos.x + 1)
        try:
            if ct.can_move(Direction.EAST):
                ct.move(Direction.EAST)
        except Exception:
            pass
