"""Probe: does a Sentinel's line pierce buildings where a Gunner's does not?"""
import sys
from fcode import Controller, EntityType, Direction, Position


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def ask(fn, *a):
    try:
        return fn(*a)
    except Exception as e:  # noqa
        return f"<{type(e).__name__}>"


class Player:
    def __init__(self):
        self.stage = 0

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as e:  # noqa
            log("ERR", type(e).__name__, e)

    def _run(self, ct):
        t = ct.get_entity_type()
        if t == EntityType.CORE:
            if ct.get_current_round() == 0:
                for tile in ct.get_nearby_tiles(2):
                    if ct.can_spawn(tile):
                        ct.spawn_builder(tile)
            return
        if t != EntityType.BUILDER_BOT:
            return
        me = ct.get_position()
        east1, east2, east3 = (Position(me.x + i, me.y) for i in (1, 2, 3))

        if self.stage == 0:
            log("=== empty ground, firing EAST from", tuple(me))
            for kind in (EntityType.GUNNER, EntityType.SENTINEL):
                log(f"  {kind} -> +1 {ask(ct.can_fire_from, me, Direction.EAST, kind, east1)}"
                    f"  +2 {ask(ct.can_fire_from, me, Direction.EAST, kind, east2)}"
                    f"  +3 {ask(ct.can_fire_from, me, Direction.EAST, kind, east3)}")
            if ct.can_build_barrier(east1):
                ct.build_barrier(east1)
                log("  built a BARRIER at +1")
                self.stage = 1
            return
        if self.stage == 1:
            log("=== with a Barrier occupying +1")
            for kind in (EntityType.GUNNER, EntityType.SENTINEL):
                log(f"  {kind} -> +2 {ask(ct.can_fire_from, me, Direction.EAST, kind, east2)}"
                    f"  +3 {ask(ct.can_fire_from, me, Direction.EAST, kind, east3)}")
            log("  VERDICT: a True at +2/+3 through the Barrier means it pierces")
            self.stage = 2
