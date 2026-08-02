"""AREA-2 / G43: does a BARRIER count as an adjacent building for a Harvester's round-robin?

If it does, a 3-Ti barrier planted next to an enemy Harvester eats a share of every cycle and
annihilates it -- permanent denial with no belt, no drain and no maintenance.  If it does not,
the round-robin is conveyor/splitter-only and denial always requires a real drain.

One barrier at (8,6), orthogonally adjacent to the enemy harvester at (8,5).
Control for this arena: b_titanium_collected = 2470.
"""

from fcode import Controller, Direction, EntityType, GameError, Position


class Player:
    def __init__(self):
        self.spawned = False
        self.built = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception:
            return

    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            if not self.spawned and ct.can_spawn(Position(3, 7)):
                ct.spawn_builder(Position(3, 7))
                self.spawned = True
            return
        if et != EntityType.BUILDER_BOT:
            return

        me = ct.get_position()
        if not self.built:
            if (me.x, me.y) != (8, 7):
                d = Direction.EAST if me.x < 8 else Direction.WEST
                if ct.can_move(d):
                    ct.move(d)
                return
            tgt = Position(8, 6)
            if ct.can_build_barrier(tgt):
                ct.build_barrier(tgt)
                self.built = True
            return
        if me.x > 3 and ct.can_move(Direction.WEST):
            ct.move(Direction.WEST)
