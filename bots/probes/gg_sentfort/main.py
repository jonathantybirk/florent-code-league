"""AREA 3b: does a SENTINEL really shoot through a solid wall, and can it kill a Core
from a position no Gunner can occupy?

Arena `sentfort` (26x22): a FULL wall column at x=12 splits the map. Core A anchor (2,10),
Core B anchor (16,10) -- footprint (16,10)(17,10)(16,11)(17,11).
A Sentinel at (11,10) facing EAST has ray (12,10)..(16,10): the last tile is the enemy Core,
and (12,10) is solid wall. No unit of either team can ever cross x=12.

Also, in a clear lane at y=16, two barriers in a row test whether a BUILDING blocks the
Sentinel's ray (it is already proven a wall does not).
"""

from fcode import Controller, Direction, EntityType, GameError, Position

E = Direction.EAST
SENT = Position(11, 10)
STAND = Position(10, 10)
TARGET = Position(16, 10)


def e(exc):
    return type(exc).__name__[:4] + ":" + str(exc)[:18]


class Player:
    def __init__(self):
        self.phase = 0
        self.spawned = False
        self.said = False
        self.shots = 0
        self.last = -1

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            print("GGPROBE|EXC " + e(exc))

    def step(self, ct, pos, tgt):
        best = None
        for d in (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST):
            if not ct.can_move(d):
                continue
            sc = pos.add(d).distance_squared(tgt)
            if best is None or sc < best[0]:
                best = (sc, d)
        if best is not None and best[0] < pos.distance_squared(tgt):
            ct.move(best[1])

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()

        if et == EntityType.CORE:
            if not self.spawned and ct.can_spawn(Position(4, 10)):
                ct.spawn_builder(Position(4, 10))
                self.spawned = True
                return
            # keep the global ammo pool topped up; 10 per Sentinel shot
            if ct.get_global_ammo() < 40 and ct.can_convert_ammo(20):
                ct.convert_ammo(20)
            return

        if et == EntityType.SENTINEL:
            if ct.can_fire(TARGET):
                a0 = ct.get_global_ammo()
                bid = ct.get_tile_building_id(TARGET)
                hp0 = ct.get_hp(bid)
                ct.fire(TARGET)
                self.shots += 1
                print("GGPROBE|SHOT %d r=%d ammo %d->%d corehp %d->%d gap=%d" % (
                    self.shots, r, a0, ct.get_global_ammo(), hp0,
                    ct.get_hp(bid), r - self.last))
                self.last = r
            elif r % 25 == 0:
                print("GGPROBE|SENT r=%d cd=%d ammo=%d canfire=%s" % (
                    r, ct.get_action_cooldown(), ct.get_global_ammo(),
                    ct.can_fire(TARGET)))
            return

        if et != EntityType.BUILDER_BOT:
            return
        pos = ct.get_position()

        if r % 20 == 0:
            print("GGPROBE|B r=%d ph=%d at=%d,%d" % (r, self.phase, pos.x, pos.y))

        if self.phase == 0:
            if pos != STAND:
                self.step(ct, pos, STAND)
                return
            if ct.get_tile_building_id(SENT) is None:
                if ct.can_build_sentinel(SENT, E):
                    ct.build_sentinel(SENT, E)
                    print("GGPROBE|BUILT sentinel r=%d ti=%d cost?" % (
                        r, ct.get_global_resources()))
                return
            out = []
            for lbl, ty in (("Gtocore", EntityType.GUNNER), ("Stocore", EntityType.SENTINEL)):
                try:
                    out.append("%s=%d" % (
                        lbl, 1 if ct.can_fire_from(SENT, E, ty, Position(13, 10)) else 0))
                except Exception as exc:
                    out.append("%s!%s" % (lbl, e(exc)))
            print("GGPROBE|WALLPEEK " + " ".join(out))
            self.phase = 5
            return

        if self.phase == 5:
            if pos != Position(9, 17):
                self.step(ct, pos, Position(9, 17))
                return
            if ct.get_tile_building_id(Position(9, 16)) is None:
                if ct.can_build_barrier(Position(9, 16)):
                    ct.build_barrier(Position(9, 16))
                return
            self.phase = 6
            return

        if self.phase == 6:
            if pos != Position(10, 17):
                self.step(ct, pos, Position(10, 17))
                return
            if ct.get_tile_building_id(Position(10, 16)) is None:
                if ct.can_build_barrier(Position(10, 16)):
                    ct.build_barrier(Position(10, 16))
                return
            self.phase = 2
            return

        if self.phase == 2:
            out = []
            for lbl, p, ty, t in (
                ("Sblock", Position(7, 16), EntityType.SENTINEL, Position(10, 16)),
                ("Gblock", Position(7, 16), EntityType.GUNNER, Position(10, 16)),
                ("Sfirst", Position(7, 16), EntityType.SENTINEL, Position(9, 16)),
            ):
                try:
                    out.append("%s=%d" % (lbl, 1 if ct.can_fire_from(p, E, ty, t) else 0))
                except Exception as exc:
                    out.append("%s!%s" % (lbl, e(exc)))
            print("GGPROBE|BLOCKTEST " + " ".join(out))
            self.phase = 3
            return
