"""Gunner ROTATION economics and SELF-DESTRUCT side effects.

Arena `maps/lab/gunline.map26` (24x16), Core A anchor (2,7) -> footprint (2,7)(3,7)(2,8)(3,8).

  d1  Does rotate() really cost a flat 10 Ti at any cost scale?
  d2  Does rotate() add to the global cost scale the way building does?
  d3  Can a gunner rotate to the direction it already faces?
  d4  What is the action cooldown after a rotation -- how many firing rounds does it cost?
  e1  Does self_destruct() give the cost scale back?
  e2  Does it free the 50-unit cap?

REPAIRED 2026-08-02. Every finding used to leave through print(), which is swallowed
(G29), so this probe produced nothing at all -- it was one of the ~59 lost to the first
hunt. Only ONE unit can report (M07) and the rotation ledger lives on the GUNNER, so the
Gunner is now the reporter and resigns at round 80. The extra builder relays its
pre-self-destruct cost scale through store slot 0 (one-round write lag, G20), which is the
only cross-unit channel that exists, then removes itself at round 50 so the Gunner's r60
and r80 rows show whether the scale or the unit count came back.
"""

from fcode import Controller, Direction, EntityType, GameError, Position

E = Direction.EAST
N = Direction.NORTH
S = Direction.SOUTH
CARD = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)
GUN = Position(7, 6)
EXTRA = Position(4, 6)
SLOT = 0


def e(exc):
    return type(exc).__name__[:4] + ":" + str(exc)[:18]


class Player:
    def __init__(self):
        self.n = []
        self.first = None
        self.phase = 0
        self.rot = 0
        self.done = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.n.append("EXC" + e(exc))

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
            if r == 0 and ct.can_spawn(Position(4, 7)):
                ct.spawn_builder(Position(4, 7))
            if r == 30 and ct.can_spawn(EXTRA):
                ct.spawn_builder(EXTRA)
            return

        if et == EntityType.GUNNER:
            if self.rot == 0:
                self.rot = 1
                ti0 = ct.get_global_resources()
                sc0 = ct.get_scale_percent()
                out = ["face=%s" % ct.get_direction(),
                       "same_can=%s" % ct.can_rotate(E),
                       "diff_can=%s" % ct.can_rotate(N)]
                try:
                    ct.rotate(E)
                    out.append("rot_same=ok")
                except Exception as exc:
                    out.append("rot_same!" + e(exc))
                ct.rotate(N)
                out.append("dTi=%d dScale=%.1f cd=%d face=%s" % (
                    ct.get_global_resources() - ti0,
                    ct.get_scale_percent() - sc0,
                    ct.get_action_cooldown(), ct.get_direction()))
                self.n.append("ROT1 r=%d " % r + " ".join(out))
                return
            if self.rot == 1:
                self.rot = 2
                self.n.append("ROT1b r=%d cd=%d canrotS=%s" % (
                    r, ct.get_action_cooldown(), ct.can_rotate(S)))
                return
            if self.rot == 2 and r >= 60:
                self.rot = 3
                ti0 = ct.get_global_resources()
                sc0 = ct.get_scale_percent()
                ct.rotate(S)
                self.n.append("ROT2 r=%d dTi=%d dScale=%.1f uc=%d bldcost=%d preSD=%d" % (
                    r, ct.get_global_resources() - ti0,
                    ct.get_scale_percent() - sc0, ct.get_unit_count(),
                    ct.get_builder_bot_cost(), ct.read_store(SLOT)))
                return
            if self.rot == 3 and r >= 80 and not self.done:
                self.done = True
                ct.resign(("GGECON " + " | ".join(self.n) +
                           " | r80 sc=%.1f uc=%d bld=%d gun=%d" % (
                               ct.get_scale_percent(), ct.get_unit_count(),
                               ct.get_builder_bot_cost(), ct.get_gunner_cost()))[:495])
            return

        if et != EntityType.BUILDER_BOT:
            return
        pos = ct.get_position()
        if self.first is None:
            self.first = (r <= 1)

        if not self.first:
            # the extra builder: publish the pre-self-destruct scale, then remove itself
            if r == 49:
                ct.write_store(SLOT, int(ct.get_scale_percent()))
                return
            if r == 50:
                ct.self_destruct()
            return

        if self.phase == 0:
            if pos != Position(6, 6):
                self.step(ct, pos, Position(6, 6))
                return
            if ct.can_build_gunner(GUN, E):
                ct.build_gunner(GUN, E)
                self.phase = 1
            return
        if self.phase == 1 and pos != Position(6, 9):
            self.step(ct, pos, Position(6, 9))
