"""Does a Harvester deliver DIRECTLY to the Core when it sits inside CORE_ACTION_RADIUS_SQ?

Builds exactly ONE harvester on the single ore tile of arenas cd1 / cd4 / cd8 / cd9
(min d^2 to the Core footprint = 1, 4, 8, 9) and then builds nothing else for the rest
of the match. No conveyor is ever laid.

MEASURED 2026-08-02 on fcode 2.3.3, `maps/lab/cd{1,4,8,9}.map26` vs `idle`:

    cd1 (d^2=1, ORTHOGONALLY ADJACENT)  a_titanium_collected = 2500, a_buildings = 2
    cd4 (d^2=4)                         a_titanium_collected = 0
    cd8 (d^2=8)                         a_titanium_collected = 0
    cd9 (d^2=9)                         a_titanium_collected = 0

So there is NO Core pull radius: CORE_ACTION_RADIUS_SQ=8 grants nothing here. What happens
is simply that the Core is a BUILDING, and a harvester round-robins into every orthogonally
adjacent building -- so a harvester touching the footprint needs ZERO conveyors and beats a
two-conveyor chain (2500 vs 2490, the difference being belt latency).

The catch is in the map format: the editor forces a one-tile EMPTY margin around each Core,
so on all 21 shipped maps the nearest ore is at least 2 tiles from the footprint. A static
sweep found 0 of 42 core-sides with a zero-conveyor ore; the minimum chain is 1 conveyor
(duel, fjord, skerry, string) and the maximum is 6 (showdown).

`a_titanium_collected` is the primary measurement; the probe also resigns at r995 with the
build round and the harvester's distance so the finding cannot be lost again (G29/M06).
"""

from fcode import Controller, Direction, EntityType, Environment, GameError, Position

CARD = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)


class Player:
    def __init__(self):
        self.spawned = False
        self.built = False
        self.ore = None
        self.note = ""

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.note = type(exc).__name__[:6] + ":" + str(exc)[:20]

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()
        if et == EntityType.CORE:
            if not self.spawned:
                a = ct.get_position()
                for p in (Position(a.x + 1, a.y - 1), Position(a.x, a.y - 1),
                          Position(a.x + 2, a.y)):
                    if ct.can_spawn(p) and ct.get_tile_env(p) == Environment.EMPTY:
                        ct.spawn_builder(p)
                        self.spawned = True
                        return
            return
        if et != EntityType.BUILDER_BOT:
            return
        if self.built:
            if r == 995:
                ore = self.ore
                ct.resign(("HDIST built_r=%s ore=%s,%s harv_id=%s ti=%d %s" % (
                    self.built, ore.x, ore.y, ct.get_tile_building_id(ore),
                    ct.get_global_resources(), self.note))[:495])
            return

        pos = ct.get_position()
        if self.ore is None:
            for t in ct.get_nearby_tiles():
                if ct.get_tile_env(t) == Environment.ORE_TITANIUM:
                    self.ore = t
                    break
        if self.ore is None:
            return
        if pos.distance_squared(self.ore) == 1:
            if ct.can_build_harvester(self.ore):
                ct.build_harvester(self.ore)
                self.built = r
            return
        best = None
        for d in CARD:
            if not ct.can_move(d):
                continue
            sc = pos.add(d).distance_squared(self.ore)
            if best is None or sc < best[0]:
                best = (sc, d)
        if best is not None and best[0] < pos.distance_squared(self.ore):
            ct.move(best[1])
