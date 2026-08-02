"""The definitive passability table for a Builder Bot: every terrain type x every building type.

Arena `apilab` (maps/lab/mkapi.py). Core A anchor (1,6). The builder homes to (6,6), where its four
orthogonal neighbours are exactly one of each terrain:

    N (6,5) ORE_TITANIUM   S (6,7) ORE_TITANIUM   W (5,6) WALL   E (7,6) EMPTY

(7,6) is the build slot. Every building type is built there in turn, measured, then destroyed
(destroy is free and costs no action cooldown), so one builder walks the whole table without moving.
The Harvester is the exception -- it needs ore, so it goes N on (6,5).

Each row is reported as NAME=pem where
    p = is_tile_passable(tile)      e = is_tile_empty(tile)      m = can_move(direction_to_tile)
and CANMOVE is measured on a round where the builder has NOT yet acted, because acting and moving are
mutually exclusive per round (docs) and would otherwise force m=0 for everything.

A second builder parks at (4,5) so the "friendly builder bot occupies the tile" row is real, and the
own-Core footprint (2,6) is inside the builder's r^2=20 vision disc so it can be queried from the same
stance.

Reported through ct.resign() (G29); resign_message truncates at 500 chars (M06).
"""

from fcode import Controller, Direction, EntityType, Environment, GameError, Position

HOME = Position(6, 6)
SLOT = Position(7, 6)        # EMPTY build slot, EAST of home
ORE_N = Position(6, 5)       # ORE, NORTH of home -- harvester site
ORE_S = Position(6, 7)       # ORE, SOUTH of home
WALL_W = Position(5, 6)      # WALL, WEST of home
CORE_F = Position(2, 6)      # our own Core footprint, d^2=16 from home
PARK = Position(4, 5)        # where builder #2 sits
WALK = ((3, 5), (4, 5), (5, 5), (6, 5), (6, 6))

# (label, builder-method-name, needs a Direction)
SPECS = (
    ("CNV", "conveyor", True),
    ("SPL", "splitter", True),
    ("BAR", "barrier", False),
    ("GUN", "gunner", True),
    ("SEN", "sentinel", True),
    ("LNC", "launcher", False),
)


class Player:
    def __init__(self):
        self.n = []
        self.spawned = 0
        self.lead = None
        self.wp = 0
        self.i = 0
        self.stage = 0
        self.done = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.n.append("T:" + type(exc).__name__)

    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            if self.spawned < 2:
                for q in (Position(3, 5), Position(3, 7)):
                    if ct.can_spawn(q):
                        ct.spawn_builder(q)
                        self.spawned += 1
                        return
            return
        if et != EntityType.BUILDER_BOT or self.done:
            return

        pos = ct.get_position()
        if self.lead is None:
            self.lead = pos.y == 5          # the (3,5) spawn is the measuring builder
        if not self.lead:
            if pos != PARK:
                d = pos.cardinal_direction_to(PARK)
                if ct.can_move(d):
                    ct.move(d)
            return

        # --- walk to (6,6) along the waypoint list (the wall at (5,6) blocks the direct route) ---
        if self.wp < len(WALK):
            tgt = Position(*WALK[self.wp])
            if pos == tgt:
                self.wp += 1
                if self.wp == 4:
                    # Standing ON an ore tile: does the engine let a builder occupy ore?
                    self.n.append("STANDONORE=%d,%d" % (pos.x, pos.y))
                return
            d = pos.cardinal_direction_to(tgt)
            if ct.can_move(d):
                ct.move(d)
            return

        # --- stage 0: terrain baseline, measured before anything has been built ---
        if self.stage == 0:
            self.stage = 1
            self.n.append("EMP=" + self.row(ct, SLOT, Direction.EAST))
            self.n.append("ORE=" + self.row(ct, ORE_S, Direction.SOUTH))
            self.n.append("WAL=" + self.row(ct, WALL_W, Direction.WEST))
            self.n.append("COR=" + self.row(ct, CORE_F, None))
            self.n.append("SLF=" + self.row(ct, HOME, None))
            self.n.append("BOT=" + self.row(ct, PARK, None))
            return

        # --- stage 1..: one building type at a time in the EAST slot ---
        if self.i >= len(SPECS):
            if self.stage == 1:
                self.stage = 2
                ct.build_harvester(ORE_N)
                return
            if self.stage == 2:
                self.stage = 3
                self.n.append("HRV=" + self.row(ct, ORE_N, Direction.NORTH))
                self.done = True
                ct.resign("PASS|" + "|".join(self.n))
            return

        label, kind, needs_dir = SPECS[self.i]
        if self.stage == 1:
            self.stage = 11
            fn = getattr(ct, "build_" + kind)
            if needs_dir:
                fn(SLOT, Direction.EAST)
            else:
                fn(SLOT)
            return
        if self.stage == 11:
            self.stage = 1
            self.n.append(label + "=" + self.row(ct, SLOT, Direction.EAST))
            ct.destroy(SLOT)
            self.i += 1
            return

    def row(self, ct, tile, d):
        """pass / empty / can_move, each 1|0|X, as a 3-char string."""
        out = ""
        for fn in (ct.is_tile_passable, ct.is_tile_empty):
            try:
                out += "1" if fn(tile) else "0"
            except GameError:
                out += "X"
        if d is None:
            out += "-"
        else:
            try:
                out += "1" if ct.can_move(d) else "0"
            except GameError:
                out += "X"
        return out
