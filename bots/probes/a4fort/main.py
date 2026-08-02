"""A4FORT -- the cheapest thing that beats a forward-Gunner rush: brick your own Core ring.

MECHANISM (proved by bots/probes/a4ring on arena `ringlab`):
    ringocc  0/12 -> 38 buildable tiles on the board can fire a Gunner at our Core (46 pos/facing pairs)
    ringocc 12/12 -> 0 tiles, 0 pairs.
A 2x2 Core footprint is bounded by exactly 12 tiles. EVERY straight Gunner or Sentinel line -- cardinal
or diagonal -- that ends on a footprint tile passes through one of them, and a building both BLOCKS the
line and ABSORBS the shot. Occupy all 12 and no turret anywhere on the map has a legal shot at the Core.
Twelve Barriers cost about 48-60 titanium out of a 500 titanium opening bank.

The exchange rate afterwards is the point. A Gunner needs 3 shots (6 Ti of ammunition, 3 rounds) to
clear one 30 HP Barrier; a Builder Bot standing outside the ring puts it back for 3-5 Ti in ONE action,
and can also heal it 4 HP for 1 Ti. So a defender with two menders keeps a ring closed against more
lanes than an attacker can afford to open, and the attacker's damage into the Core is exactly zero for
as long as that holds.

This build is deliberately DUMB: no map memory, no symmetry inference, no pathing beyond greedy
cardinal steps, no offence at all. ~250 lines against AutistimusPrime's 3200.
"""

from fcode import Controller, Direction, EntityType, Position

CARD = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)

S_X, S_Y, S_ORD = 0, 1, 2

N_BUILDERS = 5
# Titanium kept back so the ring always has money. A Barrier is the cheapest thing on the board and
# the only thing standing between their Gunner and our Core.
SPAWN_RESERVE = 40


def foot_of(a):
    return ((a[0], a[1]), (a[0] + 1, a[1]), (a[0], a[1] + 1), (a[0] + 1, a[1] + 1))


