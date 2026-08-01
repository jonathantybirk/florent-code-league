"""Probe: builder walk cadence + build cadence, reported via the resign message."""

from fcode import Controller, Direction, EntityType, Position


class Player:
    def __init__(self):
        self.n = 0
        self.trace = []
        self.spawned = False
        self.is_core = None

    def run(self, ct: Controller) -> None:
        try:
            et = ct.get_entity_type()
        except Exception:
            return
        if et == EntityType.CORE:
            if not self.spawned:
                p = ct.get_position()
                for d in (Direction.SOUTH, Direction.EAST, Direction.NORTH, Direction.WEST):
                    q = p.add(d)
                    try:
                        if ct.can_spawn(q):
                            ct.spawn_builder(q)
                            self.spawned = True
                            break
                    except Exception:
                        continue
            return
        if et != EntityType.BUILDER_BOT:
            return
        self.n += 1
        p = ct.get_position()
        try:
            mcd = ct.get_move_cooldown()
            acd = ct.get_action_cooldown()
        except Exception:
            mcd = acd = -1
        moved = 0
        try:
            if ct.can_move(Direction.EAST):
                ct.move(Direction.EAST)
                moved = 1
        except Exception:
            moved = -1
        self.trace.append("%d:%d,%d m%d a%d mv%d" % (self.n, p.x, p.y, mcd, acd, moved))
        if self.n == 14:
            try:
                ct.resign("|".join(self.trace))
            except Exception:
                ct.resign()
