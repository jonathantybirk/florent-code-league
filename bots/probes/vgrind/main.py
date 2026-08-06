"""VERIFICATION of TASK 1.1 -- does the "2 parked escorts hold a forward turret"
claim survive when BOTH sides race for the SAME four contact tiles?

`grindheal` pre-assigned disjoint contact slots (healers W,S,N -- grinders E,N,S), so
the premise "the enemy gets at most 2 tiles" was built into the arena rather than
measured.  This probe removes the pre-assignment: every bot on BOTH teams runs the
same greedy policy -- claim the nearest contact tile that currently has no bot on it,
walk there, park, then heal (team A) or grind (team B).  Whoever arrives first owns
the tile, because Builder Bots are impassable and cannot attack units.

Played as BOTH sides on maps/lab/hg<W>x<H>.map26.  Configuration in the dimensions:

    N = (H - 10) // 4   team-A escorts BEYOND the constructor (constructor also parks)
    M = (H - 10) %  4   team-B grinders
    W  ->  (turret x, B start round, A-escort start round, B deterministic?)
        24 -> (12, 0,  0, 0)  midfield, both commit r0, both sides greedy
        25 -> (17, 0,  0, 0)  FORWARD, both commit r0, both sides greedy
        26 -> (12, 0,  0, 1)  midfield, both commit r0, enemy on private lanes
        27 -> (17, 20, 0, 1)  FORWARD, enemy reacts only after the turret is up
        28 -> (17, 0,  0, 1)  FORWARD, both commit r0, enemy on private lanes

    Greedy-vs-greedy is the weaker measurement: three grinders converging on the same
    nearest tile bunch up, and a head-on meeting in row 3 stalls both sides.  Bdet=1
    routes the three grinders down private lanes to N, S and E, so arrival order
    reflects travel distance instead of a shoving match.

Team A's bot 0 is the constructor: it claims a contact tile like everybody else and
builds the Sentinel on T from there, then stays as an escort.  If team B owns all four
contact tiles first, the turret is never built at all -- also a result.

The turret publishes HP and a four-tile occupancy census every round; A's Core
run-length-encodes both and resigns the trajectory.
"""

from fcode import Controller, Direction, EntityType, Position

# width -> (turret x, round team B starts moving, round team A's ESCORTS start moving)
# The team-A constructor (bot 0) always leaves at round 0 so a turret exists to fight over.
# width -> (turret x, B start round, A-escort start round, B deterministic?)
# bdet=1 gives team B a fixed, non-colliding assignment (N, S, E) so three grinders
# reliably claim three tiles -- the greedy policy bunches up and only ever claims two.
MODES = {
    24: (12, 0, 0, 0),
    25: (17, 0, 0, 0),
    26: (12, 0, 0, 1),
    27: (17, 20, 0, 1),
    28: (17, 0, 0, 1),
}

REPORT_ROUND = 200

S_HP = 0        # turret hp + 1
S_BEAT = 1      # turret round + 1 (freezes on death)
S_OCC = 2       # friend_mask * 16 + enemy_mask over (E, N, S, W)
S_BUILT = 3     # round the turret was built, + 1
S_ARR = 4       # + bot index: round that bot parked, + 1   (4,5,6,7)
S_TILE = 8      # + bot index: parked tile code + 1 (1=E 2=N 3=S 4=W)  (8,9,10,11)

CARD = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)


def config(ct):
    w = ct.get_map_width()
    h = ct.get_map_height()
    idx = h - 10
    tx, bstart, astart, bdet = MODES.get(w, (12, 0, 0, 0))
    return w, h, idx // 4, idx % 4, tx, bstart, astart, bdet


def contacts(tx):
    # order is (E, N, S, W) -- the bitmask order used in the census
    return (Position(tx + 1, 3), Position(tx, 2), Position(tx, 4), Position(tx - 1, 3))


def _slots(mask):
    return "".join(n for bit, n in enumerate("ENSW") if mask & (1 << bit)) or "-"


