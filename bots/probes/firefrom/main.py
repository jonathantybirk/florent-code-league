"""Can a Builder PLAN the sentinel ring before it arrives?  can_fire_from() at range, and out of vision.

If can_fire_from(pos, dir, SENTINEL, target) answers for tiles the caller cannot see, the rusher can
compute all four firing slots at round 0 from the symmetry-derived enemy Core and walk straight to
them.  If it raises "Position out of vision range", the geometry has to be hand-rolled and confirmed
on arrival.

  F1  Does get_tile_env raise on a far tile?  (baseline for what "out of vision" costs)
  F2  can_fire_from with BOTH pos and target far away and unseen.
  F3  can_fire_from against our own Core (visible) -- does it refuse friendly fire?
  F4  Sanity: for a target 3 tiles east, which (offset, direction) pairs report True?
"""

from fcode import Controller, Direction, EntityType, Position

DIRS = (Direction.NORTH, Direction.SOUTH, Direction.EAST, Direction.WEST,
        Direction.NORTHEAST, Direction.NORTHWEST, Direction.SOUTHEAST, Direction.SOUTHWEST)


def cls(fn):
    try:
        return "ok:%s" % fn()
    except Exception as exc:
        return type(exc).__name__[:9]


class Player:
    def __init__(self):
        self.done = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            if not self.done:
                self.done = True
                ct.resign("TOP:%s:%s" % (type(exc).__name__, str(exc)[:60]))

    def _run(self, ct):
        if self.done or ct.get_entity_type() != EntityType.CORE:
            return
        if ct.get_current_round() < 1:
            return
        self.done = True
        p = ct.get_position()
        w, h = ct.get_map_width(), ct.get_map_height()
        far = Position(w - 2 - p.x, h - 2 - p.y)          # symmetry-derived enemy Core
        far_slot = Position(far.x - 3, far.y)
        n = []
        n.append("own=(%d,%d) derived_enemy=(%d,%d)" % (p.x, p.y, far.x, far.y))
        n.append("F1 env(far)=%s  env(near)=%s" % (
            cls(lambda: ct.get_tile_env(far)), cls(lambda: ct.get_tile_env(Position(p.x + 3, p.y)))))
        n.append("F2 fire_from(far_slot,E,SENT,far_core)=%s" % cls(
            lambda: ct.can_fire_from(far_slot, Direction.EAST, EntityType.SENTINEL, far)))
        n.append("F3 fire_from(near,E,SENT,OWN core)=%s" % cls(
            lambda: ct.can_fire_from(Position(p.x - 3, p.y), Direction.EAST, EntityType.SENTINEL, p)))
        # F4: which offsets/directions claim a hit on a tile 3 east of our core's NW corner
        tgt = Position(p.x, p.y)
        hits = []
        for dx in range(-5, 6):
            for dy in range(-5, 6):
                if dx * dx + dy * dy > 32 or (dx == 0 and dy == 0):
                    continue
                s = Position(p.x + dx, p.y + dy)
                for d in DIRS:
                    try:
                        if ct.can_fire_from(s, d, EntityType.SENTINEL, tgt):
                            hits.append((dx, dy, str(d).split(".")[-1][:2]))
                    except Exception:
                        pass
        n.append("F4 slots_hitting_own_core_NW=%d  sample=%s" % (len(hits), hits[:10]))
        ct.resign(" | ".join(n))
