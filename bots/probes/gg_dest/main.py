"""Does destroy() give the cost scale back the way self_destruct() does, and is destroy free?

Arena `gunline` (24x16), Core A anchor (2,7), ore at (8,7) and (8,9).

  1  build conveyor, conveyor, barrier (+1pp each) and read the scale after each
  2  destroy all three IN ONE ROUND (destroy is documented as not costing action cooldown)
     and read the scale after each destroy
  3  build a harvester on ore (+5pp), read scale, destroy it, read scale
  4  can_destroy on our own Core footprint tile
  5  does an ORE tile block a Gunner's firing line?  (barrier target behind ore vs
     the same geometry over clear ground)
"""

from fcode import Controller, Direction, EntityType, GameError, Position

E = Direction.EAST
CARD = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)


def e(exc):
    return type(exc).__name__[:4] + ":" + str(exc)[:22]


def sc(ct):
    return "%.1f" % ct.get_scale_percent()


class Player:
    def __init__(self):
        self.spawned = False
        self.phase = 0
        self.log = []

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
            s = pos.add(d).distance_squared(tgt)
            if best is None or s < best[0]:
                best = (s, d)
        if best is not None and best[0] < pos.distance_squared(tgt):
            ct.move(best[1])

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()
        if et == EntityType.CORE:
            if not self.spawned and ct.can_spawn(Position(4, 7)):
                ct.spawn_builder(Position(4, 7))
                self.spawned = True
            return
        if et != EntityType.BUILDER_BOT:
            return
        pos = ct.get_position()

        if self.phase == 0:
            if pos != Position(5, 7):
                self.step(ct, pos, Position(5, 7))
                return
            self.phase = 1
            print("GGPROBE|P0 r=%d scale=%s ti=%d units=%d" % (
                r, sc(ct), ct.get_global_resources(), ct.get_unit_count()))
            return

        if self.phase == 1:
            if ct.can_build_conveyor(Position(5, 6), E):
                ct.build_conveyor(Position(5, 6), E)
                print("GGPROBE|B1 conv scale=%s ti=%d" % (sc(ct), ct.get_global_resources()))
                self.phase = 2
            return
        if self.phase == 2:
            if ct.can_build_conveyor(Position(5, 8), E):
                ct.build_conveyor(Position(5, 8), E)
                print("GGPROBE|B2 conv scale=%s ti=%d" % (sc(ct), ct.get_global_resources()))
                self.phase = 3
            return
        if self.phase == 3:
            if ct.can_build_barrier(Position(6, 7)):
                ct.build_barrier(Position(6, 7))
                print("GGPROBE|B3 barr scale=%s ti=%d cd=%d" % (
                    sc(ct), ct.get_global_resources(), ct.get_action_cooldown()))
                self.phase = 4
            return

        if self.phase == 4:
            self.phase = 5
            out = ["cd0=%d" % ct.get_action_cooldown(), "scale=%s" % sc(ct),
                   "core_candestroy=%s" % ct.can_destroy(Position(3, 7))]
            for p in (Position(5, 6), Position(5, 8), Position(6, 7)):
                try:
                    ti0 = ct.get_global_resources()
                    ct.destroy(p)
                    out.append("des(%d,%d) scale=%s dTi=%d cd=%d" % (
                        p.x, p.y, sc(ct), ct.get_global_resources() - ti0,
                        ct.get_action_cooldown()))
                except Exception as exc:
                    out.append("des(%d,%d)!%s" % (p.x, p.y, e(exc)))
            print("GGPROBE|DESTROY3 r=%d %s" % (r, " ".join(out)))
            return

        if self.phase == 5:
            if pos != Position(7, 7):
                self.step(ct, pos, Position(7, 7))
                return
            if ct.can_build_harvester(Position(8, 7)):
                ct.build_harvester(Position(8, 7))
                print("GGPROBE|HARV scale=%s ti=%d" % (sc(ct), ct.get_global_resources()))
                self.phase = 6
            return
        if self.phase == 6:
            self.phase = 7
            ti0 = ct.get_global_resources()
            ct.destroy(Position(8, 7))
            print("GGPROBE|HARVDES scale=%s dTi=%d cd=%d" % (
                sc(ct), ct.get_global_resources() - ti0, ct.get_action_cooldown()))
            return

        if self.phase == 7:
            # ore-LOS: put a barrier target behind the ore at (8,7) and one on clear ground
            if ct.can_build_barrier(Position(7, 6)):
                ct.build_barrier(Position(7, 6))
            self.phase = 8
            return
        if self.phase == 8:
            if pos != Position(8, 6):
                self.step(ct, pos, Position(8, 6))
                return
            if ct.get_tile_building_id(Position(9, 6)) is None:
                if ct.can_build_barrier(Position(9, 6)):
                    ct.build_barrier(Position(9, 6))
                return
            self.phase = 9
            return
        if self.phase == 9:
            if pos != Position(9, 7):
                self.step(ct, pos, Position(9, 7))
                return
            if ct.get_tile_building_id(Position(10, 7)) is None:
                if ct.can_build_barrier(Position(10, 7)):
                    ct.build_barrier(Position(10, 7))
                return
            self.phase = 10
            return
        if self.phase == 10:
            self.phase = 11
            out = []
            # (7,6) barrier is 3 east of (4,6): clear ground control
            for lbl, p, t, ty in (
                    ("clear3", Position(6, 6), Position(9, 6), EntityType.GUNNER),
                    ("overore", Position(7, 7), Position(10, 7), EntityType.GUNNER),
                    ("overoreS", Position(7, 7), Position(10, 7), EntityType.SENTINEL),
                    ("oretile", Position(7, 7), Position(8, 7), EntityType.GUNNER)):
                try:
                    out.append("%s=%d" % (lbl, 1 if ct.can_fire_from(p, E, ty, t) else 0))
                except Exception as exc:
                    out.append("%s!%s" % (lbl, e(exc)))
            print("GGPROBE|ORELOS r=%d %s scale=%s" % (r, " ".join(out), sc(ct)))
            ct.resign("GGP|dest done")
