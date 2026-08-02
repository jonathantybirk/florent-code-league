"""AREA 1 / GobbleGlitch probe: SEALED KILL BOX sited on our OWN doorstep.

gg_kbox2 built the box in midfield; the attackers had already walked past it, so
the ring was never occupied again.  Real sieges end with enemy builders parked
next to OUR Core, so put the box there: the ring is then occupied every round
and the box runs at 100% duty cycle.

Arena `glopen` (26x14, no terrain).  Core A anchor (1,6).  gl_march parks eight
builders permanently in the block x=3..6, y=5..8 (measured: r999 ids 4..11 at
(3,5)(3,7)(4,6)(4,8)(5,5)(5,7)(6,6)(6,8)).

    (5,1) BARRIER
(4,2) BARRIER  (5,2) CELL  (6,2) BARRIER
    (5,3) GUNNER facing NORTH -> ray (5,2),(5,1),(5,0)
    ...
    (5,6) LAUNCHER, ring = the 8 tiles around it, d^2(L,CELL)=16 <= 26

Total outlay: launcher 20 + gunner 10 + 3 barriers 9 = 39 Ti, plus 2 Ti of ammo
per shot.  Question: kills, ammo per kill, rounds per kill, and does the cell
ever leak?
"""

from fcode import Controller, Direction, EntityType, GameError, Position

SPAWN = Position(3, 6)
LPOS = Position(5, 6)
CELL = Position(5, 2)
GPOS = Position(5, 3)
GSTAND = Position(5, 4)
BARS = [Position(5, 1), Position(4, 2), Position(6, 2)]
PARK = Position(5, 4)
WALK1 = [Position(4, 6), Position(4, 5), Position(5, 5)]
WALK2 = [Position(5, 4), Position(5, 3), Position(5, 2)]
RING = [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)]


def en(exc):
    return type(exc).__name__ + ":" + str(exc)[:28]


class Player:
    def __init__(self):
        self.spawned = False
        self.stage = 0
        self.wi = 0
        self.kills = 0
        self.shots = 0
        self.throws = 0
        self.ringsum = 0
        self.ringn = 0

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            print("LP|TOP %s" % en(exc))

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()
        if et == EntityType.CORE:
            if r == 0 and ct.can_convert_ammo(300):
                ct.convert_ammo(300)
            if not self.spawned and ct.can_spawn(SPAWN):
                ct.spawn_builder(SPAWN)
                self.spawned = True
            return
        if et == EntityType.BUILDER_BOT:
            self._builder(ct, r)
            return
        if et == EntityType.LAUNCHER:
            self._launcher(ct, r)
            return
        if et == EntityType.GUNNER:
            self._gunner(ct, r)
            return

    def _builder(self, ct, r):
        pos = ct.get_position()
        if self.stage == 0:
            if self._follow(ct, pos, WALK1):
                if ct.can_build_launcher(LPOS):
                    print("LP|r%d LAUNCHER id=%d" % (r, ct.build_launcher(LPOS)))
                    self.stage = 1
                    self.wi = 0
            return
        if self.stage == 1:
            if self._follow(ct, pos, WALK2):
                self.stage = 2
            return
        if self.stage == 2:
            for b in BARS:
                if ct.get_tile_building_id(b) is None:
                    if ct.can_build_barrier(b):
                        ct.build_barrier(b)
                        print("LP|r%d BARRIER %s,%s" % (r, b.x, b.y))
                    return
            self.stage = 3
            return
        if self.stage == 3:
            if pos != GSTAND:
                self._step(ct, pos, GSTAND)
            elif ct.can_build_gunner(GPOS, Direction.NORTH):
                print("LP|r%d GUNNER id=%d SEALED" % (r, ct.build_gunner(GPOS, Direction.NORTH)))
                self.stage = 4
            return
        if pos != PARK:
            self._step(ct, pos, PARK)

    def _follow(self, ct, pos, path):
        if self.wi >= len(path):
            return True
        w = path[self.wi]
        if pos == w:
            self.wi += 1
            if self.wi >= len(path):
                return True
            w = path[self.wi]
        self._step(ct, pos, w)
        return False

    def _step(self, ct, pos, goal):
        dx = goal.x - pos.x
        dy = goal.y - pos.y
        opts = []
        if abs(dx) >= abs(dy):
            if dx:
                opts.append(Direction.EAST if dx > 0 else Direction.WEST)
            if dy:
                opts.append(Direction.SOUTH if dy > 0 else Direction.NORTH)
        else:
            if dy:
                opts.append(Direction.SOUTH if dy > 0 else Direction.NORTH)
            if dx:
                opts.append(Direction.EAST if dx > 0 else Direction.WEST)
        for d in opts:
            if ct.can_move(d):
                ct.move(d)
                return

    def _launcher(self, ct, r):
        me = ct.get_team()
        if ct.get_tile_building_id(GPOS) is None:
            return
        for b in BARS:
            if ct.get_tile_building_id(b) is None:
                return
        n = 0
        pick = None
        for dx, dy in RING:
            q = Position(LPOS.x + dx, LPOS.y + dy)
            if q.x < 0 or q.y < 0:
                continue
            try:
                bid = ct.get_tile_builder_bot_id(q)
            except Exception:
                continue
            if bid is None or ct.get_team(bid) == me:
                continue
            n += 1
            if pick is None:
                pick = (bid, q)
        self.ringsum += n
        self.ringn += 1
        if r % 100 == 0:
            print("LP|r%d RING avg=%d/100 thr=%d" % (r, self.ringsum, self.throws))
            self.ringsum = 0
        if pick is None:
            return
        if ct.get_tile_builder_bot_id(CELL) is not None:
            return
        bid, q = pick
        if not ct.can_launch(q, CELL):
            print("LP|r%d NOLAUNCH from %s,%s" % (r, q.x, q.y))
            return
        ct.launch(q, CELL)
        self.throws += 1
        print("LP|r%d GOBBLE id%d %s,%s -> cell thr=%d" % (r, bid, q.x, q.y, self.throws))

    def _gunner(self, ct, r):
        me = ct.get_team()
        bid = ct.get_tile_builder_bot_id(CELL)
        if bid is None or ct.get_team(bid) == me:
            if r % 200 == 0:
                hp = []
                for b in BARS:
                    q = ct.get_tile_building_id(b)
                    hp.append(str(ct.get_hp(q)) if q is not None else "X")
                print("LP|r%d BARS %s kills=%d shots=%d ammo=%d" % (
                    r, ",".join(hp), self.kills, self.shots, ct.get_global_ammo()))
            return
        tgt = ct.get_gunner_target()
        if tgt is None or tgt.x != CELL.x or tgt.y != CELL.y:
            print("LP|r%d TGTMISMATCH %s" % (r, "none" if tgt is None else "%d,%d" % (tgt.x, tgt.y)))
            return
        if not ct.can_fire(tgt):
            print("LP|r%d CANTFIRE ammo=%d" % (r, ct.get_global_ammo()))
            return
        hp0 = ct.get_hp(bid)
        ct.fire(tgt)
        self.shots += 1
        try:
            hp1 = ct.get_hp(bid)
            alive = "y"
        except Exception:
            hp1 = 0
            alive = "DEAD"
            self.kills += 1
        print("LP|r%d SHOT id%d hp %d->%d %s kills=%d shots=%d ammo=%d" % (
            r, bid, hp0, hp1, alive, self.kills, self.shots, ct.get_global_ammo()))
