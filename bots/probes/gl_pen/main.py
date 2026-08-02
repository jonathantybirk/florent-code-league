"""AREA 1 / probe 5: the GOBBLE PEN -- a prison cell built out of barriers.

`glbox` proved a sealed TERRAIN pocket removes an enemy builder permanently.
This builds the same thing out of 3 barriers and the Launcher itself, on a map
with NO terrain at all (`glopen`, 26x14, no walls anywhere):

        (9,5)B
   (8,6)B  (9,6)CELL  (10,6)LAUNCHER
        (9,7)B

  The CELL is inside the Launcher's r^2<=2 pickup ring (d^2=1), so anything in
  the ring can be thrown into it. A bot in the CELL has all four cardinal
  neighbours blocked (3 barriers + 1 launcher) so it cannot move at all.
  The Launcher keeps 5 open ring tiles as bait: (10,5),(11,5),(11,6),(10,7),(11,7).

  Policy: enemy in the ring -> GOBBLE into the cell if the cell is free,
  otherwise REWIND: throw to the legal target with the largest x (back toward
  the enemy Core), which measures the real per-throw displacement.

Also counts BREACHes (any enemy reaching x <= 5) to measure defensive throughput.
"""

from fcode import Controller, Direction, EntityType, GameError, Position

LPOS = Position(10, 6)
CELL = Position(9, 6)
BARRS = (Position(9, 5), Position(9, 7), Position(8, 6))
RING = [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)]
PARK = Position(5, 10)


def en(exc):
    return type(exc).__name__ + ":" + str(exc)[:26]


class Player:
    def __init__(self):
        self.spawned = False
        self.stage = 0
        self.gobbles = 0
        self.rewinds = 0
        self.sumdx = 0
        self.prisoner = None
        self.breached = set()

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            print("LP|TOP %s" % en(exc))

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()
        if et == EntityType.CORE:
            if not self.spawned and ct.can_spawn(Position(3, 6)):
                ct.spawn_builder(Position(3, 6))
                self.spawned = True
            return
        if et == EntityType.BUILDER_BOT:
            self._builder(ct, r)
            return
        if et == EntityType.LAUNCHER:
            self._launcher(ct, r)

    def _builder(self, ct, r):
        pos = ct.get_position()
        # 0: go to (9,6), build launcher east
        if self.stage == 0:
            if pos != CELL:
                self._step(ct, pos, CELL)
                return
            if ct.can_build_launcher(LPOS):
                ct.build_launcher(LPOS)
                self.stage = 1
                print("LP|r%d built launcher" % r)
            return
        # 1: step out to (8,5)
        if self.stage == 1:
            if pos != Position(8, 5):
                self._step(ct, pos, Position(8, 5))
                return
            self.stage = 2
            return
        if self.stage == 2:
            if ct.can_build_barrier(Position(9, 5)):
                ct.build_barrier(Position(9, 5))
                self.stage = 3
            return
        if self.stage == 3:
            if ct.can_build_barrier(Position(8, 6)):
                ct.build_barrier(Position(8, 6))
                self.stage = 4
                print("LP|r%d two barriers up" % r)
            return
        # 4: walk round to (8,7) via (7,5)(7,6)(7,7)
        if self.stage == 4:
            if pos != Position(8, 7):
                for goal in (Position(7, 5), Position(7, 7), Position(8, 7)):
                    if pos != goal and not (goal.x == 8 and pos.x == 7 and pos.y != 7):
                        self._step(ct, pos, goal)
                        return
                self._step(ct, pos, Position(8, 7))
                return
            self.stage = 5
            return
        if self.stage == 5:
            if ct.can_build_barrier(Position(9, 7)):
                ct.build_barrier(Position(9, 7))
                self.stage = 6
                print("LP|r%d PEN COMPLETE" % r)
            return
        if pos != PARK:
            self._step(ct, pos, PARK)

    def _launcher(self, ct, r):
        me = ct.get_team()
        if self.prisoner is not None:
            try:
                p = ct.get_position(self.prisoner)
                if r % 100 == 0 or r > 995:
                    print("LP|r%d PRISONER id%d at %s,%s hp=%d" % (
                        r, self.prisoner, p.x, p.y, ct.get_hp(self.prisoner)))
                if p != CELL:
                    print("LP|r%d PRISONER ESCAPED to %s,%s" % (r, p.x, p.y))
                    self.prisoner = None
            except Exception:
                print("LP|r%d PRISONER id%d vanished" % (r, self.prisoner))
                self.prisoner = None

        # breach counter: any enemy west of x=5 in vision
        for eid in ct.get_nearby_units():
            if ct.get_team(eid) == me:
                continue
            if ct.get_position(eid).x <= 5 and eid not in self.breached:
                self.breached.add(eid)
                print("LP|r%d BREACH id%d total=%d" % (r, eid, len(self.breached)))

        src = None
        for dx, dy in RING:
            q = Position(LPOS.x + dx, LPOS.y + dy)
            if q == CELL:
                continue
            try:
                bid = ct.get_tile_builder_bot_id(q)
            except Exception:
                continue
            if bid is None or ct.get_team(bid) == me:
                continue
            src = q
            break
        if src is None:
            return

        cell_free = True
        try:
            cell_free = ct.get_tile_builder_bot_id(CELL) is None
        except Exception:
            cell_free = False
        if cell_free and ct.can_launch(src, CELL):
            bid = ct.get_tile_builder_bot_id(src)
            ct.launch(src, CELL)
            self.gobbles += 1
            self.prisoner = bid
            print("LP|r%d GOBBLE id%d %s,%s -> cell  (gobbles=%d)" % (
                r, bid, src.x, src.y, self.gobbles))
            return

        best = None
        for dy in range(-5, 6):
            for dx in range(-5, 6):
                if dx * dx + dy * dy > 26:
                    continue
                q = Position(LPOS.x + dx, LPOS.y + dy)
                if q.x < 0 or q.y < 0:
                    continue
                try:
                    ok = ct.can_launch(src, q)
                except Exception:
                    continue
                if ok and (best is None or q.x > best.x):
                    best = q
        if best is None:
            return
        bid = ct.get_tile_builder_bot_id(src)
        ct.launch(src, best)
        self.rewinds += 1
        self.sumdx += best.x - src.x
        print("LP|r%d REWIND id%d %s,%s -> %s,%s  dx=+%d (rewinds=%d avgdx=%.2f)" % (
            r, bid, src.x, src.y, best.x, best.y, best.x - src.x,
            self.rewinds, float(self.sumdx) / self.rewinds))

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
