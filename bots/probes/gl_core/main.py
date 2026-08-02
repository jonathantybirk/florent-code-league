"""LAUNCHER Q8 + cooldown: can a throw land on a CORE FOOTPRINT? one throw per round?

Arena: maps/lab/glopen.map26.  Run: python tools/runprobe.py gl_core --map lab/glopen --vs idle

Launcher at (4,6), which is d^2 = 4..9 from every tile of our own Core's 2x2
footprint at (1,6)/(2,6)/(1,7)/(2,7) -- well inside the r^2<=26 throw disc, so
if a Core tile is refused it is refused on passability, not on range.

Two builders park on ring tiles (5,6) and (5,7). The Launcher:
  T1 tries every Core footprint tile as a target,
  T2 tries the tile the OTHER builder is standing on,
  T3 launches builder 1, then in the SAME round tries to launch builder 2 and
     reads get_action_cooldown -- the throughput ceiling per Launcher per round,
  T4 next round, tries again to confirm the cooldown is 1,
  T5 tries a CONVEYOR tile as a target (a building a builder may stand on, G61)
     and reads where the passenger actually lands.
"""

from fcode import Controller, Direction, EntityType, Position

L = Position(4, 6)
A = Position(5, 6)
B = Position(5, 7)
FAR = Position(8, 6)
FAR2 = Position(8, 7)
CORE_TILES = (Position(1, 6), Position(2, 6), Position(1, 7), Position(2, 7))
CONV = Position(4, 7)
SPAWN1 = Position(3, 6)
SPAWN2 = Position(3, 7)


class Player:
    def __init__(self):
        self.n = 0
        self.role = None
        self.k = 0
        self.notes = []
        self.stage = 0
        self.cd = "?"
        self.done = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            try:
                ct.resign("gl_core TOP %s:%s" % (type(exc).__name__, str(exc)[:40]))
            except Exception:
                pass

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()
        if et == EntityType.CORE:
            if self.n == 0 and ct.can_spawn(SPAWN1):
                ct.spawn_builder(SPAWN1)
                self.n = 1
            elif self.n == 1 and ct.can_spawn(SPAWN2):
                ct.spawn_builder(SPAWN2)
                self.n = 2
            return
        if et == EntityType.BUILDER_BOT:
            self._builder(ct)
            return
        if et == EntityType.LAUNCHER:
            self._launcher(ct, r)

    def _builder(self, ct):
        if self.role is None:
            self.role = ct.read_store(3)
            ct.write_store(3, self.role + 1)
        pos = ct.get_position()
        if self.role == 0:
            if pos != A:
                self._step(ct, pos, A)
                return
            if ct.get_tile_building_id(L) is None and ct.can_build_launcher(L):
                ct.build_launcher(L)
            return
        if pos != B:
            self._step(ct, pos, B)
            return
        if ct.get_tile_building_id(CONV) is None and ct.can_build_conveyor(CONV, Direction.WEST):
            ct.build_conveyor(CONV, Direction.WEST)

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
        if self.done:
            return
        ida = None
        idb = None
        try:
            ida = ct.get_tile_builder_bot_id(A)
            idb = ct.get_tile_builder_bot_id(B)
        except Exception:
            return
        if self.stage == 0:
            if ida is None or idb is None or ct.get_tile_building_id(CONV) is None:
                return
            res = []
            for c in CORE_TILES:
                try:
                    res.append("%d,%d=%s" % (c.x, c.y, "T" if ct.can_launch(A, c) else "F"))
                except Exception as exc:
                    res.append("%d,%d=%s" % (c.x, c.y, type(exc).__name__))
            self.notes.append("CORETILES " + " ".join(res))
            try:
                self.notes.append("occupied=%s" % ("T" if ct.can_launch(A, B) else "F"))
            except Exception as exc:
                self.notes.append("occupied=%s" % type(exc).__name__)
            try:
                self.notes.append("selftile=%s" % ("T" if ct.can_launch(A, L) else "F"))
            except Exception as exc:
                self.notes.append("selftile=%s" % type(exc).__name__)
            try:
                self.notes.append("conveyor=%s" % ("T" if ct.can_launch(A, CONV) else "F"))
            except Exception as exc:
                self.notes.append("conveyor=%s" % type(exc).__name__)
            self.notes.append("cd0=%d" % ct.get_action_cooldown())
            ida2 = ct.get_tile_builder_bot_id(A)
            ct.launch(A, CONV)
            lp = ct.get_position(ida2)
            self.notes.append("land=%d,%d" % (lp.x, lp.y))
            self.notes.append("cd1=%d 2nd=%s" % (
                ct.get_action_cooldown(),
                "T" if ct.can_launch(B, FAR2) else "F"))
            self.stage = 1
            self.when = r
            return
        if self.stage == 1:
            self.notes.append("nextround cd=%d 2nd=%s" % (
                ct.get_action_cooldown(),
                "T" if ct.can_launch(B, FAR2) else "F"))
            self.done = True
            ct.resign(("CORE r%d " % r + " | ".join(self.notes))[:495])
