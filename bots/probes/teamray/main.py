"""Probe G10 / G11 on 2.3.3: turret team-blindness and friendly-in-ray jamming.

`ammo_belt` already showed a Gunner grinding down our OWN barrier, so G10 survives for the
fire path. This isolates the targeting path:

Arena `openfield`. Builder builds gunner(8,9) facing EAST, then a FRIENDLY conveyor at (9,9)
(distance 1, in the ray) and a FRIENDLY barrier at (11,9) (distance 3, behind it).
  T1 does get_gunner_target() return the friendly conveyor at (9,9)?
  T2 is can_fire() on the barrier BEHIND the friendly False?
  T3 does the friendly stay the target indefinitely, or is it skipped?
  T4 is the friendly in get_attackable_tiles()?
"""

from fcode import Controller, Direction, EntityType, GameError, Position

HOME = Position(7, 9)
GUN = Position(8, 9)
CONV = Position(9, 9)
BAR = Position(11, 9)

SCRIPT = [
    ("gun", GUN, Direction.EAST),
    ("mv", Direction.NORTH, None),      # (7,9)->(7,8)
    ("mv", Direction.EAST, None),       # ->(8,8)
    ("mv", Direction.EAST, None),       # ->(9,8)
    ("conv", CONV, Direction.EAST),     # south of (9,8)
    ("mv", Direction.EAST, None),       # ->(10,8)
    ("mv", Direction.EAST, None),       # ->(11,8)
    ("bar", BAR, None),                 # south of (11,8)
    ("mv", Direction.NORTH, None),      # clear the lane
]


def e(exc):
    return type(exc).__name__ + ":" + str(exc)[:24]


class Player:
    def __init__(self):
        self.n = []
        self.spawned = False
        self.step = 0
        self.seen = []
        self.done = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.n.append("TOP:" + e(exc))

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()
        if et == EntityType.CORE:
            if not self.spawned:
                p = Position(3, 9)
                if ct.can_spawn(p):
                    ct.spawn_builder(p)
                    self.spawned = True
                return
            if r == 30 and ct.can_convert_ammo(40):
                ct.convert_ammo(40)
            return
        if et == EntityType.BUILDER_BOT:
            self._builder(ct)
            return
        if et == EntityType.GUNNER:
            self._gunner(ct, r)

    def _builder(self, ct):
        pos = ct.get_position()
        if self.step == 0 and pos != HOME:
            d = pos.cardinal_direction_to(HOME)
            if ct.can_move(d):
                ct.move(d)
            return
        if self.step >= len(SCRIPT):
            return
        kind, a, b = SCRIPT[self.step]
        ok = False
        if kind == "mv":
            if ct.can_move(a):
                ct.move(a)
                ok = True
        elif kind == "gun":
            if ct.can_build_gunner(a, b):
                ct.build_gunner(a, b)
                ok = True
        elif kind == "conv":
            if ct.can_build_conveyor(a, b):
                ct.build_conveyor(a, b)
                ok = True
        elif kind == "bar":
            if ct.can_build_barrier(a):
                ct.build_barrier(a)
                ok = True
        if ok:
            self.step += 1

    def _gunner(self, ct, r):
        if r in (25, 29, 35, 60, 95) and len(self.n) < 8:
            t = ct.get_gunner_target()
            ts = "None" if t is None else "%d,%d" % (t.x, t.y)
            cb = ct.get_tile_building_id(BAR)
            cc = ct.get_tile_building_id(CONV)
            self.n.append("r%d tgt=%s fireBAR=%s ammo=%d convHP=%s barHP=%s" % (
                r, ts, ct.can_fire(BAR), ct.get_global_ammo(),
                "-" if cc is None else ct.get_hp(cc),
                "-" if cb is None else ct.get_hp(cb)))
        if r == 29 and not self.done:
            self.done = True
            at = ct.get_attackable_tiles()
            self.n.append("T4 natt=%d convIn=%s barIn=%s" % (
                len(at), CONV in at, BAR in at))
        # let it shoot freely once ammo exists
        if r > 30:
            t = ct.get_gunner_target()
            if t is not None and ct.can_fire(t):
                ct.fire(t)
        if r == 96:
            ct.resign(" | ".join(self.n[:8]))
