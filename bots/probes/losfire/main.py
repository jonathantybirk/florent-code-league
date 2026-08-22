"""Can a Sentinel fire at a target with a BARRIER in the way?

The docs say a Sentinel's line is "never blocked by walls or units in the way". But firing is gated
by can_fire(), and a Barrier BLOCKS LINE OF SIGHT -- so the shot may be legal while the target is
invisible. If can_fire() gates on vision, then an opponent who rings its Core with barriers makes
the Core untargetable, and a Sentinel rush grinds the ring forever instead.

Layout, all on one row, built west to east by a retreating Builder:

    S . B . T          S = our Sentinel facing EAST
    0 1 2 3 4          B = an allied Barrier at range 2 (the LOS blocker)
                       T = an allied Barrier at range 4 (the target)

  L1  can_fire(T) with B standing            -> the question
  L2  is_in_vision(T) with B standing        -> is it vision or the fire pattern?
  L3  T in get_attackable_tiles()            -> does the raw pattern include it?
"""

from fcode import Controller, Direction, EntityType, Position

S_FIRE, S_VIS, S_PAT, S_STEP = 1, 2, 3, 4
LAST = 70


class Player:
    def __init__(self):
        self.done = False
        self.spawned = False
        self.step = 0
        self.home = None

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception:
            pass

    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            self._core(ct)
        elif et == EntityType.BUILDER_BOT:
            self._builder(ct)
        elif et == EntityType.SENTINEL:
            self._sentinel(ct)

    def _core(self, ct):
        if self.done:
            return
        r = ct.get_current_round()
        if r == 1 and not self.spawned:
            for q in ct.get_nearby_tiles(2):
                try:
                    if ct.can_spawn(q):
                        ct.spawn_builder(q)
                        self.spawned = True
                        break
                except Exception:
                    continue
        try:
            if ct.get_global_ammo() < 60 and ct.can_convert_ammo(20):
                ct.convert_ammo(20)
        except Exception:
            pass
        if r >= LAST:
            self.done = True
            ct.resign("step=%d | L1 can_fire_through_barrier=%d(1=YES 2=no) | "
                      "L2 target_in_vision=%d(1=yes 2=NO) | L3 target_in_pattern=%d(1=yes 2=no)" % (
                          ct.read_store(S_STEP), ct.read_store(S_FIRE),
                          ct.read_store(S_VIS), ct.read_store(S_PAT)))

    def _builder(self, ct):
        p = ct.get_position()
        if self.home is None:
            self.home = p
        hx, hy = self.home.x, self.home.y
        ct.write_store(S_STEP, self.step + 1)

        def east():
            try:
                if ct.can_move(Direction.EAST):
                    ct.move(Direction.EAST)
                    return True
            except Exception:
                pass
            return False

        def west():
            try:
                if ct.can_move(Direction.WEST):
                    ct.move(Direction.WEST)
                    return True
            except Exception:
                pass
            return False

        def barrier_east():
            try:
                q = Position(p.x + 1, p.y)
                if ct.can_build_barrier(q):
                    ct.build_barrier(q)
                    return True
            except Exception:
                pass
            return False

        # walk to hx+3, drop T at hx+4; back to hx+1, drop B at hx+2; back to hx-1, Sentinel at hx
        if self.step == 0:
            if p.x >= hx + 3:
                self.step = 1
            else:
                east()
                return
        if self.step == 1:
            if barrier_east():
                self.step = 2
            return
        if self.step == 2:
            if p.x <= hx + 1:
                self.step = 3
            else:
                west()
                return
        if self.step == 3:
            if barrier_east():
                self.step = 4
            return
        if self.step == 4:
            if p.x <= hx - 1:
                self.step = 5
            else:
                west()
                return
        if self.step == 5:
            try:
                q = Position(p.x + 1, p.y)
                if ct.can_build_sentinel(q, Direction.EAST):
                    ct.build_sentinel(q, Direction.EAST)
                    self.step = 6
            except Exception:
                pass
            return
        for d in (Direction.NORTH, Direction.SOUTH):
            try:
                if ct.can_move(d):
                    ct.move(d)
                    return
            except Exception:
                continue

    def _sentinel(self, ct):
        p = ct.get_position()
        target = Position(p.x + 4, p.y)
        try:
            ct.write_store(S_FIRE, 1 if ct.can_fire(target) else 2)
        except Exception:
            ct.write_store(S_FIRE, 3)
        try:
            ct.write_store(S_VIS, 1 if ct.is_in_vision(target) else 2)
        except Exception:
            ct.write_store(S_VIS, 3)
        try:
            hit = any(t.x == target.x and t.y == target.y for t in ct.get_attackable_tiles())
            ct.write_store(S_PAT, 1 if hit else 2)
        except Exception:
            ct.write_store(S_PAT, 3)
