"""DEFENCE Q3/Q4 -- does a BARRIER block a turret's line to the Core, and how fast is it cleared?

Arena `maps/lab/dopen.map26`, vs noop.  Core A anchor (2,5).  A builder builds a GUNNER at
(6,5) facing WEST; its ray is (5,5)(4,5)(3,5) and (3,5) is our own Core footprint (turret
APIs are team-blind, G10, so this measures exactly what an ENEMY gunner would see).

The builder then plants a BARRIER at (5,5), the first tile of that ray.  The GUNNER is the
reporter: it records its target and `can_fire(core)` before and after the barrier appears,
then grinds the barrier down and records how many shots that took and what it sees next.
"""

from fcode import Controller, Direction, EntityType, Position

CARD = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)
GUN = Position(6, 5)
STAND = Position(6, 6)
SEAT2 = Position(5, 6)
BARR = Position(5, 5)
CORE = Position(3, 5)
SPAWN = Position(4, 7)
BUILD_BARR_AT = 10


def pt(p):
    if p is None:
        return "-"
    return "%d,%d" % (p.x, p.y)


class Player:
    def __init__(self):
        self.phase = 0
        self.pre = None
        self.post = None
        self.seen = False
        self.built_r = -1
        self.shots = 0
        self.hpseq = []
        self.after = None
        self.tiles = ""
        self.done = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception:
            return

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
            if r == 0:
                if ct.can_spawn(SPAWN):
                    ct.spawn_builder(SPAWN)
                return
            if r == 1 and ct.can_convert_ammo(120):
                ct.convert_ammo(120)
            return

        if et == EntityType.BUILDER_BOT:
            p = ct.get_position()
            if self.phase == 0:
                if p == STAND:
                    if ct.can_build_gunner(GUN, Direction.WEST):
                        ct.build_gunner(GUN, Direction.WEST)
                        self.phase = 1
                    return
                self.step(ct, p, STAND)
                return
            if self.phase == 1:
                if r < BUILD_BARR_AT:
                    if p != SEAT2:
                        self.step(ct, p, SEAT2)
                    return
                if ct.can_build_barrier(BARR):
                    ct.build_barrier(BARR)
                    self.phase = 2
                return
            if p != Position(8, 8):
                self.step(ct, p, Position(8, 8))
            return

        if et != EntityType.GUNNER:
            return

        bid = ct.get_tile_building_id(BARR)
        if self.tiles == "":
            self.tiles = ",".join(pt(t) for t in ct.get_attackable_tiles())

        if bid is None and not self.seen:
            self.pre = "%s|cfcore=%d" % (pt(ct.get_gunner_target()),
                                        1 if ct.can_fire(CORE) else 0)
            return

        if bid is not None and not self.seen:
            self.seen = True
            self.built_r = r
            self.post = "%s|cfcore=%d|cfbarr=%d" % (
                pt(ct.get_gunner_target()), 1 if ct.can_fire(CORE) else 0,
                1 if ct.can_fire(BARR) else 0)

        if bid is not None:
            if ct.can_fire(BARR):
                ct.fire(BARR)
                self.shots += 1
                nb = ct.get_tile_building_id(BARR)
                self.hpseq.append(ct.get_hp(nb) if nb is not None else 0)
            return

        if self.after is None:
            self.after = "%s|cfcore=%d r=%d" % (pt(ct.get_gunner_target()),
                                                1 if ct.can_fire(CORE) else 0, r)
            ct.resign("DLOS tiles=[%s] PRE=%s BUILT=r%d POST=%s shots=%d hp=%s AFTER=%s"
                      % (self.tiles, self.pre, self.built_r, self.post,
                         self.shots, self.hpseq, self.after))
