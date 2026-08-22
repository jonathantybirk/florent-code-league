"""A sparring partner that packs its own base solid, to squeeze the rusher's firing spots.

The turtle bot rings its Core at one radius. This one fills EVERYTHING within radius RING of the
Core with barriers, which is exactly the case the rusher is reported to fail on: the near firing
spots all become unbuildable, and the question is whether it settles for a spot at the far end of
the Sentinel's r^2 <= 32 reach instead of milling about.

It never attacks. A match against it measures placement, nothing else.
"""

from fcode import Controller, Direction, EntityType, Position

CARD = (Direction.NORTH, Direction.SOUTH, Direction.EAST, Direction.WEST)
RING = 4
BUILDERS = 6


class Player:
    def __init__(self):
        self.kind = None
        self.spawned = 0
        self.core = None
        self.step = 0

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception:
            pass

    def _run(self, ct):
        if self.kind is None:
            self.kind = ct.get_entity_type()
        if self.kind == EntityType.CORE:
            if self.spawned < BUILDERS and ct.get_global_resources() > ct.get_builder_bot_cost() + 30:
                for tile in ct.get_nearby_tiles(2):
                    if ct.can_spawn(tile):
                        ct.spawn_builder(tile)
                        self.spawned += 1
                        return
            return
        if self.kind != EntityType.BUILDER_BOT:
            return

        here = ct.get_position()
        if self.core is None:
            for uid in ct.get_nearby_buildings():
                if ct.get_entity_type(uid) == EntityType.CORE and ct.get_team(uid) == ct.get_team():
                    self.core = ct.get_position(uid)
                    break
        if self.core is None:
            return

        # brick every adjacent tile that sits inside the shell
        for d in CARD:
            dx = 1 if d == Direction.EAST else -1 if d == Direction.WEST else 0
            dy = 1 if d == Direction.SOUTH else -1 if d == Direction.NORTH else 0
            spot = Position(here.x + dx, here.y + dy)
            if max(abs(spot.x - self.core.x), abs(spot.y - self.core.y)) > RING:
                continue
            if ct.can_build_barrier(spot):
                ct.build_barrier(spot)
                return

        # otherwise shuffle around inside the shell looking for a hole
        self.step += 1
        order = (CARD[self.step % 4], CARD[(self.step + 1) % 4],
                 CARD[(self.step + 2) % 4], CARD[(self.step + 3) % 4])
        for d in order:
            dx = 1 if d == Direction.EAST else -1 if d == Direction.WEST else 0
            dy = 1 if d == Direction.SOUTH else -1 if d == Direction.NORTH else 0
            spot = Position(here.x + dx, here.y + dy)
            if max(abs(spot.x - self.core.x), abs(spot.y - self.core.y)) > RING + 1:
                continue
            if ct.can_move(d):
                ct.move(d)
                return
