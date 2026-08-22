"""An economy bot that defends by mending, and wins the round-1000 tiebreak.

Modelled on TRRR, who beat our live build 0-5 on the ladder without a single fight -- all five
games ran the full 1000 rounds and were decided on titanium collected. Our panel of sparring bots
(flagship, vigil, vanguard, tempest, starter) is five rush-and-fight bots and contains NO economy
opponent, so it is structurally blind to that loss mode.

This bot exists to make that population representative. It mines, and it mends -- which turn out
to be the same act: three Harvesters plus passive income is about 10 Ti/round, and at 4 HP per
titanium that is 40 HP/round of repair against a four-Sentinel ring's 36. Beating it requires
killing it faster than that or out-mining it, which is exactly the question the old panel could
not ask.

The tiebreak order is titanium collected, then harvesters, then titanium stored, then a coin flip.
"""

from fcode import Controller, Direction, Environment, EntityType, Position

BUILDERS = 6
CARD = (Direction.NORTH, Direction.SOUTH, Direction.EAST, Direction.WEST)
DELTA = {Direction.NORTH: (0, -1), Direction.SOUTH: (0, 1),
         Direction.EAST: (1, 0), Direction.WEST: (-1, 0)}


class Player:
    def __init__(self):
        self.kind = None
        self.spawned = 0
        self.core = None
        self.mined = 0

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception:
            pass

    def _run(self, ct):
        if self.kind is None:
            self.kind = ct.get_entity_type()
        if self.kind == EntityType.CORE:
            self._core(ct)
        elif self.kind == EntityType.BUILDER_BOT:
            self._builder(ct)

    def _core(self, ct):
        if self.spawned >= BUILDERS:
            return
        try:
            if ct.get_global_resources() < ct.get_builder_bot_cost() + 40:
                return
            for tile in ct.get_nearby_tiles(2):
                if ct.can_spawn(tile):
                    ct.spawn_builder(tile)
                    self.spawned += 1
                    return
        except Exception:
            return

    def _builder(self, ct):
        here = ct.get_position()
        if self.core is None:
            try:
                for uid in ct.get_nearby_buildings():
                    if ct.get_entity_type(uid) == EntityType.CORE \
                            and ct.get_team(uid) == ct.get_team():
                        self.core = ct.get_position(uid)
                        break
            except Exception:
                return
        if self.core is None:
            return

        # MENDING THE CORE OUTRANKS EVERYTHING once it is hurt. This is the whole counter to a
        # Sentinel rush and the reason TRRR survives one: a ring of four deals 36 HP/round, while
        # three Harvesters plus passive income is about 10 Ti/round, and mending returns 4 HP per
        # titanium -- 40 HP/round. The economy IS the defence.
        try:
            for uid in ct.get_nearby_buildings():
                if ct.get_entity_type(uid) != EntityType.CORE:
                    continue
                if ct.get_team(uid) != ct.get_team():
                    continue
                if ct.get_hp(uid) >= ct.get_max_hp(uid):
                    break
                spot = ct.get_position(uid)
                if abs(spot.x - here.x) + abs(spot.y - here.y) <= 1 and ct.can_heal(spot):
                    ct.heal(spot)
                    return
                for d in CARD:
                    dx, dy = DELTA[d]
                    q = Position(spot.x + dx, spot.y + dy)
                    if abs(q.x - here.x) + abs(q.y - here.y) <= 1 and ct.can_heal(q):
                        ct.heal(q)
                        return
                step = here.cardinal_direction_to(spot)
                if step != Direction.CENTRE and ct.can_move(step):
                    ct.move(step)
                    return
                break
        except Exception:
            pass

        # a Harvester on any adjacent ore
        for d in CARD:
            dx, dy = DELTA[d]
            spot = Position(here.x + dx, here.y + dy)
            try:
                if ct.get_tile_env(spot) == Environment.ORE_TITANIUM \
                        and ct.can_build_harvester(spot):
                    ct.build_harvester(spot)
                    self.mined += 1
                    return
            except Exception:
                continue

        # a belt tile pointing home, so the Harvester's output has somewhere to go
        if self.mined:
            for d in CARD:
                dx, dy = DELTA[d]
                spot = Position(here.x + dx, here.y + dy)
                toward = (abs(spot.x - self.core.x) + abs(spot.y - self.core.y)
                          < abs(here.x - self.core.x) + abs(here.y - self.core.y))
                if not toward:
                    continue
                try:
                    if ct.can_build_conveyor(spot, d):
                        ct.build_conveyor(spot, d)
                        return
                except Exception:
                    continue

        # mend whatever is beside us, Core included
        for d in CARD:
            dx, dy = DELTA[d]
            spot = Position(here.x + dx, here.y + dy)
            try:
                bid = ct.get_tile_building_id(spot)
                if bid is None or ct.get_team(bid) != ct.get_team():
                    continue
                if ct.get_hp(bid) < ct.get_max_hp(bid) and ct.can_heal(spot):
                    ct.heal(spot)
                    return
            except Exception:
                continue

        # otherwise walk toward the nearest ore we can see, else hug the Core
        goal = None
        try:
            ores = [t for t in ct.get_nearby_tiles()
                    if ct.get_tile_env(t) == Environment.ORE_TITANIUM
                    and ct.get_tile_building_id(t) is None]
            if ores:
                goal = min(ores, key=lambda t: abs(t.x - here.x) + abs(t.y - here.y))
        except Exception:
            goal = None
        if goal is None:
            goal = self.core
        step = here.cardinal_direction_to(goal)
        try:
            if step != Direction.CENTRE and ct.can_move(step):
                ct.move(step)
                return
        except Exception:
            pass
        for d in CARD:
            try:
                if ct.can_move(d):
                    ct.move(d)
                    return
            except Exception:
                continue
