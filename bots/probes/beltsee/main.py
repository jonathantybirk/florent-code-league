"""Is a CONVEYOR's DIRECTION observable -- on our own belts, and on the ENEMY's?

Lucas's run-length idea only works if direction is a thing a scout can SEE. The API table lists
get_direction() as "(turrets)"; conveyors and splitters also carry a facing, but nothing says a
foreign one can be read. If it cannot, a belt has to be described by its GEOMETRY (where it runs)
rather than by (start, dir, len), which changes the encoding entirely.

  B1  Build a 4-tile EAST belt with our own builder. Read get_direction() on each belt id.
  B2  Read get_entity_type() / get_hp() on those same ids from the CORE (a different unit).
  B3  Same three calls against every ENEMY building the Core or a scout can see.
  B4  get_stored_resource() on a foreign conveyor -- does cargo leak too?
"""

from fcode import Controller, Direction, EntityType, Position

S_DONE = 0


def cls(fn):
    try:
        v = fn()
        return "ok:" + str(v)[:18]
    except Exception as exc:
        return type(exc).__name__[:9]


class Player:
    def __init__(self):
        self.n = []
        self.done = False
        self.built = []
        self.step = 0
        self.spawned = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.n.append("TOP:%s:%s" % (type(exc).__name__, str(exc)[:40]))

    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.BUILDER_BOT:
            self._builder(ct)
        elif et == EntityType.CORE:
            self._core(ct)

    def _builder(self, ct):
        if self.step >= 4:
            return
        p = ct.get_position()
        tgt = Position(p.x + 1, p.y)
        try:
            if ct.can_build_conveyor(tgt, Direction.EAST):
                ct.build_conveyor(tgt, Direction.EAST)
                self.step += 1
                return
        except Exception:
            pass
        try:
            if ct.can_move(Direction.EAST):
                ct.move(Direction.EAST)
        except Exception:
            pass

    def _core(self, ct):
        if self.done:
            return
        r = ct.get_current_round()
        if r <= 1 and not self.spawned:
            for q in ct.get_nearby_tiles(2):
                try:
                    if ct.can_spawn(q):
                        ct.spawn_builder(q)
                        self.spawned = True
                        break
                except Exception:
                    continue
            return

        if r < 25:
            return

        mine, theirs = [], []
        me = ct.get_team()
        for i in ct.get_nearby_buildings():
            try:
                t = ct.get_entity_type(i)
            except Exception:
                continue
            row = "%s#%d dir=%s hp=%s res=%s" % (
                str(t).split(".")[-1][:8], i,
                cls(lambda i=i: ct.get_direction(i)),
                cls(lambda i=i: ct.get_hp(i)),
                cls(lambda i=i: ct.get_stored_resource(i)))
            try:
                (mine if ct.get_team(i) == me else theirs).append(row)
            except Exception:
                theirs.append("teamfail " + row)

        self.n.append("OURS[%d]: %s" % (len(mine), " ; ".join(mine[:6])))
        self.n.append("THEIRS[%d]: %s" % (len(theirs), " ; ".join(theirs[:6])))
        self.done = True
        ct.resign(" | ".join(self.n))
