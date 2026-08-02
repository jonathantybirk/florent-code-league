"""Q5 part 2: can a wall of Barriers deny a turret every target, and what does it cost?

gg_los already showed that vision is a pure radius -- barriers and walls blind nothing. What a
barrier does block is the FIRING LINE. So the question becomes: how many barriers, and where, make
a Gunner unable to hit anything beyond range 1 in ANY of its eight facings?

Arena `maps/lab/ggopen.map26`. One builder puts OUR Gunner at (10,7) facing EAST, then walks the
radius-2 ring and drops a barrier on all eight tiles of the radius-1 ring:
(9,6) (10,6) (11,6) (9,7) (11,7) (9,8) (10,8) (11,8).

The Gunner reports (M07): for each of the 8 facings, can_fire_from at range 2 and range 3 (both
against a live barrier target placed at range 2 where possible), plus get_gunner_target(). It also
prints the team titanium before the ring and after, giving the exact ring price at live cost scale.

Run:  python tools/runprobe.py gg_blind --map lab/ggopen
"""

from fcode import Controller, Direction, EntityType, Position

G = Position(10, 7)
E = Direction.EAST
N = Direction.NORTH
S = Direction.SOUTH
W = Direction.WEST
GUN = EntityType.GUNNER
SPAWN = Position(3, 7)
DIRS = (Direction.NORTH, Direction.NORTHEAST, Direction.EAST, Direction.SOUTHEAST,
        Direction.SOUTH, Direction.SOUTHWEST, Direction.WEST, Direction.NORTHWEST)

# (station, build-target or None)
SCRIPT = [
    (Position(9, 7), ("gun", G)),
    (Position(9, 5), None),
    (Position(11, 5), ("bar", Position(11, 6))),
    (Position(10, 5), ("bar", Position(10, 6))),
    (Position(9, 5), ("bar", Position(9, 6))),
    (Position(8, 7), ("bar", Position(9, 7))),
    (Position(8, 8), ("bar", Position(9, 8))),
    (Position(10, 9), ("bar", Position(10, 8))),
    (Position(11, 9), ("bar", Position(11, 8))),
    (Position(12, 7), ("bar", Position(11, 7))),
    (Position(14, 7), None),
]
RING = [Position(9, 6), Position(10, 6), Position(11, 6), Position(9, 7),
        Position(11, 7), Position(9, 8), Position(10, 8), Position(11, 8)]


class Player:
    def __init__(self):
        self.n = []
        self.spawned = False
        self.s = 0
        self.ti0 = None
        self.done = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.n.append("T%d:%s:%s" % (self.s, type(exc).__name__, str(exc)[:16]))

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()
        if et == EntityType.CORE:
            if not self.spawned and ct.can_spawn(SPAWN):
                ct.spawn_builder(SPAWN)
                self.spawned = True
            return
        if et == EntityType.BUILDER_BOT:
            self._builder(ct)
            return
        if et == EntityType.GUNNER:
            self._gunner(ct, r)

    def goto(self, ct, tgt):
        pos = ct.get_position()
        if pos == tgt:
            return True
        best = None
        for d in (E, W, N, S):
            nxt = pos.add(d)
            sc = nxt.distance_squared(tgt)
            if ct.can_move(d) and (best is None or sc < best[0]):
                best = (sc, d)
        if best is not None and best[0] < pos.distance_squared(tgt):
            ct.move(best[1])
        return False

    def _builder(self, ct):
        if self.s >= len(SCRIPT):
            return
        station, act = SCRIPT[self.s]
        if not self.goto(ct, station):
            return
        if act is None:
            self.s += 1
            return
        kind, p = act
        if ct.get_tile_building_id(p) is not None:
            self.s += 1
            return
        if kind == "gun" and ct.can_build_gunner(p, E):
            ct.build_gunner(p, E)
            self.s += 1
        elif kind == "bar" and ct.can_build_barrier(p):
            ct.build_barrier(p)
            self.s += 1

    def _gunner(self, ct, r):
        if self.done:
            return
        if self.ti0 is None:
            self.ti0 = ct.get_global_resources()
        if r != 70:
            return
        self.done = True
        built = sum(1 for p in RING if ct.get_tile_building_id(p) is not None)
        r2 = ""
        r3 = ""
        r1 = ""
        for d in DIRS:
            dx, dy = d.delta()
            r1 += "1" if ct.can_fire_from(G, d, GUN, Position(G.x + dx, G.y + dy)) else "0"
            r2 += "1" if ct.can_fire_from(G, d, GUN, Position(G.x + 2 * dx, G.y + 2 * dy)) else "0"
            r3 += "1" if ct.can_fire_from(G, d, GUN, Position(G.x + 3 * dx, G.y + 3 * dy)) else "0"
        t = ct.get_gunner_target()
        self.n.append("ring=%d/8 r1=%s r2=%s r3=%s tgt=%s barCost=%d ti=%d hp=%d" % (
            built, r1, r2, r3, "-" if t is None else "%d,%d" % (t.x, t.y),
            ct.get_barrier_cost(), ct.get_global_resources(), ct.get_hp()))
        ct.resign(" | ".join(self.n)[:495])
