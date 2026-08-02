"""AREA 1 / GobbleGlitch probe: REWIND THROUGHPUT -- one Launcher versus eight
attackers, and an API check on get_nearby_units().

Arena `glopen` (26x14, no terrain).  Our Core anchor (1,6).  gl_march sends
eight Builder Bots at us and parks them on our doorstep.

  LAUNCHER at (5,6).  Every round it throws one enemy Builder Bot out of its
  8-tile pickup ring to the legal target furthest from our Core (a rewind of
  4-5 tiles, which costs the victim 4-5 rounds of walking to undo).

Every round it reports:
   ring = enemy builders inside the pickup ring (throwable now)
   core = enemy builders orthogonally adjacent to our Core footprint (the ones
          actually able to hurt us)
Run with SET_LAUNCHER=False for the control (identical bot, no launcher).

Also: our parked Builder Bot prints the entity type of every id returned by
get_nearby_units(), to check whether that API really returns only units.
"""

from fcode import Controller, Direction, EntityType, GameError, Position

SET_LAUNCHER = False
SPAWN = Position(3, 6)
LPOS = Position(5, 6)
LSTAND = Position(5, 5)
PARK = Position(4, 4)
ANCHOR = Position(1, 6)
FOOT = [(1, 6), (2, 6), (1, 7), (2, 7)]
RING2 = [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)]


def en(exc):
    return type(exc).__name__ + ":" + str(exc)[:24]


def d2(a, b):
    return (a.x - b.x) ** 2 + (a.y - b.y) ** 2


class Player:
    def __init__(self):
        self.spawned = False
        self.stage = 0
        self.throws = 0
        self.said = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            print("LP|TOP %s" % en(exc))

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()
        if et == EntityType.CORE:
            if not self.spawned and ct.can_spawn(SPAWN):
                ct.spawn_builder(SPAWN)
                self.spawned = True
            return
        if et == EntityType.BUILDER_BOT:
            self._builder(ct, r)
            return
        if et == EntityType.LAUNCHER:
            self._launcher(ct, r)
            return

    def _builder(self, ct, r):
        pos = ct.get_position()
        if SET_LAUNCHER and self.stage == 0:
            if pos != LSTAND:
                self._step(ct, pos, LSTAND)
                return
            if ct.can_build_launcher(LPOS):
                print("LP|r%d LAUNCHER id=%d" % (r, ct.build_launcher(LPOS)))
                self.stage = 1
            return
        if pos != PARK:
            self._step(ct, pos, PARK)
            return
        ring, near = self._census(ct, r)
        if r <= 150:
            print("LP|r%d CENSUS ring=%d core=%d" % (r, len(ring), near))
        if not self.said:
            self.said = True
            out = []
            for uid in ct.get_nearby_units():
                out.append("%d:%s" % (uid, str(ct.get_entity_type(uid))[11:16]))
            print("LP|r%d NEARBY_UNITS %s" % (r, " ".join(out[:12])))
            out = []
            for uid in ct.get_nearby_buildings():
                out.append("%d:%s" % (uid, str(ct.get_entity_type(uid))[11:16]))
            print("LP|r%d NEARBY_BLDGS %s" % (r, " ".join(out[:12])))

    def _step(self, ct, pos, goal):
        dx = goal.x - pos.x
        dy = goal.y - pos.y
        opts = []
        if abs(dx) >= abs(dy):
            if dx:
                opts.append(Direction.EAST if dx > 0 else Direction.WEST)
            if dy:
                opts.append(Direction.SOUTH if dy > 0 else Direction.NORTH)
        else:
            if dy:
                opts.append(Direction.SOUTH if dy > 0 else Direction.NORTH)
            if dx:
                opts.append(Direction.EAST if dx > 0 else Direction.WEST)
        for d in opts:
            if ct.can_move(d):
                ct.move(d)
                return

    def _census(self, ct, r):
        me = ct.get_team()
        ring = []
        near = 0
        for uid in ct.get_nearby_units():
            if ct.get_team(uid) == me:
                continue
            if ct.get_entity_type(uid) != EntityType.BUILDER_BOT:
                continue
            q = ct.get_position(uid)
            for (fx, fy) in FOOT:
                if abs(q.x - fx) + abs(q.y - fy) == 1:
                    near += 1
                    break
            if d2(q, LPOS) <= 2:
                ring.append((uid, q))
        return ring, near

    def _launcher(self, ct, r):
        ring, near = self._census(ct, r)
        if r <= 150:
            print("LP|r%d ring=%d core=%d thr=%d" % (r, len(ring), near, self.throws))
        if not ring:
            return
        uid, src = ring[0]
        cands = []
        for dx in range(-5, 6):
            for dy in range(-5, 6):
                dd = dx * dx + dy * dy
                if dd < 16 or dd > 26:
                    continue
                q = Position(LPOS.x + dx, LPOS.y + dy)
                if q.x < 0 or q.y < 0:
                    continue
                cands.append((-d2(q, ANCHOR), q.x, q.y, q))
        cands.sort()
        tried = 0
        for _, _, _, q in cands:
            if tried >= 6:
                break
            tried += 1
            try:
                ok = ct.can_launch(src, q)
            except Exception:
                continue
            if ok:
                ct.launch(src, q)
                self.throws += 1
                print("LP|r%d REWIND id%d %d,%d -> %d,%d back=%d thr=%d" % (
                    r, uid, src.x, src.y, q.x, q.y,
                    abs(q.x - src.x) + abs(q.y - src.y), self.throws))
                return
