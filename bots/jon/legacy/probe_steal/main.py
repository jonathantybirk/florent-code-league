"""Probe: does a Conveyor of ours, placed beside an ENEMY Harvester, receive
their titanium -- and can we belt it home?

A Harvester "outputs one stack to an adjacent building" and the rulebook says
resources may be output to a building of the opposing team. We already abuse
that to feed our Gunners. If a plain Conveyor also collects, then a belt laid
next to their Harvester mines *with their machine, into our Core*.
"""
import sys
from fcode import Controller, EntityType, Direction, Position

D4 = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def ask(fn, *a):
    try:
        return fn(*a)
    except Exception:  # noqa
        return None


class Player:
    def __init__(self):
        self.tap = None
        self.seen = 0

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as e:  # noqa
            log("ERR", type(e).__name__, e)

    def _run(self, ct):
        t = ct.get_entity_type()
        r = ct.get_current_round()
        if t == EntityType.CORE:
            if r < 3:
                for tile in ct.get_nearby_tiles(2):
                    if ct.can_spawn(tile):
                        ct.spawn_builder(tile)
            return
        if t != EntityType.BUILDER_BOT:
            return
        me = ct.get_position()
        mine = ct.get_team()

        # Watch a tap we already planted.
        if self.tap is not None:
            held = ask(ct.get_stored_resource, ct.get_tile_building_id(self.tap))
            if held is not None and self.seen < 8:
                self.seen += 1
                log(f"r{r} TAP at {tuple(self.tap)} holds {held}  "
                    f"(our titanium {ct.get_global_resources()})")
            return

        # Find an enemy Harvester and put a Conveyor beside it.
        for tile in ct.get_nearby_tiles():
            bid = ct.get_tile_building_id(tile)
            if bid is None or ct.get_team(bid) == mine:
                continue
            if ct.get_entity_type(bid) != EntityType.HARVESTER:
                continue
            for d in D4:
                spot = tile.add(d)
                if spot.distance_squared(me) <= 2 and ct.can_build_conveyor(spot, d):
                    ct.build_conveyor(spot, d)
                    self.tap = spot
                    log(f"r{r} planted TAP conveyor at {tuple(spot)} "
                        f"beside enemy Harvester {tuple(tile)}")
                    return
        # else wander toward them
        goal = Position(ct.get_map_width() - 1 - me.x, ct.get_map_height() - 1 - me.y)
        best = None
        for d in [x for x in Direction if x != Direction.CENTRE]:
            if not ct.can_move(d):
                continue
            score = me.add(d).distance_squared(goal)
            if best is None or score < best[0]:
                best = (score, d)
        if best:
            ct.move(best[1])
