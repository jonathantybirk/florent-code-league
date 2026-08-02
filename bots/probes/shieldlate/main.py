"""AREA-2 control: take the snipe with no shield.  Reports Core HP over time.

SHIELD = True here.  `shieldbot` is the identical bot with SHIELD = True; the only difference is
whether a 3-Ti barrier is kept alive on (3,5), which is one of the three tiles in the attacking
Gunner's ray.
"""

from fcode import Controller, Direction, EntityType, GameError, Position

SHIELD = True
SHIELD_TILE = Position(3, 5)
STAND = Position(3, 4)


class Player:
    def __init__(self):
        self.n = []
        self.spawned = False
        self.built = 0
        self.spent = 0

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception:
            return

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()

        if et == EntityType.CORE:
            if SHIELD and not self.spawned and r >= 40:
                if ct.can_spawn(STAND):
                    ct.spawn_builder(STAND)
                    self.spawned = True
                return
            if r % 25 == 0 and r <= 200:
                self.n.append("r%d:%d" % (r, ct.get_hp()))
            if r == 201:
                self.n.append("built=%d ti=%d" % (ct.read_store(0), ct.get_global_resources()))
                ct.resign(("SH=%s " % SHIELD) + " ".join(self.n)[:470])
            return

        if et != EntityType.BUILDER_BOT:
            return
        if not SHIELD:
            return
        try:
            if ct.can_build_barrier(SHIELD_TILE):
                ct.build_barrier(SHIELD_TILE)
                self.built += 1
                ct.write_store(0, self.built)
        except Exception:
            return
