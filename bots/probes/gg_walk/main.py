"""AREA 1 / GobbleGlitch probe: WALKING control for gg_ferry, on `sweden`.

Same builder, same goal (a tile orthogonally adjacent to the enemy Core
footprint at (0,13)), no Launcher: it walks the only land route, round the
wall band through the gap at x=17..19.  BFS says that is 43 steps.
"""

from fcode import Controller, Direction, EntityType, GameError, Position

GOAL = Position(1, 12)
EFOOT = [(0, 13), (1, 13), (0, 14), (1, 14)]
WAY = [Position(2, 2), Position(18, 2), Position(18, 12), Position(1, 12)]


def en(exc):
    return type(exc).__name__ + ":" + str(exc)[:24]


class Player:
    def __init__(self):
        self.spawned = False
        self.wi = 0
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
        if self.wi < len(WAY):
            w = WAY[self.wi]
            if pos == w:
                self.wi += 1
                if self.wi >= len(WAY):
                    return
                w = WAY[self.wi]
            self._step(ct, pos, w)

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
