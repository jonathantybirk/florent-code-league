"""Sentinel damage, reload and line semantics -- the three numbers the rush timing rests on.

Builds two allied barriers in a row, then a Sentinel four tiles west of them facing EAST, and
fires at the NEAR barrier while watching the FAR one.

  R4  gap between successful fire() calls          -> the real reload
  R5  far barrier HP                              -> 20 means fire() hits ONLY the named tile
  R7  near barrier HP after each shot             -> damage per shot
Everything is relayed through the store; each unit is its own interpreter.
"""

from fcode import Controller, Direction, EntityType, Position

S_GAP, S_FAR, S_NEAR, S_SHOTS, S_STEP = 2, 3, 6, 7, 8
LAST = 80


class Player:
    def __init__(self):
        self.done = False
        self.spawned = False
        self.step = 0
        self.home = None
        self.fired = []

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
            if ct.get_global_ammo() < 80 and ct.can_convert_ammo(20):
                ct.convert_ammo(20)
        except Exception:
            pass
        if r >= LAST:
            self.done = True
            ct.resign("builder_step=%d shots=%d | R4 reload_gap=%d | R5 FAR_hp=%d (20=only named tile hit) "
                      "| R7 NEAR_hp=%d (20-hp = dmg/shot) | scale_pct=%.0f ti=%d ammo=%d" % (
                          ct.read_store(S_STEP), ct.read_store(S_SHOTS), ct.read_store(S_GAP),
                          ct.read_store(S_FAR), ct.read_store(S_NEAR),
                          ct.get_scale_percent(), ct.get_global_resources(), ct.get_global_ammo()))

    def _builder(self, ct):
        p = ct.get_position()
        if self.home is None:
            self.home = p
        hx, hy = self.home.x, self.home.y
        ct.write_store(S_STEP, self.step + 1)

        def go(dx):
            d = Direction.EAST if dx > 0 else Direction.WEST
            try:
                if ct.can_move(d):
                    ct.move(d)
                    return True
            except Exception:
                pass
            return False

        def build_barrier_east():
            q = Position(p.x + 1, p.y)
            try:
                if ct.can_build_barrier(q):
                    ct.build_barrier(q)
                    return True
            except Exception:
                pass
            return False

        # 0: walk to hx+2   1: barrier at hx+3   2: back to hx+1   3: barrier at hx+2
        # 4: back to hx-1   5: sentinel at hx facing EAST   6: idle south
        if self.step == 0:
            if p.x >= hx + 2:
                self.step = 1
            else:
                go(+1)
                return
        if self.step == 1:
            if build_barrier_east():
                self.step = 2
            return
        if self.step == 2:
            if p.x <= hx + 1:
                self.step = 3
            else:
                go(-1)
                return
        if self.step == 3:
            if build_barrier_east():
                self.step = 4
            return
        if self.step == 4:
            if p.x <= hx - 1:
                self.step = 5
            else:
                go(-1)
                return
        if self.step == 5:
            q = Position(p.x + 1, p.y)
            try:
                if ct.can_build_sentinel(q, Direction.EAST):
                    ct.build_sentinel(q, Direction.EAST)
                    self.step = 6
            except Exception:
                pass
            return
        for d in (Direction.SOUTH, Direction.NORTH):
            try:
                if ct.can_move(d):
                    ct.move(d)
                    return
            except Exception:
                continue

    def _sentinel(self, ct):
        r = ct.get_current_round()
        p = ct.get_position()

        def hp_at(q):
            try:
                b = ct.get_tile_building_id(q)
                return ct.get_hp(b) if b is not None else -1
            except Exception:
                return -1

        near, far = Position(p.x + 2, p.y), Position(p.x + 3, p.y)
        n, f = hp_at(near), hp_at(far)
        if n >= 0:
            ct.write_store(S_NEAR, n)
        if f >= 0:
            ct.write_store(S_FAR, f)
        if n <= 0:
            return
        try:
            if ct.can_fire(near):
                ct.fire(near)
                self.fired.append(r)
                ct.write_store(S_SHOTS, len(self.fired))
                if len(self.fired) >= 2:
                    ct.write_store(S_GAP, self.fired[-1] - self.fired[-2])
        except Exception:
            pass
