"""Team-B partner for `vfoe`: builds ONE PERSISTENT row of every enemy-owned prop.

Differs from pt_prop on purpose. pt_prop built one prop at a time on a shared tile and
relied on both teams counting rounds identically; if a build silently failed, the measuring
bot would have recorded an EMPTY tile under a confident label. Here all seven props are
built on distinct tiles and left standing for the rest of the game, so the measuring bot
can gate every row on actually SEEING the building (id + type + team) rather than on a
round number.

Never calls convert_ammo (so the gunner and sentinel have no ammunition and cannot fire)
and never calls launch (so the launcher cannot throw the measuring bot). Parks well clear
of the lane afterwards.

Arena: maps/lab/passlab.map26. Lane row 10 is empty for the full width; props go on row 9.
"""

from fcode import Controller, Direction, EntityType, Environment, Position

CARD = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)

# (x on row 9, kind, extra) -- built from stance (x, 10) facing NORTH
PLAN = (
    (7, "launcher", None),
    (8, "sentinel", Direction.NORTH),
    (9, "harvester", None),          # (9,9) is ORE on passlab
    (10, "gunner", Direction.NORTH),
    (11, "barrier", None),
    (12, "splitter", Direction.NORTH),
    (13, "conveyor", Direction.NORTH),
)
PARK = Position(17, 11)


class Player:
    def __init__(self):
        self.spawned = False
        self.gen = None
        self.ct = None
        self.dead = False

    def run(self, ct: Controller) -> None:
        self.ct = ct
        try:
            et = ct.get_entity_type()
        except Exception:
            return
        if et == EntityType.CORE:
            if not self.spawned:
                here = ct.get_position()
                for dx in range(-2, 4):
                    for dy in range(-2, 4):
                        p = Position(here.x + dx, here.y + dy)
                        try:
                            if ct.can_spawn(p):
                                ct.spawn_builder(p)
                                self.spawned = True
                                return
                        except Exception:
                            pass
            return
        if et != EntityType.BUILDER_BOT or self.dead:
            return
        if self.gen is None:
            self.gen = self._script()
        try:
            next(self.gen)
        except StopIteration:
            self.dead = True
        except Exception:
            self.dead = True

    def _free(self, ct, p):
        if not (0 <= p.x < ct.get_map_width() and 0 <= p.y < ct.get_map_height()):
            return False
        try:
            if not ct.is_in_vision(p):
                return False
            if ct.get_tile_env(p) == Environment.WALL:
                return False
            if ct.get_tile_building_id(p) is not None:
                return False
            b = ct.get_tile_builder_bot_id(p)
            if b is not None and b != ct.get_id():
                return False
        except Exception:
            return False
        return True

    def _walk_to(self, tx, ty, budget=120):
        tgt = Position(tx, ty)
        for _ in range(budget):
            ct = self.ct
            if ct.get_position() == tgt:
                return
            if ct.get_move_cooldown() == 0:
                pos = ct.get_position()
                order = []
                if pos.x != tx:
                    order.append(Direction.EAST if tx > pos.x else Direction.WEST)
                if pos.y != ty:
                    order.append(Direction.SOUTH if ty > pos.y else Direction.NORTH)
                for d in order + list(CARD):
                    dx = 1 if d is Direction.EAST else (-1 if d is Direction.WEST else 0)
                    dy = 1 if d is Direction.SOUTH else (-1 if d is Direction.NORTH else 0)
                    if self._free(ct, Position(pos.x + dx, pos.y + dy)):
                        try:
                            ct.move(d)
                        except Exception:
                            pass
                        break
            yield

    def _script(self):
        # get onto the lane, then run it west to the first build stance
        yield from self._walk_to(18, 10)
        yield from self._walk_to(7, 10)
        for x, kind, extra in PLAN:
            yield from self._walk_to(x, 10)
            prop = Position(x, 9)
            for _ in range(30):
                ct = self.ct
                if ct.can_act():
                    args = (prop, extra) if extra is not None else (prop,)
                    try:
                        getattr(ct, "build_" + kind)(*args)
                        break
                    except Exception:
                        pass
                yield
            yield
        # park far from the lane and stand still for the rest of the game
        yield from self._walk_to(PARK.x, 10)
        yield from self._walk_to(PARK.x, PARK.y)
        while True:
            yield