class Player:
    def __init__(self):
        self.kind = None
        self.west = None
        self.idx = None
        self.target = None
        self.parked = False
        self.leg = 0
        self.built = False
        self.acts = 0
        self.published = False
        # Core-only
        self.spawned = set()
        self.hp = []
        self.beat = []
        self.occ = []
        self.info = ""
        self.err = []

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            if len(self.err) < 5:
                self.err.append("%s:%s" % (type(exc).__name__, str(exc)[:40]))

    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            self._core(ct)
        elif et == EntityType.BUILDER_BOT:
            self._bot(ct)
        elif et in (EntityType.SENTINEL, EntityType.GUNNER):
            self._turret(ct)

    # ---------------------------------------------------------------- core ---
    def _core(self, ct):
        w, h, n, m, tx, bstart, astart, bdet = config(ct)
        r = ct.get_current_round()
        if self.west is None:
            self.west = ct.get_position().x < w // 2

        if self.west:
            spots = [Position(3, 2)] + [Position(3, y) for y in (3, 5, 4)][:n]
        else:
            spots = [Position(w - 4, y) for y in (3, 4, 5)][:m]

        for i, pos in enumerate(spots):
            if i in self.spawned:
                continue
            if ct.can_spawn(pos):
                ct.spawn_builder(pos)
                self.spawned.add(i)
            break

        if self.west:
            self.hp.append(ct.read_store(S_HP) - 1)
            self.beat.append(ct.read_store(S_BEAT) - 1)
            self.occ.append(ct.read_store(S_OCC))
            if r >= REPORT_ROUND:
                ct.resign(self._report(ct, w, h, n, m, tx, bstart, astart, bdet))

    def _report(self, ct, w, h, n, m, tx, bstart, astart, bdet):
        built = ct.read_store(S_BUILT) - 1
        arr = [ct.read_store(S_ARR + i) - 1 for i in range(4)]
        tile = [ct.read_store(S_TILE + i) - 1 for i in range(4)]
        names = {1: "E", 2: "N", 3: "S", 4: "W"}
        park = ",".join("b%d=%s@r%d" % (i, names.get(tile[i], "-"), arr[i])
                        for i in range(1 + n))
        dbg = []
        for i in range(1 + n):
            v = ct.read_store(12 + i)
            if v <= 0:
                dbg.append("b%d=parked/none" % i)
            else:
                v -= 1
                dbg.append("b%d=(%d,%d)err%d" % (i, (v // 8) // 32, (v // 8) % 32, v % 8))
        park = park + " LAST[" + " ".join(dbg) + "]"

        # occupancy timeline: emit every transition
        occline = []
        prev = None
        for i, v in enumerate(self.occ):
            if v != prev:
                occline.append("r%d:f=%s/e=%s" % (i, _slots(v // 16), _slots(v % 16)))
                prev = v

        if built < 0:
            return ("VCFG N=%d M=%d %dx%d Tx=%d Bstart=%d Astart=%d Bdet=%d | TURRET NEVER BUILT "
                    "| PARK %s | OCC %s | ERR=%s"
                    % (n, m, w, h, tx, bstart, astart, bdet, park, " ".join(occline), ";".join(self.err)))

        alive_until = -1
        for i in range(1, len(self.beat)):
            if self.beat[i] > self.beat[i - 1]:
                alive_until = i
        born = -1
        for i, v in enumerate(self.hp):
            if v >= 0:
                born = i
                break
        dead = alive_until if alive_until < len(self.beat) - 3 else -1
        seq = self.hp[born:alive_until + 1]
        parts = []
        rv, rn = None, 0
        for i in range(1, len(seq)):
            d = seq[i] - seq[i - 1]
            if d == rv:
                rn += 1
            else:
                if rv is not None:
                    parts.append("%+d%s" % (rv, "x%d" % rn if rn > 1 else ""))
                rv, rn = d, 1
        if rv is not None:
            parts.append("%+d%s" % (rv, "x%d" % rn if rn > 1 else ""))

        return ("VCFG N=%d M=%d %dx%d Tx=%d Bstart=%d Astart=%d Bdet=%d | BUILT=r%d HP0=%d END=%d MIN=%d "
                "DEAD=r%d | TRACE(r%d..)=%s | PARK %s | OCC %s | ERR=%s"
                % (n, m, w, h, tx, bstart, astart, bdet, built, seq[0], seq[-1], min(seq), dead,
                   born, " ".join(parts) or "flat", park,
                   " ".join(occline), ";".join(self.err)))

    # ----------------------------------------------------------------- bot ---
    def _bot(self, ct):
        w, h, n, m, tx, bstart, astart, bdet = config(ct)
        r = ct.get_current_round()
        p = ct.get_position()
        T = Position(tx, 3)
        C = contacts(tx)

        if self.west is None:
            self.west = p.x < w // 2
            if self.west:
                self.idx = {2: 0, 3: 1, 5: 2, 4: 3}.get(p.y, 0)
            else:
                self.idx = {3: 0, 4: 1, 5: 2}.get(p.y, 0)

        if not self.west and r < bstart:
            return
        if self.west and self.idx > 0 and r < astart:
            return

        # ---- park / act -------------------------------------------------
        if self.parked:
            self._act(ct, T)
            return

        for q in C:
            if p.x == q.x and p.y == q.y:
                self.parked = True
                if self.west:
                    code = 1 + [i for i, c in enumerate(C)
                                if c.x == q.x and c.y == q.y][0]
                    ct.write_store(S_ARR + self.idx, r + 1)
                    ct.write_store(S_TILE + self.idx, code + 1)
                self._act(ct, T)
                return

        # ---- deterministic enemy assignment (N, S, E) on private lanes -------
        # Waypoints keep the three grinders off row 3 west of the turret, where they
        # otherwise meet team A head-on and both sides stall.  Same trick grindheal
        # used for its own bots; here it is applied to the ENEMY so the race is
        # decided by distance rather than by a shoving match.
        if bdet and not self.west:
            legs = [
                [Position(w - 4, 1), Position(tx, 1), C[1]],       # -> N
                [Position(w - 4, 5), Position(tx, 5), C[2]],       # -> S
                [Position(w - 4, 3), C[0]],                        # -> E
            ][self.idx % 3]
            if self.leg >= len(legs):
                return
            g = legs[self.leg]
            if p.x == g.x and p.y == g.y:
                self.leg += 1
                if self.leg >= len(legs):
                    return
                g = legs[self.leg]
            self._step(ct, p, g)
            return

        # ---- (re)choose the nearest contact tile with no bot on it -------
        best, bd = None, 10 ** 6
        for q in C:
            try:
                uid = ct.get_tile_builder_bot_id(q)
            except Exception:
                uid = None
            if uid is not None:
                continue
            d = abs(q.x - p.x) + abs(q.y - p.y)
            if d < bd:
                best, bd = q, d
        if best is None:
            best = C[0] if not self.west else C[3]
        self.target = best
        if self.west:
            ct.write_store(12 + self.idx, 1 + (p.x * 32 + p.y) * 8 + len(self.err))
        self._step(ct, p, best)

    def _act(self, ct, T):
        if self.west:
            if self.idx == 0 and not self.built:
                if ct.can_build_sentinel(T, Direction.EAST):
                    ct.build_sentinel(T, Direction.EAST)
                    self.built = True
                    ct.write_store(S_BUILT, ct.get_current_round() + 1)
                    return
            if ct.can_heal(T):
                ct.heal(T)
                self.acts += 1
        else:
            if ct.can_fire(T):
                ct.fire(T)
                self.acts += 1

    def _step(self, ct, p, g):
        dx = g.x - p.x
        dy = g.y - p.y
        order = []
        ew = Direction.EAST if dx > 0 else Direction.WEST
        ns = Direction.SOUTH if dy > 0 else Direction.NORTH
        if abs(dx) >= abs(dy):
            if dx:
                order.append(ew)
            if dy:
                order.append(ns)
        else:
            if dy:
                order.append(ns)
            if dx:
                order.append(ew)
        if dx and not dy:
            order += [Direction.NORTH, Direction.SOUTH]
        if dy and not dx:
            order += [Direction.EAST, Direction.WEST]
        for d in order:
            if ct.can_move(d):
                ct.move(d)
                return

    # -------------------------------------------------------------- turret ---
    def _turret(self, ct):
        r = ct.get_current_round()
        ct.write_store(S_HP, ct.get_hp() + 1)
        ct.write_store(S_BEAT, r + 1)
        w = ct.get_map_width()
        tx = MODES.get(w, (12, 0, 0, 0))[0]
        mine = ct.get_team()
        friend = enemy = 0
        for bit, q in enumerate(contacts(tx)):
            uid = ct.get_tile_builder_bot_id(q)
            if uid is None:
                continue
            if ct.get_team(uid) == mine:
                friend |= 1 << bit
            else:
                enemy |= 1 << bit
        ct.write_store(S_OCC, friend * 16 + enemy)
