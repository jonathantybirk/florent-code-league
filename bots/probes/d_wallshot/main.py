"""DEFENCE Q3 -- does terrain WALL stop a Sentinel, when a barrier does not?

`d_sent2` showed a Sentinel firing straight through an allied BARRIER at its target without
scratching the barrier.  The remaining question is whether map terrain behaves the same, because
if a Sentinel ignores walls too then no static obstacle of any kind protects a Core from one.

Arena `maps/lab/dwall.map26` (20x12, one WALL tile at (6,5), rot180 twin at (13,6)).
SENTINEL at (9,5) facing WEST: line (8,5)(7,5)(6,5)=WALL,(5,5)(4,5).
GUNNER   at (8,5) facing WEST: line (7,5)(6,5)=WALL,(5,5)   -- the control, since gunners are
known to be blocked by buildings (d_los).
A BARRIER is planted at (5,5), on the far side of the wall from both turrets.

The SENTINEL is the reporter (M07).
"""

from fcode import Controller, Direction, EntityType, Position

DIRS = {(0, -1): Direction.NORTH, (1, 0): Direction.EAST,
        (0, 1): Direction.SOUTH, (-1, 0): Direction.WEST}
ROUTE = [(5, 7), (5, 6)]
ROUTE2 = [(6, 6), (7, 6), (8, 6), (9, 6)]
TARGET = Position(5, 5)
SENT = Position(9, 5)
REPORT = 40


class Player:
    def __init__(self):
        self.spawned = False
        self.leg = 0
        self.st = 0
        self.note = None
        self.shots = 0
        self.hps = []

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception:
            return

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()

        if et == EntityType.CORE:
            if not self.spawned:
                if ct.can_spawn(Position(4, 7)):
                    ct.spawn_builder(Position(4, 7))
                    self.spawned = True
                return
            if ct.get_global_ammo() < 40 and ct.can_convert_ammo(120):
                ct.convert_ammo(120)
            return

        if et == EntityType.BUILDER_BOT:
            p = ct.get_position()
            if self.st > 1:
                return
            route = ROUTE if self.st == 0 else ROUTE2
            if self.leg < len(route) and (p.x, p.y) == route[self.leg]:
                self.leg += 1
            if self.leg < len(route):
                t = route[self.leg]
                d = DIRS.get((t[0] - p.x, t[1] - p.y))
                if d is not None and ct.can_move(d):
                    ct.move(d)
                return
            if self.st == 0:
                if ct.can_build_barrier(TARGET):
                    ct.build_barrier(TARGET)
                    self.st = 1
                    self.leg = 0
                return
            if ct.can_build_sentinel(SENT, Direction.WEST):
                ct.build_sentinel(SENT, Direction.WEST)
                self.st = 2
            return

        if et != EntityType.SENTINEL:
            return

        bid = ct.get_tile_building_id(TARGET)
        if self.note is None:
            g = 0
            try:
                g = 1 if ct.can_fire_from(Position(8, 5), Direction.WEST,
                                          EntityType.GUNNER, TARGET) else 0
            except Exception:
                g = 9
            s = 0
            try:
                s = 1 if ct.can_fire_from(Position(9, 5), Direction.WEST,
                                          EntityType.SENTINEL, TARGET) else 0
            except Exception:
                s = 9
            self.note = "r%d tiles=%d cf=%d gun_from85=%d sent_from95=%d" % (
                r, len(ct.get_attackable_tiles()),
                1 if ct.can_fire(TARGET) else 0, g, s)
        if bid is not None and ct.can_fire(TARGET):
            ct.fire(TARGET)
            self.shots += 1
            nb = ct.get_tile_building_id(TARGET)
            self.hps.append(ct.get_hp(nb) if nb is not None else 0)
        if r == REPORT:
            ct.resign("DWALLSHOT %s shots=%d hp=%s" % (self.note, self.shots, self.hps))
