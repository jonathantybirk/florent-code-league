"""Two leftovers: does bare ORE block a Gunner's ray, and can a TURRET self-destruct?

Arena `gunline` (24x16), Core A anchor (2,7), ore at (8,7) and (8,9).

  ORE-LOS   barrier target at (9,9) behind the bare ore tile (8,9);
            control barrier at (9,10) with two empty tiles in front.
            Both queried from tiles that put nothing else in the ray.
  TURRET    a gunner is built at (6,5) facing NORTH, prints the scale, then calls
            self_destruct(); the builder reads the scale again afterwards.
  STAND     is a bare ore tile passable / buildable-on for a builder bot?
"""

from fcode import Controller, Direction, EntityType, Environment, GameError, Position

E = Direction.EAST
N = Direction.NORTH
CARD = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)
ROUTE = [Position(9, 8), Position(8, 8), Position(7, 8), Position(7, 9),
         Position(7, 10), Position(8, 10), Position(8, 11)]


def e(exc):
    return type(exc).__name__[:4] + ":" + str(exc)[:22]


class Player:
    def __init__(self):
        self.spawned = False
        self.phase = 0
        self.i = 0
        self.said = False

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

        if et == EntityType.GUNNER:
            if not self.said:
                self.said = True
                print("GGPROBE|GUNSD r=%d scale=%.1f units=%d -> self_destruct" % (
                    r, ct.get_scale_percent(), ct.get_unit_count()))
                ct.self_destruct()
            return

        if et != EntityType.BUILDER_BOT:
            return
        pos = ct.get_position()

        if self.phase == 0:
            if pos != Position(5, 5):
                self.step(ct, pos, Position(5, 5))
                return
            if ct.can_build_gunner(Position(6, 5), N):
                ct.build_gunner(Position(6, 5), N)
                print("GGPROBE|GUNBUILT r=%d scale=%.1f" % (r, ct.get_scale_percent()))
                self.phase = 1
            return

        if self.phase == 1:
            if r < 12:
                return
            print("GGPROBE|AFTERSD r=%d scale=%.1f units=%d gunner_gone=%s" % (
                r, ct.get_scale_percent(), ct.get_unit_count(),
                ct.get_tile_building_id(Position(6, 5)) is None))
            out = ["orestand=%s" % ct.is_tile_passable(Position(8, 7)),
                   "oreempty=%s" % ct.is_tile_empty(Position(8, 7)),
                   "orebarr=%s" % ct.can_build_barrier(Position(8, 7))]
            print("GGPROBE|ORESTAND r=%d %s" % (r, " ".join(out)))
            self.phase = 2
            return

        if self.phase == 2:
            if pos != Position(9, 8):
                self.step(ct, pos, Position(9, 8))
                return
            if ct.get_tile_building_id(Position(9, 9)) is None:
                if ct.can_build_barrier(Position(9, 9)):
                    ct.build_barrier(Position(9, 9))
                return
            self.phase = 3
            return

        if self.phase == 3:
            if pos != Position(8, 10):
                self.step(ct, pos, ROUTE[self.i] if self.i < len(ROUTE) else Position(8, 10))
                if pos == ROUTE[min(self.i, len(ROUTE) - 1)]:
                    self.i += 1
                return
            if ct.get_tile_building_id(Position(9, 10)) is None:
                if ct.can_build_barrier(Position(9, 10)):
                    ct.build_barrier(Position(9, 10))
                return
            self.phase = 4
            return

        if self.phase == 4:
            if pos != Position(8, 12):
                self.step(ct, pos, Position(8, 12))
                return
            self.phase = 5
            out = []
            for lbl, p, t, ty in (
                    ("control", Position(6, 10), Position(9, 10), EntityType.GUNNER),
                    ("overore", Position(6, 9), Position(9, 9), EntityType.GUNNER),
                    ("overoreSENT", Position(6, 9), Position(9, 9), EntityType.SENTINEL)):
                try:
                    out.append("%s=%d" % (lbl, 1 if ct.can_fire_from(p, E, ty, t) else 0))
                except Exception as exc:
                    out.append("%s!%s" % (lbl, e(exc)))
            b9 = ct.get_tile_building_id(Position(9, 9))
            b10 = ct.get_tile_building_id(Position(9, 10))
            print("GGPROBE|ORELOS r=%d %s | b99=%s b910=%s ore89=%s" % (
                r, " ".join(out), b9, b10, ct.get_tile_env(Position(8, 9))))
            ct.resign("GGP|misc done")
