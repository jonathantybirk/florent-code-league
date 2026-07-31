"""Probe: what exactly gates a turret shot on the global ammo pool?

Does can_fire() know about ammo, or does only fire() raise? A gunner policy that trusts
can_fire() will throw uncaught GameErrors (and G23 says an uncaught exception deletes the unit).

Arena `openfield`: gunner(8,9) facing EAST at a friendly barrier(9,9).
The Core converts exactly 1 ammo at r30 and 1 more at r40, so the gunner is observed at
ammo 0, ammo 1 (below the 2 needed) and ammo 2.
"""

from fcode import Controller, Direction, EntityType, GameError, Position

HOME = Position(7, 9)
GUN = Position(8, 9)
BAR = Position(9, 9)

SCRIPT = [
    ("gun", GUN, Direction.EAST),
    ("mv", Direction.NORTH, None),
    ("mv", Direction.EAST, None),
    ("mv", Direction.EAST, None),
    ("bar", BAR, None),
    ("mv", Direction.NORTH, None),
]


def e(exc):
    return type(exc).__name__ + ":" + str(exc)[:22]


class Player:
    def __init__(self):
        self.n = []
        self.spawned = False
        self.step = 0

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
                if ct.can_spawn(Position(3, 9)):
                    ct.spawn_builder(Position(3, 9))
                    self.spawned = True
                return
            if r in (30, 40) and ct.can_convert_ammo(1):
                ct.convert_ammo(1)
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
        elif kind == "bar":
            if ct.can_build_barrier(a):
                ct.build_barrier(a)
                ok = True
        if ok:
            self.step += 1

    def _gunner(self, ct, r):
        if r not in (25, 35, 45):
            return
        ammo = ct.get_global_ammo()
        t = ct.get_gunner_target()
        ts = "None" if t is None else "%d,%d" % (t.x, t.y)
        cf = "n/a" if t is None else str(ct.can_fire(t))
        res = "skip"
        if t is not None:
            try:
                ct.fire(t)
                res = "FIRED->ammo%d" % ct.get_global_ammo()
            except Exception as exc:
                res = e(exc)
        self.n.append("r%d ammo=%d tgt=%s canfire=%s %s" % (r, ammo, ts, cf, res))
        if r == 45:
            ct.resign(" | ".join(self.n[:6]))
