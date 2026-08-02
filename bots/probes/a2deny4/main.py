"""ECON Q2/Q7: how much titanium does a DEAD-END parasite chain swallow before it jams?

`a2deny` (one conveyor, dead-ending into bare ground) cost the victim exactly one 10-Ti
stack. If a dead-end belt jams at one stack per conveyor, a chain of N should swallow
N x 10 Ti and then be skipped by the harvester's round-robin forever.

Arena `maps/lab/para.map26` (18x11), opponent `a2econ` (Core B (13,5), harvester (8,5),
belt (9,5)(10,5)(11,5)(12,5) EAST into Core tile (13,5)).

We take ONE of the harvester's free neighbours, (8,6), and hang a 4-long southward
dead-end off it:  (8,6)S -> (8,7)S -> (8,8)S -> (8,9)S -> bare ground (8,10).
12 Ti of conveyor. Read `b_titanium_collected` against the 2470 baseline
(`noop` vs `a2econ`): the shortfall is what the dead end swallowed.

Reports the stack ids resting on each of the four conveyors at round 995.
"""

from fcode import Controller, Direction, EntityType, GameError, Position

S = Direction.SOUTH
# (stand, build) -- build the head last so the belt is complete before it is fed
PLAN = (
    ((7, 9), (8, 9)),
    ((7, 8), (8, 8)),
    ((7, 7), (8, 7)),
    ((7, 6), (8, 6)),
)
BELT = (Position(8, 6), Position(8, 7), Position(8, 8), Position(8, 9))


class Player:
    def __init__(self):
        self.spawned = False
        self.i = 0
        self.done_round = None
        self.note = ""

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.note = type(exc).__name__[:6] + ":" + str(exc)[:18]

    def _walk(self, ct, me, goal):
        gx, gy = goal
        d = None
        if me.y != gy:
            d = Direction.SOUTH if gy > me.y else Direction.NORTH
            if not ct.can_move(d):
                d = Direction.EAST if gx > me.x else Direction.WEST
        elif me.x != gx:
            d = Direction.EAST if gx > me.x else Direction.WEST
        if d is not None and ct.can_move(d):
            ct.move(d)

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()
        if et == EntityType.CORE:
            if not self.spawned and ct.can_spawn(Position(3, 7)):
                ct.spawn_builder(Position(3, 7))
                self.spawned = True
            return
        if et != EntityType.BUILDER_BOT:
            return

        me = ct.get_position()
        if self.i < len(PLAN):
            stand, build = PLAN[self.i]
            if (me.x, me.y) != stand:
                self._walk(ct, me, stand)
                return
            tgt = Position(build[0], build[1])
            if ct.can_build_conveyor(tgt, S):
                ct.build_conveyor(tgt, S)
                self.i += 1
                if self.i == len(PLAN):
                    self.done_round = r
            elif ct.get_tile_building_id(tgt) is not None:
                self.i += 1
            return

        if r == 995:
            ids = []
            for p in BELT:
                b = ct.get_tile_building_id(p)
                ids.append("-" if b is None else str(ct.get_stored_resource_id(b)))
            ct.resign(("DENY4 built=%s belt(8,6..9)=%s %s" % (
                self.done_round, ",".join(ids), self.note))[:495])
