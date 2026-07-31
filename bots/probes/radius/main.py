"""Probe G50 / G13 / G14 on 2.3.3: the Builder Bot's real action radius.

G50 (2.2.0) claimed a builder's action radius is r^2<=2, i.e. DIAGONAL BUILDS ARE LEGAL.
Every 2.3.3 docstring instead says "position must be an orthogonally adjacent tile to this
builder bot (not diagonal, not this builder bot's own tile)". Measure it.

Arena `openfield` (24x20, no ore, Core A anchor (1,9)). The builder parks at (6,9), where every
offset in [-2..2]^2 is open ground, and scans:
  R1 can_build_barrier over the 5x5 offset block   -> the build radius shape
  R2 can_heal over the same block                  -> the heal radius shape
  R3 can_fire over the same block                  -> the builder attack shape (G13/G14)
Then it actually builds at the most diagonal legal offset it found, to confirm can_* and build()
agree, and fires at an adjacent building and at its own tile.
"""

from fcode import Controller, Direction, EntityType, GameError, Position

HOME = Position(6, 9)
OFFS = [(dx, dy) for dy in (-2, -1, 0, 1, 2) for dx in (-2, -1, 0, 1, 2)]


def grid(fn):
    """Run fn over the 5x5 offset block, return 5 rows of 5 chars."""
    rows = []
    for dy in (-2, -1, 0, 1, 2):
        row = ""
        for dx in (-2, -1, 0, 1, 2):
            try:
                row += "1" if fn(dx, dy) else "0"
            except Exception:
                row += "X"
        rows.append(row)
    return ",".join(rows)


class Player:
    def __init__(self):
        self.n = []
        self.spawned = False
        self.phase = 0

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.n.append("TOP:" + type(exc).__name__ + str(exc)[:30])

    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            if not self.spawned:
                p = Position(3, 9)
                if ct.can_spawn(p):
                    ct.spawn_builder(p)
                    self.spawned = True
            return
        if et != EntityType.BUILDER_BOT:
            return

        pos = ct.get_position()
        if pos != HOME:
            d = pos.cardinal_direction_to(HOME)
            if ct.can_move(d):
                ct.move(d)
            return

        if self.phase == 0:
            self.phase = 1
            self.n.append("BUILD " + grid(
                lambda dx, dy: ct.can_build_barrier(Position(pos.x + dx, pos.y + dy))))
            self.n.append("HEAL " + grid(
                lambda dx, dy: ct.can_heal(Position(pos.x + dx, pos.y + dy))))
            self.n.append("FIRE " + grid(
                lambda dx, dy: ct.can_fire(Position(pos.x + dx, pos.y + dy))))
            return

        if self.phase == 1:
            self.phase = 2
            # Does build() agree with can_build_barrier()? Try a DIAGONAL first.
            diag = Position(pos.x + 1, pos.y + 1)
            try:
                ct.build_barrier(diag)
                self.n.append("DIAGBUILD ok at %d,%d" % (diag.x, diag.y))
            except Exception as exc:
                self.n.append("DIAGBUILD " + type(exc).__name__ + ":" + str(exc)[:34])
            return

        if self.phase == 2:
            self.phase = 3
            orth = Position(pos.x + 1, pos.y)
            try:
                ct.build_barrier(orth)
                self.n.append("ORTHBUILD ok")
            except Exception as exc:
                self.n.append("ORTHBUILD " + type(exc).__name__ + ":" + str(exc)[:30])
            return

        if self.phase == 3:
            self.phase = 4
            # G13: can a builder shoot an ORTHOGONALLY ADJACENT building?
            orth = Position(pos.x + 1, pos.y)
            bid = ct.get_tile_building_id(orth)
            hp0 = ct.get_hp(bid) if bid is not None else None
            ti0 = ct.get_global_resources()
            try:
                ct.fire(orth)
                self.n.append("ADJFIRE ok hp %s->%s dTi=%d" % (
                    hp0, ct.get_hp(bid), ct.get_global_resources() - ti0))
            except Exception as exc:
                self.n.append("ADJFIRE " + type(exc).__name__ + ":" + str(exc)[:30])
            return

        if self.phase == 4:
            self.phase = 5
            # G14: the range-0 own-tile shot.
            try:
                ct.fire(pos)
                self.n.append("SELFFIRE ok")
            except Exception as exc:
                self.n.append("SELFFIRE " + type(exc).__name__ + ":" + str(exc)[:30])
            return

        ct.resign(" | ".join(self.n[:10]))
