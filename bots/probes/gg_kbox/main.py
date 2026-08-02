"""AREA 1 / GobbleGlitch probe: the KILL BOX.

Question (e): does a Launcher feeding a team-blind Gunner's ray actually KILL
enemy builders, and at what price?

Arena `glchoke` (26x14). Wall column x=13 with a single gap at (13,6).
Core A anchor (1,6); Core B anchor (22,6). Every attacker must pass (13,6).

  LAUNCHER  L = (12,5).  Its pickup ring (r^2<=2) is the 8 neighbours, which
            includes the choke gap (13,6) (d^2=2) and the two tiles the
            attacker walks to next, (12,6) (d^2=1) and (11,6) (d^2=2).
  GUNNER    G = (11,8) facing NORTH.  Ray = (11,7),(11,6),(11,5).
            (11,6) and (11,5) are BOTH inside L's pickup ring, so the Launcher
            can bounce a victim between two tiles that are both under fire and
            both still pickable next round.  Neither equals the other, so the
            "target == source" rejection never bites.

BUILD ORDER IS THE EXPERIMENT: the Launcher is built FIRST so its entity id is
LOWER than the Gunner's.  Entities act in ascending id order, so within a single
round the Launcher can throw a victim into the ray and the Gunner then fires at
it the same round.  If the order were reversed the Gunner would act first and
see an empty ray.

Logged: id order, every throw, every shot with hp before/after, kills, ammo
spent, rounds per kill, ring occupancy, and BREACHes (enemy at x<=8).
"""

from fcode import Controller, Direction, EntityType, GameError, Position

LPOS = Position(12, 5)
GPOS = Position(11, 8)
GSTAND = Position(12, 8)
LSTAND = Position(12, 6)
PARK = Position(7, 10)
RAY = [Position(11, 6), Position(11, 5)]
RING = [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)]


def en(exc):
    return type(exc).__name__ + ":" + str(exc)[:28]


class Player:
    def __init__(self):
        self.spawned = False
        self.stage = 0
        self.kills = 0
        self.shots = 0
        self.throws = 0
        self.seen = {}
        self.said = False

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

    def _builder(self, ct, r):
        pos = ct.get_position()
        if self.stage == 0:
            if pos != LSTAND:
                self._step(ct, pos, LSTAND)
                return
            if ct.can_build_launcher(LPOS):
                lid = ct.build_launcher(LPOS)
                print("LP|r%d LAUNCHER id=%d" % (r, lid))
                self.stage = 1
            return
        if self.stage == 1:
            if pos != GSTAND:
                self._step(ct, pos, GSTAND)
                return
            if ct.can_build_gunner(GPOS, Direction.NORTH):
                gid = ct.build_gunner(GPOS, Direction.NORTH)
                print("LP|r%d GUNNER id=%d (built second => higher id)" % (r, gid))
                self.stage = 2
            return
        if pos != PARK:
            self._step(ct, pos, PARK)
            return
        # parked: report any attacker that got past us
        me = ct.get_team()
        n = 0
        for uid in ct.get_nearby_units():
            if ct.get_team(uid) != me:
                n += 1
        if n:
            print("LP|r%d BREACH n=%d at park" % (r, n))

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
        ring = []
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
            ring.append((bid, q))
        if not ring:
            return
        # pick a destination that is a ray tile, empty, and not the source
        for bid, q in ring:
            dest = None
            for t in RAY:
                if t.x == q.x and t.y == q.y:
                    continue
                if ct.get_tile_builder_bot_id(t) is not None:
                    continue
                dest = t
                break
            if dest is None:
                continue
            if not ct.can_launch(q, dest):
                print("LP|r%d NOLAUNCH %s,%s -> %s,%s" % (r, q.x, q.y, dest.x, dest.y))
                continue
            hp0 = ct.get_hp(bid)
            ct.launch(q, dest)
            self.throws += 1
            if bid not in self.seen:
                self.seen[bid] = r
            print("LP|r%d THROW id%d %s,%s -> %s,%s hp=%d ring=%d thr=%d" % (
                r, bid, q.x, q.y, dest.x, dest.y, hp0, len(ring), self.throws))
            return
        print("LP|r%d ring=%d but no legal ray tile" % (r, len(ring)))

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
        self.shots += 1
        try:
            hp1 = ct.get_hp(bid)
            alive = "y"
        except Exception:
            hp1 = 0
            alive = "DEAD"
            self.kills += 1
        print("LP|r%d SHOT id%d at %s,%s hp %d->%d %s kills=%d shots=%d ammo=%d" % (
            r, bid, tgt.x, tgt.y, hp0, hp1, alive, self.kills, self.shots,
            ct.get_global_ammo()))
