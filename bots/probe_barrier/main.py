"""Probe: does a Barrier actually cut a Gunner's lane onto our Core?

sprint, Team A. Core anchored (1,1), footprint {(1,1),(2,1),(1,2),(2,2)}.
An enemy Gunner at (5,1) facing WEST rays (4,1),(3,1),(2,1) and hits the Core tile (2,1) at range 3.
(4,1) sits at distance 2 from the footprint -- outside our 12-tile spawn ring, so it is a legal
deny tile.

The builder is routed via (3,2) -> (4,2) so it NEVER stands in the ray: (4,2) is off-lane, which
keeps the can_fire_from() reading a clean measurement of the Barrier alone rather than of a friendly
body blocking the shot (G11).
"""

from fcode import Controller, Direction, EntityType, Position

SHOOTER = (5, 1)
CORE_TILE = (2, 1)
DENY = (4, 1)
SPAWN = (3, 2)
RAY = ((4, 1), (3, 1), (2, 1))


class Player:
    def __init__(self):
        self.n = 0
        self.log = []
        self.spawned = False
        self.step = 0

    def run(self, ct: Controller) -> None:
        try:
            et = ct.get_entity_type()
        except Exception:
            return
        if et == EntityType.CORE:
            self._core(ct)
        elif et == EntityType.BUILDER_BOT:
            self._builder(ct)

    def _core(self, ct):
        self.n += 1
        try:
            can = ct.can_fire_from(Position(*SHOOTER), Direction.WEST,
                                   EntityType.GUNNER, Position(*CORE_TILE))
        except Exception as e:
            can = "ERR:%s" % type(e).__name__
        try:
            bid = ct.get_tile_building_id(Position(*DENY))
        except Exception:
            bid = None
        occupied = []
        for t in RAY:
            try:
                if ct.get_tile_builder_bot_id(Position(*t)) is not None:
                    occupied.append("%d,%d" % t)
            except Exception:
                pass
        self.log.append("r%d can_fire=%s barrier=%s bots_in_ray=[%s]"
                        % (self.n, can, "yes" if bid is not None else "no", ",".join(occupied)))
        if not self.spawned:
            try:
                ct.spawn_builder(Position(*SPAWN))
                self.spawned = True
            except Exception:
                pass
        if self.n == 6:
            try:
                ct.resign("|".join(self.log))
            except Exception:
                ct.resign()

    def _builder(self, ct):
        if self.step == 0:
            try:
                ct.move(Direction.EAST)          # (3,2) -> (4,2), off-lane
                self.step = 1
            except Exception:
                pass
            return
        if self.step == 1:
            try:
                if ct.can_build_barrier(Position(*DENY)):
                    ct.build_barrier(Position(*DENY))
                    self.step = 2
            except Exception:
                pass
