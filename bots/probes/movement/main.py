"""Probe G42 and the rest of the movement/standing rules on 2.3.3.

The 2.3.3 is_tile_passable docstring says a builder may stand on a tile that is empty, or holds
"a conveyor, splitter, or the allied core". G42 (2.2.0) says harvesters DO block. Measure:
  M1 harvester -- passable? can_move onto it?
  M2 conveyor  -- passable? can a builder actually END UP standing on it?
  M3 allied Core footprint -- passable? (the Core itself reported False for its own tile)
  M4 barrier   -- passable?
  M5 diagonal movement -- is_cardinal only?

Arena `scal`: ore at (6,8) and (6,10); builder homes to (6,9).
"""

from fcode import Controller, Direction, EntityType, GameError, Position

HOME = Position(6, 9)
ORE_N = Position(6, 8)
CONV_W = Position(5, 9)
BARR_S = Position(6, 10)
CORE_TILE = Position(2, 9)      # Core A anchor is (1,9); (2,9) is its NE footprint tile


def e(exc):
    return type(exc).__name__ + ":" + str(exc)[:20]


class Player:
    def __init__(self):
        self.n = []
        self.spawned = False
        self.ph = 0

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.n.append("TOP:" + e(exc))

    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            if not self.spawned and ct.can_spawn(Position(3, 9)):
                ct.spawn_builder(Position(3, 9))
                self.spawned = True
            return
        if et != EntityType.BUILDER_BOT:
            return

        pos = ct.get_position()

        if self.ph == 0:
            if pos != HOME:
                d = pos.cardinal_direction_to(HOME)
                if ct.can_move(d):
                    ct.move(d)
                return
            self.ph = 1
            # M5: diagonal movement legality, on open ground, before anything is built.
            self.n.append("M5 diagNE can=%s isCard=%s" % (
                ct.can_move(Direction.NORTHEAST), Direction.NORTHEAST.is_cardinal()))
            return

        if self.ph == 1:
            self.ph = 2
            ct.build_harvester(ORE_N)
            return
        if self.ph == 2:
            self.ph = 3
            self.n.append("M1 harv pass=%s empty=%s canmoveN=%s" % (
                ct.is_tile_passable(ORE_N), ct.is_tile_empty(ORE_N),
                ct.can_move(Direction.NORTH)))
            ct.build_conveyor(CONV_W, Direction.NORTH)
            return
        if self.ph == 3:
            self.ph = 4
            self.n.append("M2 conv pass=%s empty=%s canmoveW=%s" % (
                ct.is_tile_passable(CONV_W), ct.is_tile_empty(CONV_W),
                ct.can_move(Direction.WEST)))
            ct.build_barrier(BARR_S)
            return
        if self.ph == 4:
            self.ph = 5
            self.n.append("M4 barr pass=%s canmoveS=%s" % (
                ct.is_tile_passable(BARR_S), ct.can_move(Direction.SOUTH)))
            self.n.append("M3 coretile pass=%s empty=%s" % (
                ct.is_tile_passable(CORE_TILE), ct.is_tile_empty(CORE_TILE)))
            return
        if self.ph == 5:
            self.ph = 6
            # M2b: actually step onto the conveyor and confirm we are standing on it.
            try:
                ct.move(Direction.WEST)
                self.n.append("M2b moved onto conv, now at %d,%d bld=%s" % (
                    ct.get_position().x, ct.get_position().y,
                    ct.get_tile_building_id(ct.get_position()) is not None))
            except Exception as exc:
                self.n.append("M2b " + e(exc))
            return
        if self.ph == 6:
            self.ph = 7
            # M3b: walk west toward the Core and see whether we may enter its footprint.
            p = ct.get_position()
            self.n.append("M3b at %d,%d canW=%s" % (p.x, p.y, ct.can_move(Direction.WEST)))
            return
        ct.resign(" | ".join(self.n[:9]))
