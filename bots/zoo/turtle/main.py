"""A sparring partner that does nothing but wall itself in.

The rusher has to cope with an opponent that answers a Sentinel ring by bricking up the approach.
This bot spawns builders and has them ring the Core with barriers, then keep rebuilding any that
are destroyed. It never attacks, so a match against it measures exactly one thing: whether the
rusher can chew through a wall and still finish inside the round limit.
"""

from fcode import Controller, Direction, EntityType, Position

CARD = (Direction.NORTH, Direction.SOUTH, Direction.EAST, Direction.WEST)
RING = 3


class Player:
    def __init__(self):
        self.kind = None
        self.spawned = 0
        self.core = None

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception:
            pass

    def _run(self, ct):
        if self.kind is None:
            self.kind = ct.get_entity_type()
        if self.kind == EntityType.CORE:
            if self.spawned < 4 and ct.get_global_resources() > ct.get_builder_bot_cost() + 40:
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

        for d in CARD:
            spot = Position(here.x + (1 if d == Direction.EAST else -1 if d == Direction.WEST else 0),
                            here.y + (1 if d == Direction.SOUTH else -1 if d == Direction.NORTH else 0))
            gap = max(abs(spot.x - self.core.x), abs(spot.y - self.core.y))
            if gap != RING:
                continue
            if ct.can_build_barrier(spot):
                ct.build_barrier(spot)
                return

        # shuffle around the ring looking for a hole
        want = Position(self.core.x + RING, self.core.y)
        step = here.cardinal_direction_to(want)
        for d in (step,) + CARD:
            if d != Direction.CENTRE and ct.can_move(d):
                ct.move(d)
                return
