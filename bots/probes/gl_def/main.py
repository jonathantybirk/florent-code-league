"""AREA 1 / probe 3: the DEFENSIVE launcher, on arena `glbox`.

Layout (26x14, Core A anchor (1,6), Core B anchor (22,6)):
  LAUNCHER at (10,6). Its pickup ring (r^2<=2) covers the 8 tiles around it.
  GUNNER   at (9,3) facing SOUTH -> ray (9,4),(9,5),(9,6).
  SEALED POCKET at (12,2): the tile is EMPTY but walled on all four sides
  ((12,1),(11,2),(13,2),(12,3) are terrain WALL), so nothing can walk out of it.
  d^2 from the Launcher to the pocket = 2^2 + 4^2 = 20 <= 26, so it is a legal throw.

Tests
  T1  Throw the first enemy builder into the SEALED POCKET. Is the target legal?
      Does it land there? Does it EVER leave? (log its tile + HP every round)
  T2  Throw every later enemy builder into the GUNNER's ray at (9,4) and let the
      team-blind Gunner shoot it. How many rounds to a kill, at what ammo cost?
  T3  Log HP immediately before and after a throw -- does displacement damage?
"""

from fcode import Controller, Direction, EntityType, GameError, Position

LPOS = Position(10, 6)
GPOS = Position(9, 3)
GSTAND = Position(9, 4)
POCKET = Position(12, 2)
RAY_FAR = Position(9, 4)
PARK = Position(7, 8)
RING = [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)]


def en(exc):
    return type(exc).__name__ + ":" + str(exc)[:28]


class Player:
    def __init__(self):
        self.spawned = False
        self.stage = 0
        self.pocketed = None
        self.kills = 0

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            print("LP|TOP %s" % en(exc))

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()
        if et == EntityType.CORE:
            if r == 0 and ct.can_convert_ammo(200):
                ct.convert_ammo(200)
            if not self.spawned and ct.can_spawn(Position(3, 6)):
                ct.spawn_builder(Position(3, 6))
                self.spawned = True
            return

        if et == EntityType.BUILDER_BOT:
            self._builder(ct)
            return

        if et == EntityType.LAUNCHER:
            self._launcher(ct, r)
            return

        if et == EntityType.GUNNER:
            self._gunner(ct, r)
            return

    # ---- builder: put down one launcher and one gunner, then hide ----
    def _builder(self, ct):
        pos = ct.get_position()
        if self.stage == 0:
            if pos != Position(9, 6):
                self._step(ct, pos, Position(9, 6))
                return
            if ct.can_build_launcher(LPOS):
                ct.build_launcher(LPOS)
                self.stage = 1
            return
        if self.stage == 1:
            if pos != GSTAND:
                self._step(ct, pos, GSTAND)
                return
            if ct.can_build_gunner(GPOS, Direction.SOUTH):
                ct.build_gunner(GPOS, Direction.SOUTH)
                self.stage = 2
            return
        if pos != PARK:
            self._step(ct, pos, PARK)

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

    # ---- the defensive launcher ----
    def _launcher(self, ct, r):
        me = ct.get_team()
        # keep watching the prisoner
        if self.pocketed is not None:
            try:
                p = ct.get_position(self.pocketed)
                print("LP|r%d PRISONER id%d at %s,%s hp=%s" % (
                    r, self.pocketed, p.x, p.y, ct.get_hp(self.pocketed)))
            except Exception as exc:
                print("LP|r%d PRISONER id%d GONE %s" % (r, self.pocketed, en(exc)))
                self.pocketed = None

        targets = []
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
            targets.append((bid, q))
        if not targets:
            return
        bid, q = targets[0]
        hp0 = ct.get_hp(bid)
        if self.pocketed is None:
            dest = POCKET
            what = "POCKET"
        else:
            dest = RAY_FAR
            what = "RAY"
        try:
            ok = ct.can_launch(q, dest)
        except Exception as exc:
            print("LP|r%d canlaunch %s ERR %s" % (r, what, en(exc)))
            return
        if not ok:
            print("LP|r%d %s illegal from %s,%s (n=%d)" % (r, what, q.x, q.y, len(targets)))
            return
        ct.launch(q, dest)
        try:
            p2 = ct.get_position(bid)
            hp1 = ct.get_hp(bid)
            land = ct.get_tile_builder_bot_id(dest)
        except Exception as exc:
            print("LP|r%d THROW %s id%d post-read ERR %s" % (r, what, bid, en(exc)))
            return
        print("LP|r%d THROW %s id%d %s,%s -> %s,%s hp %d->%d landed=%s n_in_ring=%d" % (
            r, what, bid, q.x, q.y, p2.x, p2.y, hp0, hp1, land == bid, len(targets)))
        if what == "POCKET":
            self.pocketed = bid

    # ---- team-safe gunner: only shoot tiles holding an ENEMY builder ----
    def _gunner(self, ct, r):
        tgt = ct.get_gunner_target()
        if tgt is None:
            return
        me = ct.get_team()
        try:
            bid = ct.get_tile_builder_bot_id(tgt)
        except Exception:
            return
        if bid is None or ct.get_team(bid) == me:
            return
        if not ct.can_fire(tgt):
            return
        hp0 = ct.get_hp(bid)
        ct.fire(tgt)
        try:
            hp1 = ct.get_hp(bid)
            alive = "y"
        except Exception:
            hp1 = -1
            alive = "DEAD"
            self.kills += 1
        print("LP|r%d GUN id%d at %s,%s hp %d->%d %s ammo=%d kills=%d" % (
            r, bid, tgt.x, tgt.y, hp0, hp1, alive, ct.get_global_ammo(), self.kills))
