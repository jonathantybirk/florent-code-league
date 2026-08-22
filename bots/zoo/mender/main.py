"""A local stand-in for the top of the ladder: rush a little, then out-heal everything.

Modelled directly on `not adgato` (rank 1, 2323) as decoded from five ladder replays. Across all
five games they built exactly five Builder Bots and four Sentinels, ZERO harvesters, conveyors or
splitters, and won by mending:

    us    109 shots = 1962 HP dealt, 1090 Ti spent, 0 heals
    them   28 shots =  504 HP dealt,  280 Ti spent, 510 heals = 2040 HP for 510 Ti

Mending returns 4 HP per titanium; a Sentinel returns 1.8. With neither side mining, both run on
the same 2.5 Ti/round of passive income, so the cheaper spender wins every long game.

This bot exists to reproduce that matchup locally, because it is the one we cannot beat.
"""

from fcode import Controller, Direction, EntityType, Position

BUILDERS = 5
SENTINELS = 2
CARD = (Direction.NORTH, Direction.SOUTH, Direction.EAST, Direction.WEST)
DELTA = {Direction.NORTH: (0, -1), Direction.SOUTH: (0, 1),
         Direction.EAST: (1, 0), Direction.WEST: (-1, 0)}


class Player:
    def __init__(self):
        self.kind = None
        self.spawned = 0
        self.core = None
        self.built = 0

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
        elif self.kind in (EntityType.SENTINEL, EntityType.GUNNER):
            self._turret(ct)

    def _core(self, ct):
        if self.spawned < BUILDERS:
            try:
                if ct.get_global_resources() >= ct.get_builder_bot_cost():
                    for tile in ct.get_nearby_tiles(2):
                        if ct.can_spawn(tile):
                            ct.spawn_builder(tile)
                            self.spawned += 1
                            return
            except Exception:
                return
        # keep a little ammunition so the Sentinels can answer
        try:
            if ct.get_global_ammo() < 40 and ct.get_global_resources() > 120 \
                    and ct.can_convert_ammo(10):
                ct.convert_ammo(10)
        except Exception:
            pass

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

        # mending the Core comes before everything else
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

        # a couple of Sentinels facing out, so the attacker cannot camp for free
        if self.built < SENTINELS:
            for d in CARD:
                dx, dy = DELTA[d]
                spot = Position(here.x + dx, here.y + dy)
                try:
                    if ct.can_build_sentinel(spot, d):
                        ct.build_sentinel(spot, d)
                        self.built += 1
                        return
                except Exception:
                    continue

        # otherwise hug the Core, ready to mend
        gap = max(abs(here.x - self.core.x), abs(here.y - self.core.y))
        if gap <= 2:
            return
        step = here.cardinal_direction_to(self.core)
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

    def _turret(self, ct):
        try:
            for tile in ct.get_attackable_tiles():
                bid = ct.get_tile_building_id(tile)
                if bid is None or ct.get_team(bid) == ct.get_team():
                    continue
                if ct.can_fire(tile):
                    ct.fire(tile)
                    return
        except Exception:
            return
