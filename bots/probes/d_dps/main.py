"""DEFENCE Q1 -- what damages a Core, and how fast.  Arena `maps/lab/dopen.map26`, vs noop.

dopen is 20x12, rot180, Core A anchor (2,5) -> footprint (2,5)(3,5)(2,6)(3,6).
Turret APIs are team-blind (G10), so we can measure Core damage WITHOUT a second bot:
a builder spawns at (4,7), walks to (6,6) and builds a GUNNER at (6,5) facing WEST.
The Gunner's 3-tile ray is (5,5)(4,5)(3,5); (3,5) is our OWN Core footprint.

The CORE is the reporter (M07): it alone reads its own HP every round and resigns at
round 60, before the 50th shot would kill it.
"""

from fcode import Controller, Direction, EntityType, Position

CARD = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)
GUN = Position(6, 5)
STAND = Position(6, 6)
SPAWN = Position(4, 7)
TARGET = Position(3, 5)
AWAY = Position(8, 7)
REPORT = 45


class Player:
    def __init__(self):
        self.built = False
        self.hp = None
        self.first = -1
        self.last = -1
        self.hits = 0
        self.tot = 0
        self.deltas = []
        self.gaps = []

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
            hp = ct.get_hp()
            if self.hp is None:
                self.hp = hp
            elif hp != self.hp:
                if self.first < 0:
                    self.first = r
                else:
                    self.gaps.append(r - self.last)
                self.last = r
                self.hits += 1
                self.tot += self.hp - hp
                if (self.hp - hp) not in self.deltas:
                    self.deltas.append(self.hp - hp)
                self.hp = hp
            if r == 0:
                if ct.can_spawn(SPAWN):
                    ct.spawn_builder(SPAWN)
                return
            if r == 1 and ct.can_convert_ammo(150):
                ct.convert_ammo(150)
                return
            if r == REPORT:
                gs = []
                for g in self.gaps:
                    if g not in gs:
                        gs.append(g)
                ct.resign(
                    "DDPS first=%d last=%d hits=%d totdmg=%d hp=%d/500 dmgset=%s gapset=%s"
                    " ti=%d ammo=%d gcost=%d"
                    % (self.first, self.last, self.hits, self.tot, self.hp,
                       sorted(self.deltas), sorted(gs),
                       ct.get_global_resources(), ct.get_global_ammo(),
                       ct.get_gunner_cost()))
            return

        if et == EntityType.BUILDER_BOT:
            p = ct.get_position()
            if not self.built:
                if p == STAND:
                    if ct.can_build_gunner(GUN, Direction.WEST):
                        ct.build_gunner(GUN, Direction.WEST)
                        self.built = True
                    return
                self.step(ct, p, STAND)
                return
            if p != AWAY:
                self.step(ct, p, AWAY)
            return

        if et == EntityType.GUNNER:
            if ct.can_fire(TARGET):
                ct.fire(TARGET)
            return
