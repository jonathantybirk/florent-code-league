"""AREA-2 / G43: the DEAD-END parasite -- pure denial for one 3-Ti conveyor.

No trunk, no route home: a single conveyor at (8,6), orthogonally adjacent to the enemy
harvester at (8,5), facing WEST into bare ground at (7,6).

Two possible outcomes, both interesting:
  * the conveyor dumps its stack onto empty ground and the titanium is annihilated
    -> 3 Ti permanently deletes half of a 20-Ti harvester, the cheapest attack in the game;
  * the conveyor fills and jams after one stack
    -> the denial is worth exactly 10 Ti and the harvester round-robins past it thereafter.

The builder walks to (8,7), builds, then retreats west so it cannot be blamed for anything.

MEASURED 2026-08-02, fcode 2.3.3, `maps/lab/para.map26` vs `a2econ`:
    b_titanium_collected = 2460   (baseline `noop` vs `a2econ` = 2470)   a_collected = 0
REFUTED as an attack. One dead-end conveyor swallows exactly ONE 10-Ti stack and then jams
permanently; the harvester's round-robin skips a full building from then on, so 3 Ti buys
10 Ti of denial, once. `a2deny4` (a 4-long dead end) loses the victim 40 Ti and `a2loop`
(a closed 4-conveyor cycle) also loses exactly 40 -- a cycle does NOT circulate, capacity
is one stack per conveyor and then deadlock. Only a parasite that DRAINS keeps stealing:
see `a2para` / `a2para2` / `a2para3`.
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
            if ct.can_build_conveyor(tgt, Direction.WEST):
                ct.build_conveyor(tgt, Direction.WEST)
                self.built = True
            return
        if me.x > 3 and ct.can_move(Direction.WEST):
            ct.move(Direction.WEST)
