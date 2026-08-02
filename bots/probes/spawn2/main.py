"""Which buildings CLOSE a spawn-ring tile?  (And does our own economy throttle our own spawning?)

A barrier closes a ring tile -- but conveyors and splitters are PASSABLE to a Builder Bot (G61), so
if can_spawn only tested passability a conveyor would leave the tile open.  That distinction decides
two things: whether a ring lock needs 3-Ti barriers specifically, and whether the belt an economy bot
lays across its OWN ring is quietly costing it spawn tiles.

Derives its own anchor, so it runs on any map.  T = anchor+(2,0) and the builder stands on
anchor+(2,1); both are ring tiles and they are orthogonally adjacent, so the builder can cycle every
building type onto T while the Core -- which acts first, being the lower entity id -- reads
can_spawn / is_tile_passable / is_tile_empty on T one round after each build.

Reported by the CORE (M07) through resign (G29/M06).
"""

from fcode import Controller, Direction, EntityType, GameError, Position

REPORT = 15


class Player:
    def __init__(self):
        self.n = []
        self.a = None
        self.spawned = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.n.append("TOP:" + type(exc).__name__ + ":" + str(exc)[:16])

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()
        if et == EntityType.CORE:
            self._core(ct, r)
        elif et == EntityType.BUILDER_BOT:
            self._builder(ct, r)

    def _core(self, ct, r):
        a = ct.get_position()
        t = Position(a.x + 2, a.y)
        if not self.spawned:
            s = Position(a.x + 2, a.y + 1)
            if ct.can_spawn(s):
                ct.spawn_builder(s)
                self.spawned = True
            return
        if r in (2, 4, 6, 8, 10, 12):
            k = "none"
            try:
                b = ct.get_tile_building_id(t)
                if b is not None:
                    k = str(ct.get_entity_type(b)).split(".")[-1][:4]
            except GameError:
                k = "err"
            try:
                self.n.append("%s sp%d pa%d em%d" % (
                    k, int(ct.can_spawn(t)), int(ct.is_tile_passable(t)),
                    int(ct.is_tile_empty(t))))
            except GameError:
                self.n.append(k + " raised")
            return
        if r == REPORT:
            ct.resign(("S2|" + " | ".join(self.n))[:495])

    def _builder(self, ct, r):
        pos = ct.get_position()
        t = Position(pos.x, pos.y - 1)

        def clear():
            try:
                if ct.get_tile_building_id(t) is not None:
                    ct.destroy(t)
            except GameError:
                return

        if r == 1:
            ct.build_conveyor(t, Direction.EAST)
        elif r == 3:
            clear()
            ct.build_harvester(t)
        elif r == 5:
            clear()
            ct.build_gunner(t, Direction.EAST)
        elif r == 7:
            clear()
            ct.build_launcher(t)
        elif r == 9:
            clear()
            ct.build_splitter(t, Direction.EAST)
        elif r == 11:
            clear()
            ct.build_barrier(t)
