"""AREA 1 / GobbleGlitch probe: the SEALED KILL BOX (no terrain required).

gg_kbox proved the same-round chain (Launcher id 12 threw at r15, Gunner id 13
fired at the victim the same round) but the victim then WALKED OUT of the ray,
because enemy builders spawned early have LOW ids and move before our launcher
acts.  Fix: throw them into a cell they cannot leave.

Arena `glopen` (26x14, NO terrain anywhere).  Core A (1,6), Core B (22,6).
Attackers march west along row 5 and row 8.

    (12,1) BARRIER
(11,2) BARRIER   (12,2) CELL   (13,2) BARRIER
    (12,3) GUNNER facing NORTH  -> ray (12,2),(12,1),(12,0)

  The CELL's four cardinal neighbours are 3 barriers + the Gunner itself, so a
  Builder Bot thrown into it can never move.  The Gunner is the fourth wall AND
  the executioner: the cell is the FIRST tile of its ray, so nothing can block
  the shot.  Cost: launcher 20 + gunner 10 + 3 barriers 9 = 39 Ti, then 2 Ti of
  ammo per shot.

  LAUNCHER L = (12,5); ring includes (13,5) and (11,5) on the row-5 march lane.
  d^2(L, CELL) = 9 <= 26, so the cell is a legal throw target.

Measures: rounds per kill, ammo per kill, how many attackers die, whether the
cell ever leaks, and whether the barriers survive the prisoners' 2-dmg attacks.
"""

from fcode import Controller, Direction, EntityType, GameError, Position

LPOS = Position(12, 5)
LSTAND = Position(12, 6)
CELL = Position(12, 2)
GPOS = Position(12, 3)
GSTAND = Position(12, 4)
BARS = [Position(12, 1), Position(11, 2), Position(13, 2)]
PARK = Position(7, 10)
RING = [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)]
WALK = [Position(11, 6), Position(11, 5), Position(11, 4), Position(12, 4),
        Position(12, 3), Position(12, 2)]


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
        self.first = {}

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
            if not self.spawned and ct.can_spawn(Position(3, 6)):
                ct.spawn_builder(Position(3, 6))
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

    # stages: 0 walk to LSTAND, 1 build launcher, 2 walk to cell, 3 build bars,
    #         4 step out to GSTAND, 5 build gunner, 6 park + watch
    def _builder(self, ct, r):
        pos = ct.get_position()
        if self.stage == 0:
            if pos != LSTAND:
                self._step(ct, pos, LSTAND)
            elif ct.can_build_launcher(LPOS):
                print("LP|r%d LAUNCHER id=%d" % (r, ct.build_launcher(LPOS)))
                self.stage = 1
            return
        if self.stage == 1:
            if pos == CELL:
                self.stage = 2
                return
            if self.wi < len(WALK):
                w = WALK[self.wi]
                if pos == w:
                    self.wi += 1
                    if self.wi < len(WALK):
                        w = WALK[self.wi]
                    else:
                        return
                self._step(ct, pos, w)
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
            return
        me = ct.get_team()
        n = 0
        for uid in ct.get_nearby_units():
            if ct.get_team(uid) != me:
                n += 1
        if n and r % 25 == 0:
            print("LP|r%d BREACH n=%d" % (r, n))

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
        # do not gobble until the box is sealed: 3 barriers + the gunner
        if ct.get_tile_building_id(GPOS) is None:
            return
        for b in BARS:
            if ct.get_tile_building_id(b) is None:
                return
        if ct.get_tile_builder_bot_id(CELL) is not None:
            return
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
            if not ct.can_launch(q, CELL):
                print("LP|r%d NOLAUNCH from %s,%s" % (r, q.x, q.y))
                continue
            ct.launch(q, CELL)
            self.throws += 1
            self.first[bid] = r
            print("LP|r%d GOBBLE id%d %s,%s -> cell thr=%d" % (r, bid, q.x, q.y, self.throws))
            return

    def _gunner(self, ct, r):
        me = ct.get_team()
        bid = ct.get_tile_builder_bot_id(CELL)
        if bid is None or ct.get_team(bid) == me:
            # report barrier health now and then
            if r % 100 == 0:
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
