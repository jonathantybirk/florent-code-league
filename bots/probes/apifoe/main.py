"""Opponent fixture for the enemy half of the passability table (used by probe `apipass2`).

Runs as Team B on arena `close` (14x11, Core A anchor (1,5), Core B anchor (8,5)). It plants a known
set of buildings on column x=6, halfway between the Cores, and parks a spare builder there:

    (6,4) BARRIER   (6,5) CONVEYOR facing EAST   (6,6) SPLITTER facing EAST   (6,7) parked BUILDER
    (6,3) BARRIER -- sits directly BEHIND the (6,4) barrier as seen from (6,5)/(6,6), so `apipass2`
                     can ask whether an ENTITY hidden behind an occluder is still enumerable.

`apipass2` then walks a Team A builder to (5,5) and reads all four tiles plus the Team B Core
footprint at (8,5). This probe never resigns -- the reporting unit must be the one asking the
question (M07), and only one resign_message survives.
"""

from fcode import Controller, Direction, EntityType, GameError, Position

# (build target, stance the builder must occupy, kind, direction or None)
JOBS = (
    (Position(6, 5), Position(7, 5), "conveyor", Direction.EAST),
    (Position(6, 4), Position(7, 4), "barrier", None),
    (Position(6, 3), Position(7, 3), "barrier", None),
    (Position(6, 6), Position(7, 6), "splitter", Direction.EAST),
)
PARK = Position(6, 7)


class Player:
    def __init__(self):
        self.spawned = 0
        self.role = None
        self.i = 0

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception:
            return

    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            if self.spawned < 2:
                for q in (Position(7, 5), Position(7, 6)):
                    if ct.can_spawn(q):
                        ct.spawn_builder(q)
                        self.spawned += 1
                        return
            return
        if et != EntityType.BUILDER_BOT:
            return

        pos = ct.get_position()
        if self.role is None:
            self.role = "b" if pos.y == 5 else "p"

        if self.role == "p":
            # The parked body: walk to (6,7) and never move again.
            if pos != PARK:
                d = pos.cardinal_direction_to(PARK)
                if ct.can_move(d):
                    ct.move(d)
            return

        if self.i >= len(JOBS):
            return
        tgt, stance, kind, d = JOBS[self.i]
        if ct.get_tile_building_id(tgt) is not None:
            self.i += 1
            return
        if pos != stance:
            step = pos.cardinal_direction_to(stance)
            if ct.can_move(step):
                ct.move(step)
            return
        fn = getattr(ct, "build_" + kind)
        if d is None:
            fn(tgt)
        else:
            fn(tgt, d)
        self.i += 1
