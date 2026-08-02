"""A4-RING -- does filling a Core's 12-tile ring with buildings deny EVERY gunner lane onto it?

Claim under test: a 2x2 Core footprint is surrounded by exactly 12 tiles (the 4x4 block minus the
footprint). Every straight gunner line -- cardinal or diagonal -- that reaches a footprint tile must
pass through one of those 12. Buildings both BLOCK and ABSORB a gunner shot (see the 2.3.3
`can_fire`/`can_fire_from` docstrings), and a gunner cannot be built on an occupied tile. So if all
12 ring tiles hold a building, there should be ZERO (position, facing) pairs anywhere on the board
from which a hypothetical Gunner could fire at the Core.

Measured with `can_fire_from(pos, facing, GUNNER, footprint_tile)`, which the engine documents as
"uses the current map state for occupancy and walls" -- i.e. the exact ballistic question, asked
without having to build anything.

Reported by the CORE (M07: only one unit's notes survive), through resign (G29/M06).
"""

from fcode import Controller, Direction, EntityType, Position

DIRS8 = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST,
         Direction.NORTHEAST, Direction.SOUTHEAST, Direction.SOUTHWEST, Direction.NORTHWEST)
CARD = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)

S_X, S_Y = 0, 1
N_BUILDERS = 4
MEASURE_1 = 3
MEASURE_2 = 160


def foot_of(a):
    return ((a[0], a[1]), (a[0] + 1, a[1]), (a[0], a[1] + 1), (a[0] + 1, a[1] + 1))


def ring_of(a, w, h):
    f = set(foot_of(a))
    out = []
    for dx in range(-1, 3):
        for dy in range(-1, 3):
            t = (a[0] + dx, a[1] + dy)
            if t in f:
                continue
            if 0 <= t[0] < w and 0 <= t[1] < h:
                out.append(t)
    return out


