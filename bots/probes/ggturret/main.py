"""Sparring partner (NOT a probe -- it never resigns): a bot that actually runs a live Gunner.

Every shipped rival either builds no turret or fires on its own team, so there was no way to test
jamming against a real enemy turret. This bot exists to be that enemy.

On `maps/lab/ggopen.map26` (Core B anchor (25,7)) it spawns one builder, walks it to (15,6), builds
a Gunner at (15,7) facing WEST -- ray (14,7),(13,7),(12,7), pointed straight down the lane an
attacker from the west must cross -- converts 300 titanium into ammo, and then fires at
get_gunner_target() every single round for the rest of the game. No team guard: fully naive.

Used as the opponent for `gg_ejam`.
"""

from fcode import Controller, Direction, EntityType, Position

GUN = Position(15, 7)
STAND = Position(15, 6)
PARK = Position(15, 3)
SPAWN = Position(24, 6)
W = Direction.WEST


class Player:
    def __init__(self):
        self.spawned = False
        self.built = False
        self.fed = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception:
            return

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()
        if et == EntityType.CORE:
            if not self.spawned and ct.can_spawn(SPAWN):
                ct.spawn_builder(SPAWN)
                self.spawned = True
                return
            if not self.fed and r >= 20 and ct.can_convert_ammo(300):
                ct.convert_ammo(300)
                self.fed = True
            return
        if et == EntityType.BUILDER_BOT:
            pos = ct.get_position()
            if not self.built:
                if pos == STAND:
                    if ct.get_tile_building_id(GUN) is not None:
                        self.built = True
                    elif ct.can_build_gunner(GUN, W):
                        ct.build_gunner(GUN, W)
                        self.built = True
                    return
                self._walk(ct, STAND)
                return
            self._walk(ct, PARK)
            return
        if et == EntityType.GUNNER:
            t = ct.get_gunner_target()
            if t is not None and ct.can_fire(t):
                ct.fire(t)

    def _walk(self, ct, tgt):
        pos = ct.get_position()
        if pos == tgt:
            return
        best = None
        for d in (Direction.WEST, Direction.NORTH, Direction.SOUTH, Direction.EAST):
            nxt = pos.add(d)
            sc = nxt.distance_squared(tgt)
            if ct.can_move(d) and (best is None or sc < best[0]):
                best = (sc, d)
        if best is not None and best[0] < pos.distance_squared(tgt):
            ct.move(best[1])
