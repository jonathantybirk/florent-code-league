"""CONVEYOR MAZE Q1b: does a LOADED conveyor displace the Builder standing on it?

`cm_disp` showed an EMPTY belt does not move a unit. If a displacement rule existed at all
it would most plausibly fire on the tick a stack actually moves, so this repeats the
measurement on a belt that is carrying titanium every single round.

The carrier is a closed 4-cycle (the `a2loop` construction): a cycle never jams, so once
the harvester has fed it, a stack steps from tile to tile every round forever.

Arena `maps/lab/belt.map26` (20x12), Core A anchor (1,5), ore at (5,5).

    harvester (5,5)
      -> (5,6) EAST -> (6,6) SOUTH -> (6,7) WEST -> (5,7) NORTH -> back to (5,6)

The builder parks on (6,6), inside the cycle, and does nothing for WATCH rounds.

Two engine facts this probe had to work around, both worth keeping:
  * the balance accessor is `ct.get_global_resources()`; `ct.get_titanium()` does not exist
  * `is_tile_passable` is False for a tile a Builder Bot stands on even when
    `is_tile_empty` is True, so a stray extra builder reads exactly like terrain.
"""

from fcode import Controller, Direction, EntityType, Position

ORE = Position(5, 5)
SIT = Position(6, 6)
WATCH = 60

# (tile the builder must stand on, tile to build, what, facing)
PLAN = (
    (Position(6, 5), ORE, "harv", None),
    (Position(6, 5), Position(6, 6), "cnv", Direction.SOUTH),
    (Position(6, 6), Position(6, 7), "cnv", Direction.WEST),
    (Position(6, 7), Position(5, 7), "cnv", Direction.NORTH),
    (Position(5, 7), Position(5, 6), "cnv", Direction.EAST),
)


class Player:
    def __init__(self):
        self.phase = 0
        self.spawned = 0
        self.lead = None
        self.i = 0
        self.log = []
        self.notes = []
        self.done = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.notes.append("EXC:" + type(exc).__name__ + ":" + str(exc)[:40])

    def say(self, ct, msg):
        self.done = True
        ct.resign("CMDISP2|" + msg + "|" + "|".join(self.notes[:5]))

    def _run(self, ct):
        if self.done:
            return
        et = ct.get_entity_type()
        r = ct.get_current_round()

        if et == EntityType.CORE:
            if r > 500:
                self.say(ct, "COREONLY units=%d tries=%d" % (ct.get_unit_count(), self.spawned))
            elif ct.get_unit_count() < 2 and r % 3 == 1:
                # NOTE: every entity gets its OWN Player instance, so the Core cannot see
                # builder state at all -- get_unit_count() is the only stop condition.
                cands = (Position(3, 4), Position(2, 4), Position(3, 7), Position(2, 7),
                         Position(1, 4), Position(0, 5), Position(1, 7))
                q = cands[self.spawned % len(cands)]
                self.spawned += 1
                if ct.can_spawn(q):
                    ct.spawn_builder(q)
            return
        if et != EntityType.BUILDER_BOT:
            return

        bid = ct.get_id()
        if self.lead is None:
            self.lead = bid
        if bid != self.lead:
            ct.self_destruct()
            return

        pos = ct.get_position()
        if self.phase == 0:
            self.phase = 1
        if r > 450 and self.phase < 3:
            look = []
            for t in (Position(5, 6), Position(6, 6), Position(6, 7), Position(5, 7)):
                try:
                    bid2 = ct.get_tile_builder_bot_id(t)
                    gid = ct.get_tile_building_id(t)
                    res = None
                    if gid is not None:
                        res = ct.get_stored_resource(gid)
                    look.append("%d,%d pas=%d emp=%d bot=%s bld=%s res=%s"
                                % (t.x, t.y, ct.is_tile_passable(t), ct.is_tile_empty(t),
                                   bid2, gid, res))
                except Exception as exc:
                    look.append("%d,%d %s:%s" % (t.x, t.y, type(exc).__name__, str(exc)[:30]))
            self.say(ct, "STALL r=%d pos=%d,%d ph=%d i=%d ti=%d|%s"
                     % (r, pos.x, pos.y, self.phase, self.i, ct.get_global_resources(),
                        "|".join(look)))
            return

        if self.phase == 1:
            if self.i >= len(PLAN):
                self.phase = 2
                return
            stand, tile, what, face = PLAN[self.i]
            if pos != stand:
                self.walk(ct, pos, stand)
                return
            if not ct.is_tile_empty(tile):
                self.i += 1
                return
            if what == "harv":
                if ct.can_build_harvester(tile):
                    ct.build_harvester(tile)
                else:
                    self.notes.append("NOHARV r%d" % r)
            else:
                if ct.can_build_conveyor(tile, face):
                    ct.build_conveyor(tile, face)
                else:
                    self.notes.append("NOCNV%d r%d" % (self.i, r))
            return

        if self.phase == 2:
            if pos == SIT:
                self.phase = 3
                self.notes.append("ONBELT r%d ti=%d" % (r, ct.get_global_resources()))
                return
            self.walk(ct, pos, SIT)
            return

        self.log.append("%d@%d,%d" % (r, pos.x, pos.y))
        if len(self.log) >= WATCH:
            tiles = sorted(set(s.split("@")[1] for s in self.log))
            self.say(ct, "MOVED=%s tiles=%s first=%s last=%s ti=%d"
                     % (len(tiles) > 1, tiles, self.log[0], self.log[-1],
                        ct.get_global_resources()))

    def walk(self, ct, pos, tgt):
        """Cardinal greedy, x first then y, with the other axis as the fallback."""
        opts = []
        if pos.x != tgt.x:
            opts.append(Direction.EAST if tgt.x > pos.x else Direction.WEST)
        if pos.y != tgt.y:
            opts.append(Direction.SOUTH if tgt.y > pos.y else Direction.NORTH)
        for d in opts:
            if ct.can_move(d):
                ct.move(d)
                return
