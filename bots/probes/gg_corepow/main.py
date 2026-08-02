"""AREA 3a: what can a CORE actually DO?  CORE_ACTION_RADIUS_SQ = 8 and nobody uses it.

Arena `corelab` (26x22): Core A anchor (6,9), footprint (6,9)(7,9)(6,10)(7,10).
Ore at (4,7) -- d^2 = 8 from footprint tile (6,9), i.e. exactly on the action radius.
Ore at (9,12) -- d^2 = 8 from footprint tile (7,10).

Round 0 calls every non-info Controller method FROM THE CORE and records the outcome.
"""

from fcode import Controller, Direction, EntityType, GameError, Position


def e(exc):
    return type(exc).__name__[:4] + ":" + str(exc)[:20]


class Player:
    def __init__(self):
        self.n = []
        self.done = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.n.append("TOP:" + e(exc))

    def _run(self, ct):
        if ct.get_entity_type() != EntityType.CORE or self.done:
            return
        r = ct.get_current_round()
        if r != 0:
            return
        self.done = True
        p = ct.get_position()
        far = Position(p.x + 3, p.y)      # (9,9): d^2=4 from footprint (7,9)
        ore = Position(p.x - 2, p.y - 2)  # (4,7): d^2=8 from footprint (6,9)

        def t(label, fn):
            try:
                v = fn()
                self.n.append("%s=%s" % (label, str(v)[:16]))
            except Exception as exc:
                self.n.append("%s!%s" % (label, e(exc)))

        t("bar", lambda: ct.can_build_barrier(far))
        t("cnv", lambda: ct.can_build_conveyor(far, Direction.EAST))
        t("gun", lambda: ct.can_build_gunner(far, Direction.EAST))
        t("hrv", lambda: ct.can_build_harvester(ore))
        t("lau", lambda: ct.can_build_launcher(far))
        t("heal", lambda: ct.can_heal(far))
        t("des", lambda: ct.can_destroy(far))
        t("fire", lambda: ct.can_fire(far))
        t("atk", lambda: len(ct.get_attackable_tiles()))
        t("lnch", lambda: ct.can_launch(far, far))
        t("rot", lambda: ct.can_rotate(Direction.EAST))
        t("mov", lambda: ct.can_move(Direction.EAST))
        ct.resign("GGP|" + "|".join(self.n))
