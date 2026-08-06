"""VERIFY probe, side A: the id-race WINNER, now with its own healer, so both
sides field one Sentinel plus one adjacent healing builder.

maps/lab/firstshot.map26.  Spawn schedule makes the entity ids interleave
1=coreA 2=coreB 3=builderA 4=builderB 5=healerA 6=healerB 7=turretA 8=turretB,
so BOTH healers act before EITHER turret fires and the two sides are exactly
symmetric apart from the id tie-break.

healerA parks at (6,5) -- orthogonally adjacent to A's turret at (6,4) and off
the y=4 lane that B's Sentinel covers ((8,4)..(4,4)).  Pairs with du_hl_b, whose
healer parks at the mirrored tile (9,5).

A's turret builder parks at (5,3) and relays both turret HPs through the store
slots; the CORE resigns with the trace (resign() is the only output channel).
"""

from fcode import Controller, Direction, EntityType, Position

SPAWN = Position(3, 4)
HSPAWN = Position(3, 5)
TPOS = Position(6, 4)
ETPOS = Position(9, 4)
HPOS = Position(6, 5)
FACING = Direction.EAST
WALK = Direction.EAST
BUILD_ROUND = 20
HEAL_FROM = 21
RESIGN_ROUND = 60
LOG_FROM = 18

T_SHOTS, T_LASTFIRE, T_ID = 0, 1, 2
B_ID, B_TID, B_OHP, B_EHP, B_EID, H_N = 3, 4, 5, 6, 7, 8


def _w(ct, slot, val):
    try:
        ct.write_store(slot, max(0, min(4294967295, int(val))))
    except Exception:
        pass


class Player:
    def __init__(self):
        self.err = []
        self.spawned = 0
        self.log = []
        self.last = None
        self.dead_own = "-"
        self.dead_foe = "-"
        self.step = 0
        self.role = None
        self.heals = 0
        self.shots = 0
        self.lastfire = -1

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            if len(self.err) < 6:
                self.err.append("%s:%s" % (type(exc).__name__, str(exc)[:50]))

    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            self._core(ct)
        elif et == EntityType.BUILDER_BOT:
            self._builder(ct)
        elif et in (EntityType.SENTINEL, EntityType.GUNNER):
            self._turret(ct)

    def _core(self, ct):
        r = ct.get_current_round()
        self._sample(ct, r)
        if self.spawned == 0 and r >= 2 and ct.can_spawn(SPAWN):
            ct.spawn_builder(SPAWN)
            self.spawned = 1
            return
        if self.spawned == 1 and r >= 3 and ct.can_spawn(HSPAWN):
            ct.spawn_builder(HSPAWN)
            self.spawned = 2
            return
        try:
            if (ct.get_global_ammo() < 300 and ct.get_global_resources() > 200
                    and ct.can_convert_ammo(50)):
                ct.convert_ammo(50)
        except Exception:
            pass

    def _sample(self, ct, r):
        try:
            v = tuple(ct.read_store(i) for i in range(9))
        except Exception:
            return
        hp = (v[B_OHP], v[B_EHP])
        if hp != self.last and r >= LOG_FROM:
            f = lambda x: (x - 1) if x else "x"          # noqa: E731
            self.log.append("%d:%s/%s" % (r - 1, f(hp[0]), f(hp[1])))
            if hp[0] == 0 and self.last and self.last[0]:
                self.dead_own = r - 1
            if hp[1] == 0 and self.last and self.last[1]:
                self.dead_foe = r - 1
            self.last = hp
        elif self.last is None:
            self.last = hp
        if r >= RESIGN_ROUND:
            d = lambda i: v[i] - 1 if v[i] else "x"      # noqa: E731
            head = ("HM|A|bid%s|tid%s|eid%s|sh%s|lf%s|heals%s|dOWN%s|dFOE%s|E%s|HP "
                    % (d(B_ID), d(B_TID), d(B_EID), d(T_SHOTS), d(T_LASTFIRE),
                       d(H_N), self.dead_own, self.dead_foe, ";".join(self.err[:2])))
            body = " ".join(self.log)
            ct.resign((head + body)[:490])

    def _builder(self, ct):
        if self.role is None:
            self.role = "turret" if ct.get_id() <= 4 else "healer"
        if self.role == "healer":
            self._healer(ct)
            return

        r = ct.get_current_round()
        _w(ct, B_ID, ct.get_id() + 1)
        for tile, slot in ((TPOS, B_OHP), (ETPOS, B_EHP)):
            try:
                b = ct.get_tile_building_id(tile)
                _w(ct, slot, (ct.get_hp(b) + 1) if b is not None else 0)
                if tile == ETPOS and b is not None:
                    _w(ct, B_EID, b + 1)
            except Exception:
                pass

        if self.step < 2:
            if ct.can_move(WALK):
                ct.move(WALK)
                self.step += 1
            return
        if self.step == 2:
            if r < BUILD_ROUND:
                return
            try:
                if not ct.can_build_sentinel(TPOS, FACING):
                    return
                _w(ct, B_TID, ct.build_sentinel(TPOS, FACING) + 1)
            except Exception as exc:
                self.err.append("B:%s" % str(exc)[:30])
                return
            self.step = 3
            return
        if self.step == 3:
            if ct.can_move(Direction.NORTH):
                ct.move(Direction.NORTH)
            self.step = 4
            return

    def _healer(self, ct):
        r = ct.get_current_round()
        pos = ct.get_position()
        if pos != HPOS:
            if pos.x < HPOS.x and ct.can_move(Direction.EAST):
                ct.move(Direction.EAST)
            return
        if r < HEAL_FROM:
            return
        try:
            if ct.can_heal(TPOS):
                ct.heal(TPOS)
                self.heals += 1
                _w(ct, H_N, self.heals + 1)
        except Exception as exc:
            if len(self.err) < 6:
                self.err.append("H:%s" % str(exc)[:30])

    def _turret(self, ct):
        r = ct.get_current_round()
        try:
            b = ct.get_tile_building_id(ETPOS)
            if b is not None and ct.can_fire(ETPOS):
                ct.fire(ETPOS)
                self.shots += 1
                self.lastfire = r
        except Exception as exc:
            if len(self.err) < 6:
                self.err.append("F:%s" % str(exc)[:30])
        _w(ct, T_SHOTS, self.shots + 1)
        _w(ct, T_LASTFIRE, self.lastfire + 1)
