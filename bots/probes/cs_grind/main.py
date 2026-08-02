"""Attacker half of the cross-team attrition test.  Pair with `cs_victim`.

    runfull cs_grind --map lab/cstiny --vs cs_victim

Core A anchor is (1,4) on `lab/cstiny`.  A Builder Bot spawns at (3,4) and immediately builds a
GUNNER at (4,4) facing EAST; the Core converts 20 titanium into ammunition.  The gunner's ray runs
(5,4) empty -> (6,4), which is where cs_victim puts its barrier, so the barrier is destroyed by an
entity belonging to the OTHER team.  This bot never resigns, so the result dict carries
cs_victim's message.
"""

from fcode import Controller, Direction, EntityType, GameError, Position

SPAWN = Position(3, 4)
GUN = Position(4, 4)


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
            if not self.spawned and ct.can_spawn(SPAWN):
                ct.spawn_builder(SPAWN)
                self.spawned = True
            if ct.get_global_ammo() < 20 and ct.can_convert_ammo(20):
                ct.convert_ammo(20)
            return

        if et == EntityType.GUNNER:
            tgt = ct.get_gunner_target()
            if tgt is not None and ct.can_fire(tgt):
                ct.fire(tgt)
            return

        if et != EntityType.BUILDER_BOT or self.built:
            return
        if ct.can_build_gunner(GUN, Direction.EAST):
            ct.build_gunner(GUN, Direction.EAST)
            self.built = True
