"""A4SWAP -- can a builder DESTROY its own barrier and BUILD on the same tile in the SAME turn?

`destroy()` is documented as "Does not cost action cooldown". If that is literal, a sealed Core ring
can be opened for a conveyor terminal and closed again with zero frames of exposure -- which is the
only thing standing between a fully bricked ring (no turret can ever bear on the Core) and an economy
(a chain scores only by terminating on a tile orthogonally adjacent to the footprint, G02).

Arena: ringlab. Reported by the BUILDER through resign (M07).
"""

from fcode import Controller, Direction, EntityType, Position

CARD = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)
S_X, S_Y = 0, 1


class Player:
    def __init__(self):
        self.spawned = 0
        self.core = None
        self.notes = []
        self.step = 0
        self.target = None

    def run(self, ct: Controller) -> None:
        try:
            et = ct.get_entity_type()
        except Exception:
            return
        try:
            if et == EntityType.CORE:
                self._core(ct)
            elif et == EntityType.BUILDER_BOT:
                self._builder(ct)
        except Exception:
            return

    def _core(self, ct):
        p = ct.get_position()
        ct.write_store(S_X, p.x + 1)
        ct.write_store(S_Y, p.y + 1)
        if self.spawned >= 1:
            return
        if ct.get_action_cooldown() != 0:
            return
        # spawn onto the tile two north-east of the anchor's north edge so we sit OUTSIDE the ring
        t = Position(p.x, p.y - 1)
        try:
            if ct.can_spawn(t):
                ct.spawn_builder(t)
                self.spawned += 1
        except Exception:
            return

    def _builder(self, ct):
        pos = ct.get_position()
        if self.core is None:
            x, y = ct.read_store(S_X), ct.read_store(S_Y)
            if x <= 0 or y <= 0:
                return
            self.core = (x - 1, y - 1)
        a = self.core
        gate = Position(a[0], a[1] - 1)       # edge ring tile, orthogonally adjacent to (a0,a1)
        stand = Position(a[0], a[1] - 2)      # shell tile just outside it
        if self.step == 0:
            # walk out of the ring onto the shell
            if (pos.x, pos.y) == (stand.x, stand.y):
                self.step = 1
                return
            try:
                if ct.can_move(Direction.NORTH):
                    ct.move(Direction.NORTH)
            except Exception:
                return
            return
        if self.step == 1:
            try:
                ok = ct.can_build_barrier(gate)
                if ok:
                    ct.build_barrier(gate)
                    self.notes.append("barrier built")
                    self.step = 2
                else:
                    self.notes.append("barrier ILLEGAL")
                    self.step = 3
            except Exception:
                self.notes.append("barrier RAISED")
                self.step = 3
            return
        if self.step == 2:
            # the actual experiment: destroy, then build a conveyor, in ONE turn
            cd0 = ct.get_action_cooldown()
            try:
                cd = ct.can_destroy(gate)
                self.notes.append("cd0=%d can_destroy=%s" % (cd0, cd))
                ct.destroy(gate)
            except Exception:
                self.notes.append("destroy RAISED")
                self.step = 3
                return
            cd1 = ct.get_action_cooldown()
            built = "no"
            try:
                if ct.can_build_conveyor(gate, Direction.SOUTH):
                    ct.build_conveyor(gate, Direction.SOUTH)
                    built = "yes"
            except Exception:
                built = "raised"
            cd2 = ct.get_action_cooldown()
            occ = None
            try:
                occ = ct.get_tile_building_id(gate)
            except Exception:
                occ = None
            self.notes.append("cd_after_destroy=%d built_same_turn=%s cd_after_build=%d occ=%s"
                              % (cd1, built, cd2, occ is not None))
            self.step = 3
            return
        if self.step == 3:
            ct.resign(" | ".join(self.notes))
