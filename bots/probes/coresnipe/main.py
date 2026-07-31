"""The decisive strategic probe for 2.3.3: can a forward Gunner kill an enemy Core using
ONLY Core-converted ammo -- no harvester, no conveyor, no ore anywhere on the map?

Under 2.2.0 a forward Gunner had to be sited orthogonally adjacent to ore so a Harvester could
feed it (that is what `bot/siege.py` ranks firing positions on). If ammo is global, that
constraint is meaningless and the only requirement is line-of-fire.

Arena `close` (14x11, NO ORE AT ALL). Enemy Core B footprint is {(8,5),(9,5),(8,6),(9,6)}.
Our builder builds a Gunner at (5,5) facing EAST; (8,5) is 3 tiles away, d^2=9 <= 13.
The Core converts 120 titanium into 120 ammo (60 shots x 10 dmg = 600 > CORE_MAX_HP 500).
"""

from fcode import Controller, Direction, EntityType, GameError, Position

HOME = Position(4, 5)
GUN = Position(5, 5)


class Player:
    def __init__(self):
        self.spawned = False
        self.built = False
        self.converted = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception:
            pass

    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            if not self.spawned:
                if ct.can_spawn(Position(3, 5)):
                    ct.spawn_builder(Position(3, 5))
                    self.spawned = True
                return
            if not self.converted and ct.can_convert_ammo(120):
                ct.convert_ammo(120)
                self.converted = True
            return

        if et == EntityType.BUILDER_BOT:
            if self.built:
                return
            pos = ct.get_position()
            if pos != HOME:
                d = pos.cardinal_direction_to(HOME)
                if ct.can_move(d):
                    ct.move(d)
                return
            if ct.can_build_gunner(GUN, Direction.EAST):
                ct.build_gunner(GUN, Direction.EAST)
                self.built = True
            return

        if et == EntityType.GUNNER:
            t = ct.get_gunner_target()
            if t is not None and ct.can_fire(t):
                ct.fire(t)
