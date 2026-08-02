"""Opponent for the AREA-1 defensive-launcher probes.

Spawns up to CAP builder bots and marches every one of them at the enemy Core
by a greedy axis walk. No economy, no combat -- a pure stream of attackers, so
that a defensive Launcher's throughput can be counted against a known arrival
rate. Prints its own roster each round as 'LP|M ...'.
"""

from fcode import Controller, Direction, EntityType, GameError, Position

CAP = 8
GOAL = Position(3, 6)
SPAWN = Position(21, 5)


class Player:
    def __init__(self):
        self.n = 0

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            print("LP|M TOP %s" % type(exc).__name__)

    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            if self.n >= CAP:
                return
            for p in (SPAWN, Position(21, 8), Position(20, 5), Position(20, 8)):
                if ct.can_spawn(p):
                    ct.spawn_builder(p)
                    self.n += 1
                    return
            return
        if et != EntityType.BUILDER_BOT:
            return
        pos = ct.get_position()
        print("LP|M r%d id%d at %s,%s hp%d" % (
            ct.get_current_round(), ct.get_id(), pos.x, pos.y, ct.get_hp()))
        dx = GOAL.x - pos.x
        dy = GOAL.y - pos.y
        opts = []
        if abs(dx) >= abs(dy):
            if dx:
                opts.append(Direction.WEST if dx < 0 else Direction.EAST)
            if dy:
                opts.append(Direction.NORTH if dy < 0 else Direction.SOUTH)
        else:
            if dy:
                opts.append(Direction.NORTH if dy < 0 else Direction.SOUTH)
            if dx:
                opts.append(Direction.WEST if dx < 0 else Direction.EAST)
        opts += [Direction.NORTH, Direction.SOUTH, Direction.WEST, Direction.EAST]
        for d in opts:
            if ct.can_move(d):
                ct.move(d)
                return
