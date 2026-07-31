"""Probe: is a DIAGONAL-facing Gunner legal on 2.3.3, and what does its ray look like?

`bot/siege.py` ranks firing positions over EIGHT facings, on the 2.2.0 belief that a Gunner's
r^2 = 13 attack pattern reaches 2 tiles along a diagonal (2, 8 <= 13 < 18). If `build_gunner`
rejects a diagonal Direction on 2.3.3 the planner can propose a tile the executor can never
build, and the rush executor retries the same illegal build forever.

Runs on `duel`. One builder walks to open ground, then:
  D1  can_build_gunner over all 8 directions + CENTRE, from the same target tile
  D2  actually build_gunner facing NORTHEAST, and read get_attackable_tiles_from() on it
  D3  the same for EAST, as the cardinal control
Only the Builder Bot reports (M07): everything is read from the builder, never from the turret.
"""

from fcode import Controller, Direction, EntityType, Position

DIRS = (Direction.NORTH, Direction.NORTHEAST, Direction.EAST, Direction.SOUTHEAST,
        Direction.SOUTH, Direction.SOUTHWEST, Direction.WEST, Direction.NORTHWEST)
TAGS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")


class Player:
    def __init__(self):
        self.n = []
        self.spawned = False
        self.phase = 0
        self.home = None

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.n.append("TOP:" + type(exc).__name__ + str(exc)[:30])

    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            if not self.spawned:
                for d in (Direction.EAST, Direction.NORTH, Direction.SOUTH, Direction.WEST):
                    p = ct.get_position().add(d)
                    try:
                        if ct.can_spawn(p):
                            ct.spawn_builder(p)
                            self.spawned = True
                            return
                    except Exception:
                        continue
            return
        if et == EntityType.GUNNER:
            # M07: the turret is its own reporter. `get_attackable_tiles_from` takes a signature
            # none of (pos), (id), (pos, dir), (id, pos) matches, so read the pattern from the
            # unit that owns it.
            p = ct.get_position()
            tiles = ct.get_attackable_tiles()
            off = sorted((t.x - p.x, t.y - p.y) for t in tiles)
            d2 = [o[0] * o[0] + o[1] * o[1] for o in off]
            ct.resign("NE GUNNER at %d,%d n=%d off=%s maxd2=%d" % (
                p.x, p.y, len(off), ";".join("%d,%d" % o for o in off), max(d2) if d2 else -1))
            return
        if et != EntityType.BUILDER_BOT:
            return

        pos = ct.get_position()
        if self.home is None:
            self.home = Position(pos.x, pos.y)

        # Walk a few tiles clear of the Core so every neighbour is open ground.
        if self.phase == 0:
            if abs(pos.x - self.home.x) + abs(pos.y - self.home.y) < 4:
                for d in (Direction.EAST, Direction.SOUTH, Direction.NORTH, Direction.WEST):
                    try:
                        if ct.can_move(d):
                            ct.move(d)
                            return
                    except Exception:
                        continue
                return
            self.phase = 1
            return

        if self.phase == 1:
            self.phase = 2
            t = Position(pos.x + 1, pos.y)
            row = ""
            for d in DIRS:
                try:
                    row += "1" if ct.can_build_gunner(t, d) else "0"
                except Exception:
                    row += "X"
            try:
                c = "1" if ct.can_build_gunner(t, Direction.CENTRE) else "0"
            except Exception:
                c = "X"
            self.n.append("DIRS " + "".join(TAGS[i] + row[i] for i in range(8)) + " C" + c)
            return

        if self.phase == 2:
            self.phase = 3
            t = Position(pos.x + 1, pos.y)
            try:
                ct.build_gunner(t, Direction.NORTHEAST)
                self.n.append("NEBUILD ok")
            except Exception as exc:
                self.n.append("NEBUILD " + type(exc).__name__ + ":" + str(exc)[:28])
            return

        if self.phase == 3:
            self.phase = 4
            t = Position(pos.x + 1, pos.y)
            try:
                bid = ct.get_tile_building_id(t)
                tiles = None
                for args in ((t,), (bid,), (t, Direction.NORTHEAST), (bid, t)):
                    try:
                        tiles = ct.get_attackable_tiles_from(*args)
                        break
                    except TypeError:
                        continue
                if tiles is None:
                    raise ValueError("no signature matched")
                off = sorted((p.x - t.x, p.y - t.y) for p in tiles)
                self.n.append("NERAY n=%d %s" % (
                    len(off), ";".join("%d,%d" % o for o in off[:6])))
            except Exception as exc:
                self.n.append("NERAY " + type(exc).__name__ + ":" + str(exc)[:28])
            return

        if self.phase == 4:
            self.phase = 5
            t = Position(pos.x, pos.y + 1)
            try:
                ct.build_gunner(t, Direction.EAST)
                bid = ct.get_tile_building_id(t)
                tiles = None
                for args in ((t,), (bid,), (t, Direction.NORTHEAST), (bid, t)):
                    try:
                        tiles = ct.get_attackable_tiles_from(*args)
                        break
                    except TypeError:
                        continue
                if tiles is None:
                    raise ValueError("no signature matched")
                off = sorted((p.x - t.x, p.y - t.y) for p in tiles)
                self.n.append("ERAY n=%d %s" % (
                    len(off), ";".join("%d,%d" % o for o in off[:6])))
            except Exception as exc:
                self.n.append("ERAY " + type(exc).__name__ + ":" + str(exc)[:28])
            return

        ct.resign(" | ".join(self.n[:8]))