class Player:
    def __init__(self):
        self.notes = []
        self.spawned = 0
        self.core = None

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

    # ---- core: publisher, spawner, measurer, reporter ----
    def _core(self, ct):
        p = ct.get_position()
        ct.write_store(S_X, p.x + 1)
        ct.write_store(S_Y, p.y + 1)
        a = (p.x, p.y)
        r = ct.get_current_round()
        if r == MEASURE_1:
            self.notes.append("EMPTY " + self._measure(ct, a))
        if r == MEASURE_2:
            self.notes.append("FULL " + self._measure(ct, a))
            ct.resign(" | ".join(self.notes))
            return
        if self.spawned >= N_BUILDERS:
            return
        if ct.get_action_cooldown() != 0:
            return
        if ct.get_global_resources() < ct.get_builder_bot_cost() + 60:
            return
        for t in ring_of(a, ct.get_map_width(), ct.get_map_height()):
            tp = Position(t[0], t[1])
            try:
                if ct.can_spawn(tp):
                    ct.spawn_builder(tp)
                    self.spawned += 1
                    return
            except Exception:
                continue

    def _measure(self, ct, a):
        w, h = ct.get_map_width(), ct.get_map_height()
        foot = foot_of(a)
        pairs = 0
        tiles = 0
        blocked_site = 0
        for dx in range(-5, 7):
            for dy in range(-5, 7):
                x, y = a[0] + dx, a[1] + dy
                if not (0 <= x < w and 0 <= y < h):
                    continue
                if (x, y) in foot:
                    continue
                pos = Position(x, y)
                occ = None
                try:
                    occ = ct.get_tile_building_id(pos)
                except Exception:
                    occ = None
                if occ is not None:
                    # cannot build a turret on an occupied tile -- not a real firing position
                    blocked_site += 1
                    continue
                hit = 0
                for d in DIRS8:
                    for f in foot:
                        ok = False
                        try:
                            ok = ct.can_fire_from(pos, d, EntityType.GUNNER,
                                                  Position(f[0], f[1]))
                        except Exception:
                            ok = False
                        if ok:
                            pairs += 1
                            hit = 1
                            break
                tiles += hit
        occ = 0
        holes = []
        for t in ring_of(a, w, h):
            b = None
            bot = None
            try:
                b = ct.get_tile_building_id(Position(t[0], t[1]))
                bot = ct.get_tile_builder_bot_id(Position(t[0], t[1]))
            except Exception:
                b = None
            if b is not None:
                occ += 1
            else:
                holes.append("%d,%d%s" % (t[0] - a[0], t[1] - a[1],
                                          "*" if bot is not None else ""))
        # spot check: a Gunner two tiles due north of the anchor, facing SOUTH, on to (ax,ay)
        spot = "?"
        try:
            spot = str(ct.can_fire_from(Position(a[0], a[1] - 2), Direction.SOUTH,
                                        EntityType.GUNNER, Position(a[0], a[1])))
        except Exception:
            spot = "err"
        return "lanes=%d sites=%d ringocc=%d/%d n2south=%s holes[%s]" % (
            pairs, tiles, occ, len(ring_of(a, w, h)), spot, " ".join(holes))

    # ---- builders: brick every ring tile, standing outside the ring ----
    def _builder(self, ct):
        pos = ct.get_position()
        if self.core is None:
            x, y = ct.read_store(S_X), ct.read_store(S_Y)
            if x <= 0 or y <= 0:
                return
            self.core = (x - 1, y - 1)
        w, h = ct.get_map_width(), ct.get_map_height()
        a = self.core
        ring = ring_of(a, w, h)
        rset = set(ring)
        fset = set(foot_of(a))
        todo = []
        for t in ring:
            b = None
            try:
                b = ct.get_tile_building_id(Position(t[0], t[1]))
            except Exception:
                b = None
            if b is None:
                todo.append(t)
        if not todo:
            return
        # A builder standing ON a ring tile can never brick the tile under it (G59), so get out
        # of the ring first -- otherwise the last two tiles are the two bodies holding them open.
        here = (pos.x, pos.y)
        if here in rset and ct.get_move_cooldown() == 0:
            for d in CARD:
                n = pos.add(d)
                if (n.x, n.y) in rset or (n.x, n.y) in fset:
                    continue
                if not (0 <= n.x < w and 0 <= n.y < h):
                    continue
                try:
                    if ct.can_move(d):
                        ct.move(d)
                        return
                except Exception:
                    continue
        todo.sort(key=lambda t: abs(t[0] - pos.x) + abs(t[1] - pos.y))
        # build if one is orthogonally adjacent
        if ct.get_action_cooldown() == 0:
            for t in todo:
                if abs(t[0] - pos.x) + abs(t[1] - pos.y) != 1:
                    continue
                tp = Position(t[0], t[1])
                try:
                    if ct.can_build_barrier(tp):
                        ct.build_barrier(tp)
                        return
                except Exception:
                    continue
        # otherwise walk to an OUTSIDE stand tile for the nearest empty ring tile
        goal = None
        for t in todo:
            for d in ((0, -1), (1, 0), (0, 1), (-1, 0)):
                s = (t[0] + d[0], t[1] + d[1])
                if s in rset or s in fset:
                    continue
                if not (0 <= s[0] < w and 0 <= s[1] < h):
                    continue
                goal = s
                break
            if goal is not None:
                break
        if goal is None:
            return
        if ct.get_move_cooldown() != 0:
            return
        best, best_d = None, abs(goal[0] - pos.x) + abs(goal[1] - pos.y)
        for d in CARD:
            n = pos.add(d)
            nd = abs(goal[0] - n.x) + abs(goal[1] - n.y)
            if nd >= best_d:
                continue
            try:
                if not ct.can_move(d):
                    continue
            except Exception:
                continue
            best, best_d = d, nd
        if best is None:
            for d in CARD:
                try:
                    if ct.can_move(d):
                        best = d
                        break
                except Exception:
                    continue
        if best is not None:
            try:
                ct.move(best)
            except Exception:
                return
