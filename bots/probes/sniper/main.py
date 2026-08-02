"""AREA-2 attacker: the G57 core-snipe, reduced to its skeleton, on arena `lane` (20x11).

Core B anchor (16,5).  Builder spawns on (15,5), walks WEST to (6,5), builds a Gunner on (5,5)
facing WEST.  Gunner reach is 3 tiles along the facing -> (4,5)(3,5)(2,5); (2,5) is a Core A
footprint tile.  The Core converts 300 Ti to ammo up front (150 Gunner shots = 1500 damage,
three times what a 500 HP Core needs), so ammo is never the limiting factor.

The Gunner uses get_gunner_target(), i.e. it shoots whatever is nearest in its ray -- exactly the
behaviour a real bot has, and exactly what a shield has to survive.
"""

from fcode import Controller, Direction, EntityType, GameError, Position

GUN = Position(5, 5)
STAND = Position(6, 5)


class Player:
    def __init__(self):
        self.spawned = False
        self.converted = False
        self.built = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception:
            return

    def _run(self, ct):
        et = ct.get_entity_type()

        if et == EntityType.CORE:
            if not self.spawned:
                if ct.can_spawn(Position(15, 5)):
                    ct.spawn_builder(Position(15, 5))
                    self.spawned = True
                return
            if not self.converted and ct.can_convert_ammo(300):
                ct.convert_ammo(300)
                self.converted = True
            return

        if et == EntityType.BUILDER_BOT:
            if self.built:
                return
            me = ct.get_position()
            if me.x == STAND.x and me.y == STAND.y:
                if ct.can_build_gunner(GUN, Direction.WEST):
                    ct.build_gunner(GUN, Direction.WEST)
                    self.built = True
                return
            if ct.can_move(Direction.WEST):
                ct.move(Direction.WEST)
            return

        if et == EntityType.GUNNER:
            t = ct.get_gunner_target()
            if t is not None and ct.can_fire(t):
                ct.fire(t)
            return
