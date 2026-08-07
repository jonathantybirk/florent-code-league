"""CONVEYOR MAZE Q2 (side A): does an ENEMY conveyor displace a Builder standing on it?

This is the load-bearing question for the whole "conveyor maze" idea. `cm_disp` and
`cm_disp2` already showed a team's OWN belt -- idle and loaded -- never moves a unit
standing on it. The claim that survives that is that the belt shoves the OTHER team's
units, since Conveyor/Splitter are the only buildings passable by both teams.

Run against `cm_foe_b`, which lays a Team-B chain at (12,4)->(11,4)->(10,4) all facing
WEST in the middle of `maps/lab/belt.map26`. This builder walks east to (9,4), waits for
the chain to appear, steps onto (10,4) and then (11,4), and from there does nothing at all
for WATCH rounds while logging its own position. Displacement would drag it west.

    python tools/runprobe.py cm_foe_a --map lab/belt --vs cm_foe_b
"""

from fcode import Controller, Direction, EntityType, Position

WAIT = Position(9, 4)            # bare ground just west of the enemy chain
HEAD = Position(10, 4)           # enemy belt, output = (9,4)
SIT = Position(11, 4)            # enemy belt, output = HEAD -- a belt, so it has somewhere to go
WATCH = 40
SPAWNS = (Position(3, 4), Position(3, 7), Position(0, 4), Position(2, 4),
          Position(2, 7), Position(1, 4), Position(0, 7))


class Player:
    def __init__(self):
        self.tries = 0
        self.phase = 1
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
        ct.resign("CMFOE|" + msg + "|" + "|".join(self.notes[:5]))

    def _run(self, ct):
        if self.done:
            return
        et = ct.get_entity_type()
        r = ct.get_current_round()

        if et == EntityType.CORE:
            if r > 300:
                self.say(ct, "COREONLY units=%d tries=%d" % (ct.get_unit_count(), self.tries))
            elif ct.get_unit_count() < 2 and r % 3 == 1:
                q = SPAWNS[self.tries % len(SPAWNS)]
                self.tries += 1
                if ct.can_spawn(q):
                    ct.spawn_builder(q)
            return
        if et != EntityType.BUILDER_BOT:
            return

        pos = ct.get_position()
        if r > 260 and self.phase < 4:
            self.say(ct, "STALL r=%d pos=%d,%d ph=%d" % (r, pos.x, pos.y, self.phase))
            return

        if self.phase == 1:                        # walk out to the waiting tile
            if pos == WAIT:
                self.phase = 2
                return
            self.walk(ct, pos, WAIT)
            return

        if self.phase == 2:                        # wait for the enemy chain to exist
            if ct.is_tile_empty(SIT) or ct.is_tile_empty(HEAD):
                return
            self.notes.append("CHAIN r%d headpass=%d sitpass=%d"
                              % (r, ct.is_tile_passable(HEAD), ct.is_tile_passable(SIT)))
            self.phase = 3
            return

        if self.phase == 3:                        # step onto the enemy belt, twice
            if pos == SIT:
                self.phase = 4
                self.notes.append("ONFOEBELT r%d" % r)
                return
            if ct.can_move(Direction.EAST):
                ct.move(Direction.EAST)
            else:
                self.notes.append("BLOCKED r%d at %d,%d" % (r, pos.x, pos.y))
            return

        # phase 4: never act again -- just record where the engine has put us
        self.log.append("%d@%d,%d" % (r, pos.x, pos.y))
        if len(self.log) >= WATCH:
            tiles = sorted(set(s.split("@")[1] for s in self.log))
            self.say(ct, "MOVED=%s tiles=%s first=%s last=%s n=%d"
                     % (len(tiles) > 1, tiles, self.log[0], self.log[-1], len(self.log)))

    def walk(self, ct, pos, tgt):
        opts = []
        if pos.x != tgt.x:
            opts.append(Direction.EAST if tgt.x > pos.x else Direction.WEST)
        if pos.y != tgt.y:
            opts.append(Direction.SOUTH if tgt.y > pos.y else Direction.NORTH)
        for d in opts:
            if ct.can_move(d):
                ct.move(d)
                return
