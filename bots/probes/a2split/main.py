"""ECON Q6: what does a SPLITTER actually do with its three outputs?

`gg_belt2` showed a splitter with two of its three output sides on BARE GROUND delivers
exactly as much as a conveyor (2490) -- so empty sides cost nothing. This probe gives the
splitter three real buildings to choose between and watches the round-robin.

Arena `maps/lab/belt.map26` (20x12): Core A anchor (1,5), ore (5,5).

    harvester (5,5)
    splitter  (4,5) facing WEST
    conveyor  (3,5) WEST -> Core tile (2,5)      [the only route that scores]
    conveyor  (4,4) NORTH -> (4,3) bare ground   [dead end, jams after one stack]
    conveyor  (4,6) SOUTH -> (4,7) bare ground   [dead end, jams after one stack]

If the splitter round-robins blindly across all three, roughly one stack in three reaches
the Core and `a_titanium_collected` lands near 830. If it skips full/jammed destinations,
it loses exactly two stacks (2470) and a splitter is simply a 6-Ti conveyor.

Counts, per dead end, how many DISTINCT stack ids ever rested on it, and reports at r995.
"""

from fcode import Controller, Direction, EntityType, GameError, Position

HARV = Position(5, 5)
SPL = Position(4, 5)
TAIL = Position(3, 5)
UP = Position(4, 4)
DOWN = Position(4, 6)

STEPS = (
    (5, 4, "harv", HARV, None),
    (3, 4, "conv", TAIL, Direction.WEST),
    (4, 4, "spl", SPL, Direction.WEST),
    (3, 4, "conv", UP, Direction.NORTH),
    (5, 6, "conv", DOWN, Direction.SOUTH),
)
PARK = (5, 7)


class Player:
    def __init__(self):
        self.spawned = False
        self.i = 0
        self.done = None
        self.up_ids = 0
        self.dn_ids = 0
        self.up_prev = None
        self.dn_prev = None
        self.note = ""

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.note = type(exc).__name__[:6] + ":" + str(exc)[:18]

    def _walk(self, ct, me, gx, gy):
        order = []
        if me.y != gy:
            order.append(Direction.SOUTH if gy > me.y else Direction.NORTH)
        if me.x != gx:
            order.append(Direction.EAST if gx > me.x else Direction.WEST)
        for d in order:
            if ct.can_move(d):
                ct.move(d)
                return

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()
        if et == EntityType.CORE:
            if not self.spawned and ct.can_spawn(Position(3, 4)):
                ct.spawn_builder(Position(3, 4))
                self.spawned = True
            return
        if et != EntityType.BUILDER_BOT:
            return

        me = ct.get_position()
        if self.i < len(STEPS):
            sx, sy, kind, tgt, face = STEPS[self.i]
            if (me.x, me.y) != (sx, sy):
                self._walk(ct, me, sx, sy)
                return
            ok = False
            if kind == "harv" and ct.can_build_harvester(tgt):
                ct.build_harvester(tgt)
                ok = True
            elif kind == "conv" and ct.can_build_conveyor(tgt, face):
                ct.build_conveyor(tgt, face)
                ok = True
            elif kind == "spl" and ct.can_build_splitter(tgt, face):
                ct.build_splitter(tgt, face)
                ok = True
            if ok:
                self.i += 1
                if self.i == len(STEPS):
                    self.done = r
            elif ct.get_tile_building_id(tgt) is not None:
                self.i += 1
            return

        if (me.x, me.y) != PARK:
            self._walk(ct, me, PARK[0], PARK[1])
            return

        self.up_prev, self.up_ids = self._count(ct, UP, self.up_prev, self.up_ids)
        self.dn_prev, self.dn_ids = self._count(ct, DOWN, self.dn_prev, self.dn_ids)

        if r == 995:
            ct.resign(("SPLIT built=%s up_stacks=%d dn_stacks=%d now up=%s dn=%s tail=%s %s"
                       % (self.done, self.up_ids, self.dn_ids,
                          self._id(ct, UP), self._id(ct, DOWN), self._id(ct, TAIL),
                          self.note))[:495])

    def _id(self, ct, p):
        b = ct.get_tile_building_id(p)
        if b is None:
            return "-"
        return str(ct.get_stored_resource_id(b))

    def _count(self, ct, p, prev, n):
        b = ct.get_tile_building_id(p)
        cur = None if b is None else ct.get_stored_resource_id(b)
        if cur is not None and cur != prev:
            n += 1
        return cur, n
