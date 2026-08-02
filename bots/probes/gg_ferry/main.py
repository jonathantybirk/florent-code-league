"""AREA 1 / GobbleGlitch probe: the LAUNCHER FERRY on `sweden`.

sweden (25x15) puts both Cores on the left edge -- ours at (0,0), theirs at
(0,13) -- with a three-row wall band across rows 6,7,8 whose only gap is at
x=17..19.  Manhattan distance 13, walking distance 43 (G64).

A Launcher throw is a disc of d^2<=26 that ARCS over walls (G48).  The band is
three rows thick, so one throw crosses it:

    builder stands (4,5), builds a LAUNCHER at (5,5)          [1 round, 20 Ti]
    next round the Launcher throws the builder (4,5) -> (5,9) [d^2 = 16]
    the builder walks (5,9) -> (1,12), adjacent to their Core

Control: bots/probes/gg_walk walks the same trip the long way round.

Reports the round on which the builder first stands orthogonally adjacent to the
enemy Core footprint.
"""

from fcode import Controller, Direction, EntityType, GameError, Position

LAUNCH_FROM = Position(4, 5)
LPOS = Position(5, 5)
LAND = Position(5, 9)
GOAL = Position(1, 12)
EFOOT = [(0, 13), (1, 13), (0, 14), (1, 14)]
WAY = [Position(2, 2), Position(4, 2), Position(4, 5)]


def en(exc):
    return type(exc).__name__ + ":" + str(exc)[:24]


class Player:
    def __init__(self):
        self.spawned = False
        self.wi = 0
        self.built = False
        self.arrived = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            print("LP|TOP %s" % en(exc))

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()
        if et == EntityType.CORE:
            if not self.spawned and ct.can_spawn(Position(2, 2)):
                ct.spawn_builder(Position(2, 2))
                self.spawned = True
            return
        if et == EntityType.LAUNCHER:
            bid = ct.get_tile_builder_bot_id(LAUNCH_FROM)
            if bid is None:
                return
            if ct.can_launch(LAUNCH_FROM, LAND):
                ct.launch(LAUNCH_FROM, LAND)
                print("LP|r%d FERRY %d,%d -> %d,%d" % (
                    r, LAUNCH_FROM.x, LAUNCH_FROM.y, LAND.x, LAND.y))
            else:
                print("LP|r%d FERRY ILLEGAL" % r)
            return
        if et != EntityType.BUILDER_BOT:
            return
        pos = ct.get_position()
        if not self.arrived:
            for (fx, fy) in EFOOT:
                if abs(pos.x - fx) + abs(pos.y - fy) == 1:
                    print("LP|r%d ARRIVED at %d,%d" % (r, pos.x, pos.y))
                    self.arrived = True
                    return
        if self.arrived:
            return
        if not self.built:
            if pos == LAUNCH_FROM:
                if ct.can_build_launcher(LPOS):
                    print("LP|r%d LAUNCHER id=%d" % (r, ct.build_launcher(LPOS)))
                    self.built = True
                return
            if self.wi < len(WAY):
                w = WAY[self.wi]
                if pos == w:
                    self.wi += 1
                    if self.wi >= len(WAY):
                        return
                    w = WAY[self.wi]
                self._step(ct, pos, w)
            return
        if pos.y < 6:
            return           # waiting to be thrown
        self._step(ct, pos, GOAL)

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
