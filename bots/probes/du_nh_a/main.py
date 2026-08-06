"""VERIFY probe, side A: the control half of the "does a healer beat build order"
duel on maps/lab/firstshot.map26.

A is the side that WINS the entity-id race: A's core (id 1) acts before B's core
(id 2), so A's builder holds id 3 and A's Sentinel is created before B's on the
same round and holds the lower turret id.  Under the bare 1v1 duel that is
supposed to be decisive (A survives at 4/40).

A does nothing special: one builder, one Sentinel at (6,4) facing EAST, strict
turret-only targeting.  A's builder parks at (5,3) -- off the y=4 firing line,
d^2 = 2 to its own turret and 17 to the enemy turret, both inside
BUILDER_BOT_VISION_RADIUS_SQ = 20 -- and relays both turret HPs through the
store slots so the CORE can resign with the full trace (resign() is the only
output channel; see HARNESS.md).
"""

from fcode import Controller, Direction, EntityType, Position

SPAWN = Position(3, 4)
BPOS = Position(5, 4)
TPOS = Position(6, 4)
ETPOS = Position(9, 4)
OBS = Position(5, 3)
FACING = Direction.EAST
WALK = Direction.EAST
SPAWN_ROUND = 1
BUILD_ROUND = 20
RESIGN_ROUND = 60
LOG_FROM = 18

T_SHOTS, T_LASTFIRE, T_ID = 0, 1, 2
B_ID, B_TID, B_OHP, B_EHP, B_EID = 3, 4, 5, 6, 7


def _w(ct, slot, val):
    try:
        ct.write_store(slot, max(0, min(4294967295, int(val))))
    except Exception:
        pass


class Player:
    def __init__(self):
        self.err = []
        self.spawned = None
        self.log = []
        self.last = None
        self.dead_own = "-"
        self.dead_foe = "-"
        self.step = 0
        self.shots = 0
        self.lastfire = -1
        self.first = None

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
        if self.spawned is None and r >= SPAWN_ROUND:
            if ct.can_spawn(SPAWN):
                self.spawned = ct.spawn_builder(SPAWN)
                return
        try:
            if (ct.get_global_ammo() < 300 and ct.get_global_resources() > 200
                    and ct.can_convert_ammo(50)):
                ct.convert_ammo(50)
        except Exception:
            pass

    def _sample(self, ct, r):
        try:
            v = tuple(ct.read_store(i) for i in range(8))
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
            head = ("HEAL|A|bid%s|tid%s|eid%s|sh%s|lf%s|dOWN%s|dFOE%s|E%s|HP "
                    % (d(B_ID), d(B_TID), d(B_EID), d(T_SHOTS), d(T_LASTFIRE),
                       self.dead_own, self.dead_foe, ";".join(self.err[:2])))
            body = " ".join(self.log)
            ct.resign((head + body)[:490])

    def _builder(self, ct):
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

    def _turret(self, ct):
        r = ct.get_current_round()
        if self.first is None:
            self.first = r
            _w(ct, T_ID, ct.get_id() + 1)
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
