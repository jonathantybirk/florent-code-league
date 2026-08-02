"""DEFENCE Q1/Q8 -- can a BUILDER damage a Core, and can a builder HEAL a Core?

Arena `maps/lab/dopen.map26`, vs noop.  Core A anchor (2,5); (4,5) is a spawn-ring tile
orthogonally adjacent to footprint tile (3,5), so one builder parked there can both
`fire((3,5))` and `heal((3,5))` on our OWN Core.

Phases: r4..r33 attack (30 shots), r34..r55 heal (22 heals), report r=60.
The CORE is the reporter (M07); the builder relays its own counters through the store.
"""

from fcode import Controller, Direction, EntityType, Position

CARD = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)
SEAT = Position(4, 5)
FOOT = Position(3, 5)
S_ATK, S_HEAL, S_FLAG = 0, 1, 2
A0, A1 = 4, 33
H0, H1 = 34, 55
REPORT = 60


class Player:
    def __init__(self):
        self.hp = None
        self.atk = 0
        self.heal = 0
        self.flag = 0
        self.dset = []
        self.hset = []
        self.mark = {}

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception:
            return

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()

        if et == EntityType.CORE:
            hp = ct.get_hp()
            if self.hp is None:
                self.hp = hp
            elif hp != self.hp:
                d = hp - self.hp
                if d < 0 and d not in self.dset:
                    self.dset.append(d)
                if d > 0 and d not in self.hset:
                    self.hset.append(d)
                self.hp = hp
            if r in (3, A1 + 1, H1 + 1):
                self.mark[r] = (hp, ct.get_global_resources())
            if r == 0:
                if ct.can_spawn(SEAT):
                    ct.spawn_builder(SEAT)
                return
            if r == REPORT:
                m3 = self.mark.get(3, (0, 0))
                ma = self.mark.get(A1 + 1, (0, 0))
                mh = self.mark.get(H1 + 1, (0, 0))
                ct.resign(
                    "DBHIT atk=%d heal=%d flag=%d hp/ti r3=%s rA=%s rH=%s"
                    " dmgset=%s healset=%s"
                    % (ct.read_store(S_ATK), ct.read_store(S_HEAL),
                       ct.read_store(S_FLAG), m3, ma, mh,
                       sorted(self.dset), sorted(self.hset)))
            return

        if et != EntityType.BUILDER_BOT:
            return

        p = ct.get_position()
        if p != SEAT:
            best = None
            for d in CARD:
                if not ct.can_move(d):
                    continue
                sc = p.add(d).distance_squared(SEAT)
                if best is None or sc < best[0]:
                    best = (sc, d)
            if best is not None and best[0] < p.distance_squared(SEAT):
                ct.move(best[1])
            return

        if A0 <= r <= A1:
            if ct.can_fire(FOOT):
                self.flag = self.flag | 1
                ct.fire(FOOT)
                self.atk += 1
            ct.write_store(S_ATK, self.atk)
            ct.write_store(S_FLAG, self.flag)
            return

        if H0 <= r <= H1:
            ok = False
            try:
                ok = ct.can_heal(FOOT)
            except Exception:
                self.flag = self.flag | 8
            if ok:
                self.flag = self.flag | 2
                try:
                    ct.heal(FOOT)
                    self.heal += 1
                except Exception:
                    self.flag = self.flag | 4
            ct.write_store(S_HEAL, self.heal)
            ct.write_store(S_FLAG, self.flag)
            return
