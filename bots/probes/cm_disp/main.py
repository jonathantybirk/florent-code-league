"""CONVEYOR MAZE Q1: does a Conveyor DISPLACE a Builder Bot standing on it?

The "conveyor maze" idea -- belts near the enemy Core that carry enemy Builders the wrong
way -- rests entirely on belts moving UNITS. The official rules only ever say a belt moves
a resource STACK (game-rules-conveyors), so this measures the unit case directly.

Arena `maps/lab/belt.map26` (20x12), Core A anchor (1,5), ore at (5,5).

The builder walks out to open ground at (9,4), lays a two-tile chain pointing EAST
    (10,4) EAST -> (11,4) EAST
steps onto the head of it at (10,4), and then does nothing at all for WATCH rounds while
logging its own position every round. A belt that displaces units would drag it east onto
(11,4) and then off the end of the chain.

NOTE: the balance accessor is `ct.get_global_resources()`; there is no `ct.get_titanium()`.

Reported by the builder through resign (G29).
"""

from fcode import Controller, Direction, EntityType, Position

PARK = Position(9, 4)            # last EMPTY tile before the chain
B1 = Position(10, 4)             # chain head, points EAST -- this is what we stand on
B2 = Position(11, 4)             # chain tail, points EAST
WATCH = 40


class Player:
    def __init__(self):
        self.phase = 1
        self.spawned = 0
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
        ct.resign("CMDISP|" + msg + "|" + "|".join(self.notes[:5]))

    def _run(self, ct):
        if self.done:
            return
        et = ct.get_entity_type()
        r = ct.get_current_round()

        if et == EntityType.CORE:
            if r > 400:
                self.say(ct, "COREONLY ph=%d" % self.phase)
            elif self.spawned == 0:
                for q in (Position(3, 4), Position(3, 5), Position(2, 4), Position(2, 7)):
                    if ct.can_spawn(q):
                        ct.spawn_builder(q)
                        self.spawned = 1
                        return
            return
        if et != EntityType.BUILDER_BOT:
            return

        pos = ct.get_position()
        if r > 350 and self.phase < 4:
            self.say(ct, "STALL r=%d pos=%d,%d ph=%d ti=%d"
                     % (r, pos.x, pos.y, self.phase, ct.get_global_resources()))
            return

        if self.phase == 1:                       # walk out to the parking tile
            if pos == PARK:
                self.phase = 2
                return
            d = pos.cardinal_direction_to(PARK)
            if ct.can_move(d):
                ct.move(d)
            elif pos.y != PARK.y:
                dy = Direction.SOUTH if PARK.y > pos.y else Direction.NORTH
                if ct.can_move(dy):
                    ct.move(dy)
            return

        if self.phase == 2:                       # build the chain head, then stand on it
            if pos == B1:
                self.phase = 3
                return
            if ct.is_tile_empty(B1):
                if ct.can_build_conveyor(B1, Direction.EAST):
                    ct.build_conveyor(B1, Direction.EAST)
                return
            if ct.can_move(Direction.EAST):
                ct.move(Direction.EAST)
            else:
                self.notes.append("NOSTEP r%d" % r)
            return

        if self.phase == 3:                       # build the chain tail from on top of B1
            if not ct.is_tile_empty(B2):
                self.phase = 4
                self.notes.append("ONBELT r%d at %d,%d" % (r, pos.x, pos.y))
                return
            if ct.can_build_conveyor(B2, Direction.EAST):
                ct.build_conveyor(B2, Direction.EAST)
            else:
                self.notes.append("NOB2 r%d" % r)
            return

        # phase 4: do absolutely nothing, just record where we are
        self.log.append("%d@%d,%d" % (r, pos.x, pos.y))
        if len(self.log) >= WATCH:
            tiles = sorted(set(s.split("@")[1] for s in self.log))
            self.say(ct, "MOVED=%s tiles=%s first=%s last=%s n=%d"
                     % (len(tiles) > 1, tiles, self.log[0], self.log[-1], len(self.log)))