def ring_of(a, w, h):
    """The 12 tiles touching a 2x2 footprint (G63), bounds-checked (G64a: Cores touch borders)."""
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
        self.spawned = 0
        self.ordinal = None
        self.core = None
        self.ring = None
        self.rset = frozenset()
        self.fset = frozenset()

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
            elif et == EntityType.GUNNER:
                self._gunner(ct)
        except Exception:
            return

    # ------------------------------------------------------------------
    def _core(self, ct):
        p = ct.get_position()
        ct.write_store(S_X, p.x + 1)
        ct.write_store(S_Y, p.y + 1)
        a = (p.x, p.y)
        w, h = ct.get_map_width(), ct.get_map_height()
        if self.spawned >= N_BUILDERS:
            return
        try:
            if ct.get_action_cooldown() != 0:
                return
            if ct.get_global_resources() < ct.get_builder_bot_cost() + SPAWN_RESERVE:
                return
        except Exception:
            return
        for t in ring_of(a, w, h):
            tp = Position(t[0], t[1])
            try:
                if ct.can_spawn(tp):
                    ct.spawn_builder(tp)
                    self.spawned += 1
                    ct.write_store(S_ORD, ct.read_store(S_ORD) + 1)
                    return
            except Exception:
                continue

    # ------------------------------------------------------------------
    def _builder(self, ct):
        pos = ct.get_position()
        if self.ordinal is None:
            try:
                self.ordinal = ct.read_store(S_ORD)
            except Exception:
                self.ordinal = 0
        if self.core is None:
            try:
                x, y = ct.read_store(S_X), ct.read_store(S_Y)
            except Exception:
                return
            if x <= 0 or y <= 0:
                return
            self.core = (x - 1, y - 1)
            w, h = ct.get_map_width(), ct.get_map_height()
            ring = ring_of(self.core, w, h)
            # Brick the middle-facing side first: on every map in this pool the opponent comes
            # from the far side of the board, and the ring tile nearest the map centre is the one
            # their Gunner reaches first.
            cx, cy = (w - 1) / 2.0, (h - 1) / 2.0
            ring.sort(key=lambda t: (t[0] - cx) ** 2 + (t[1] - cy) ** 2)
            self.ring = tuple(ring)
            self.rset = frozenset(ring)
            self.fset = frozenset(foot_of(self.core))
        self._fortify(ct, pos)

    def _empty_ring(self, ct):
        out = []
        for t in self.ring:
            b = None
            try:
                b = ct.get_tile_building_id(Position(t[0], t[1]))
            except Exception:
                b = None
            if b is None:
                out.append(t)
        return out

    def _fortify(self, ct, pos):
        todo = self._empty_ring(ct)
        can_act = False
        try:
            can_act = ct.get_action_cooldown() == 0
        except Exception:
            can_act = False

        # 1. brick anything empty we can already reach
        if can_act and todo:
            afford = False
            try:
                afford = ct.get_global_resources() >= ct.get_barrier_cost()
            except Exception:
                afford = False
            if afford:
                for t in todo:
                    if abs(t[0] - pos.x) + abs(t[1] - pos.y) != 1:
                        continue
                    try:
                        if ct.can_build_barrier(Position(t[0], t[1])):
                            ct.build_barrier(Position(t[0], t[1]))
                            return
                    except Exception:
                        continue

        # 2. heal any damaged neighbour -- 4 HP for 1 Ti is the cheapest titanium in the game,
        #    and it is what makes the ring cost the attacker more than it costs us.
        if can_act and self._heal(ct, pos):
            return

        # 3. get out of the ring: a builder standing on a ring tile is holding that lane open,
        #    and it can never brick the tile under its own feet (G59).
        here = (pos.x, pos.y)
        if here in self.rset and todo:
            if self._step_out(ct, pos):
                return

        # 4. walk to a stand tile for the nearest empty ring tile
        if todo:
            goal = self._stand_for(ct, pos, todo)
            if goal is not None and self._step_to(ct, pos, goal):
                return

        # 5. ring is closed. Park on the shell beside it and wait to mend.
        if here in self.rset:
            self._step_out(ct, pos)

    def _heal(self, ct, pos):
        for d in CARD:
            t = pos.add(d)
            try:
                if ct.can_heal(t):
                    ct.heal(t)
                    return True
            except Exception:
                continue
        return False

    def _step_out(self, ct, pos):
        try:
            if ct.get_move_cooldown() != 0:
                return True
        except Exception:
            return False
        for d in CARD:
            n = pos.add(d)
            if (n.x, n.y) in self.rset or (n.x, n.y) in self.fset:
                continue
            try:
                if ct.can_move(d):
                    ct.move(d)
                    return True
            except Exception:
                continue
        return False

    def _stand_for(self, ct, pos, todo):
        """Nearest tile OUTSIDE the ring from which some empty ring tile can be bricked."""
        best, best_d = None, None
        w, h = 0, 0
        try:
            w, h = ct.get_map_width(), ct.get_map_height()
        except Exception:
            return None
        for t in todo:
            for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
                s = (t[0] + dx, t[1] + dy)
                if s in self.rset or s in self.fset:
                    continue
                if not (0 <= s[0] < w and 0 <= s[1] < h):
                    continue
                d = abs(s[0] - pos.x) + abs(s[1] - pos.y)
                if best_d is None or d < best_d:
                    best_d, best = d, s
        return best

    def _step_to(self, ct, pos, goal):
        try:
            if ct.get_move_cooldown() != 0:
                return True
        except Exception:
            return False
        if (pos.x, pos.y) == goal:
            return False
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
            return False
        try:
            ct.move(best)
        except Exception:
            return False
        return True

    # ------------------------------------------------------------------
    def _gunner(self, ct):
        """Never built by this version -- present only so a stray turret is not inert."""
        try:
            target = ct.get_gunner_target()
        except Exception:
            return
        if target is None:
            return
        occ = None
        try:
            occ = ct.get_tile_building_id(target)
            if occ is None:
                occ = ct.get_tile_builder_bot_id(target)
        except Exception:
            return
        if occ is None:
            return
        try:
            if ct.get_team(occ) == ct.get_team():
                return
            if ct.can_fire(target):
                ct.fire(target)
        except Exception:
            return
