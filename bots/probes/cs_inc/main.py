"""The definitive INCREMENT + REFUND table: build one of every entity type, read the scale, then
remove it and read the scale again -- in the SAME round, because destroy() does not consume the
action cooldown.

Arena `lab/cslab` (csopen plus an ore tile at (5,5) so the harvester can be built without walking).
The reporting Builder Bot parks at (5,6):

    (5,5) ORE  -> harvester
    (4,6)      -> conveyor, splitter, barrier, gunner, sentinel, launcher, one per round
    builder bot increment comes from the Core spawning a second builder, which then
    self_destruct()s; the reporter reads the scale on both sides.

Every row is  <type> +<increment> -<refund>  so a non-symmetric refund would be visible
immediately.
"""

from fcode import Controller, Direction, EntityType, GameError, Position

HOME = Position(5, 6)
ORE = Position(5, 5)
SLOT = Position(4, 6)
SPAWN1 = Position(3, 6)
SPAWN2 = Position(3, 7)
N = Direction.NORTH
E = Direction.EAST


def e(exc):
    return type(exc).__name__[:4] + ":" + str(exc)[:18]


class Player:
    def __init__(self):
        self.n = []
        self.role = None
        self.done = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.n.append("!" + e(exc))

    def cycle(self, ct, tag, place, target):
        s0 = ct.get_scale_percent()
        try:
            place()
        except Exception as exc:
            self.n.append(tag + "!" + e(exc))
            return
        s1 = ct.get_scale_percent()
        try:
            ct.destroy(target)
            s2 = ct.get_scale_percent()
        except Exception as exc:
            self.n.append("%s+%.0f-!%s" % (tag, s1 - s0, e(exc)))
            return
        self.n.append("%s+%.0f-%.0f" % (tag, s1 - s0, s1 - s2))

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()

        if et == EntityType.CORE:
            if r == 0 and ct.can_spawn(SPAWN1):
                ct.spawn_builder(SPAWN1)
            if r == 20 and ct.can_spawn(SPAWN2):
                ct.spawn_builder(SPAWN2)
            return

        if et != EntityType.BUILDER_BOT or self.done:
            return
        if self.role is None:
            self.role = "rep" if r <= 2 else "sui"
        if self.role == "sui":
            if r >= 22:
                ct.self_destruct()
            return

        pos = ct.get_position()
        if pos.x != HOME.x or pos.y != HOME.y:
            d = pos.cardinal_direction_to(HOME)
            if ct.can_move(d):
                ct.move(d)
            return

        if r == 3:
            self.n.append("base=%.0f" % ct.get_scale_percent())
            self.cycle(ct, "cv", lambda: ct.build_conveyor(SLOT, E), SLOT)
        elif r == 4:
            self.cycle(ct, "sp", lambda: ct.build_splitter(SLOT, E), SLOT)
        elif r == 5:
            self.cycle(ct, "br", lambda: ct.build_barrier(SLOT), SLOT)
        elif r == 6:
            self.cycle(ct, "gn", lambda: ct.build_gunner(SLOT, N), SLOT)
        elif r == 7:
            self.cycle(ct, "st", lambda: ct.build_sentinel(SLOT, N), SLOT)
        elif r == 8:
            self.cycle(ct, "lu", lambda: ct.build_launcher(SLOT), SLOT)
        elif r == 9:
            self.cycle(ct, "hv", lambda: ct.build_harvester(ORE), ORE)
        elif r == 21:
            self.n.append("bbLIVE=%.0f u=%d" % (ct.get_scale_percent(), ct.get_unit_count()))
        elif r == 24:
            self.n.append("bbSD=%.0f u=%d" % (ct.get_scale_percent(), ct.get_unit_count()))
        elif r == 26:
            self.done = True
            ct.resign(("CSINC " + " ".join(self.n))[:495])
