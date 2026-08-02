"""The SENTINEL PILLBOX: a turret walled in on all four sides that still kills a Core.

Arena `sentbox` (26x20). A solid wall column at x=12 for every y except y=9.
Core A anchor (2,9). Core B anchor (16,9) -> footprint (16,9)(17,9)(16,10)(17,10).
Walls at (11,8), (11,10), (13,9), (14,9).

Build order:
  1. walk to (11,9), build a BARRIER at (12,9)        <- plugs the only hole in the wall
  2. step west to (10,9), build a SENTINEL at (11,9) facing EAST
  3. step west to (9,9),  build a BARRIER at (10,9)   <- seals the sentinel in

The sentinel is then enclosed by wall N, wall S, our own barrier E and our own barrier W.
Nothing of either team can ever stand next to it, and no unit of either team can cross
x=12 at all. Its EAST ray is (12,9) barrier, (13,9) wall, (14,9) wall, (15,9) empty,
(16,9) enemy Core.

Measures: whether it fires, what it hits, and whether the Core dies.
"""

from fcode import Controller, Direction, EntityType, GameError, Position

E = Direction.EAST
CARD = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)
PLUG = Position(12, 9)
SENT = Position(11, 9)
SEAL = Position(10, 9)
TARGET = Position(16, 9)
EMPTYTILE = Position(15, 9)


def e(exc):
    return type(exc).__name__[:4] + ":" + str(exc)[:20]


class Player:
    def __init__(self):
        self.spawned = False
        self.phase = 0
        self.shots = 0
        self.last = -1
        self.probed = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            print("GGPROBE|EXC %s" % e(exc))

    def step(self, ct, pos, tgt):
        best = None
        for d in CARD:
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
            if not self.spawned and ct.can_spawn(Position(4, 9)):
                ct.spawn_builder(Position(4, 9))
                self.spawned = True
                return
            if ct.get_global_ammo() < 30 and ct.can_convert_ammo(20):
                ct.convert_ammo(20)
            return

        if et == EntityType.SENTINEL:
            if not self.probed:
                self.probed = True
                out = []
                for lbl, p in (("core", TARGET), ("empty15", EMPTYTILE),
                               ("wall13", Position(13, 9)),
                               ("ownbarrier12", PLUG), ("core17", Position(17, 9)),
                               ("coreS", Position(16, 10))):
                    try:
                        out.append("%s=%d" % (lbl, 1 if ct.can_fire(p) else 0))
                    except Exception as exc:
                        out.append("%s!%s" % (lbl, e(exc)))
                try:
                    ts = ct.get_attackable_tiles()
                    out.append("attk=" + ",".join("%d:%d" % (t.x, t.y) for t in ts))
                except Exception as exc:
                    out.append("attk!%s" % e(exc))
                print("GGPROBE|SENTPROBE r=%d %s" % (r, " ".join(out)))
            if ct.can_fire(TARGET):
                a0 = ct.get_global_ammo()
                bid = ct.get_tile_building_id(TARGET)
                hp0 = ct.get_hp(bid)
                ct.fire(TARGET)
                self.shots += 1
                if self.shots < 4 or self.shots % 7 == 0:
                    print("GGPROBE|SHOT %d r=%d ammo %d->%d hp %d->%d gap=%d" % (
                        self.shots, r, a0, ct.get_global_ammo(), hp0,
                        ct.get_hp(bid), r - self.last))
                self.last = r
            return

        if et != EntityType.BUILDER_BOT:
            return
        pos = ct.get_position()

        if self.phase == 0:
            if pos != SENT:
                self.step(ct, pos, SENT)
                return
            if ct.get_tile_building_id(PLUG) is None:
                if ct.can_build_barrier(PLUG):
                    ct.build_barrier(PLUG)
                    print("GGPROBE|PLUG r=%d" % r)
                return
            self.phase = 1
            return

        if self.phase == 1:
            if pos != SEAL:
                self.step(ct, pos, SEAL)
                return
            if ct.get_tile_building_id(SENT) is None:
                if ct.can_build_sentinel(SENT, E):
                    ti0 = ct.get_global_resources()
                    ct.build_sentinel(SENT, E)
                    print("GGPROBE|SENTBUILT r=%d ti %d->%d" % (
                        r, ti0, ct.get_global_resources()))
                return
            self.phase = 2
            return

        if self.phase == 2:
            if pos != Position(9, 9):
                self.step(ct, pos, Position(9, 9))
                return
            if ct.get_tile_building_id(SEAL) is None:
                if ct.can_build_barrier(SEAL):
                    ct.build_barrier(SEAL)
                    print("GGPROBE|SEAL r=%d sentinel now enclosed" % r)
                return
            self.phase = 3
            print("GGPROBE|ENCLOSED r=%d" % r)
            return

        if self.phase == 3 and r % 100 == 0:
            print("GGPROBE|IDLE r=%d ti=%d ammo=%d" % (
                r, ct.get_global_resources(), ct.get_global_ammo()))
