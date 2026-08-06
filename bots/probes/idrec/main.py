"""Are entity ids ever RECYCLED, or are they a strictly ascending global counter?

This is the load-bearing question behind "does a turret built one round LATER but
with a lower entity id still fire first?".  Turn order is ascending global entity
id (re-verified on 2.3.6 by the du_s_af / du_s_bf duel pair), so that scenario is
only constructible if a dead entity's id can be handed to a later creation.

The probe, on maps/lab/firstshot.map26 with a builder parked at (5,4):

  1. build a barrier at (6,4)            -> id a
  2. destroy it, then build there again  -> id b     b == a  =>  ids recycle
  3. build a barrier at (5,3)            -> id c
  4. destroy the (6,4) barrier, build a barrier at (4,4) -> id d
  5. core spawns a second builder        -> id u1
  6. that builder self-destructs; core spawns a third   -> id u2
     u2 == u1  =>  unit ids recycle after a death, not just after a destroy

Everything is relayed to the CORE through the store slots (team-wide, one-round
write lag) because the second builder deliberately kills itself.  The core
resigns with the id sequence -- resign() is the only output channel (HARNESS.md).
"""

from fcode import Controller, Direction, EntityType, Position

BPOS = Position(5, 4)
P1 = Position(6, 4)
P2 = Position(5, 3)
P3 = Position(4, 4)
SPAWN = Position(3, 4)
RESIGN_ROUND = 40

S_A, S_B, S_C, S_D, S_STEP, S_U1, S_U2, S_ERR = 0, 1, 2, 3, 4, 5, 6, 7


def _w(ct, slot, val):
    try:
        ct.write_store(slot, max(0, min(4294967295, int(val))))
    except Exception:
        pass


class Player:
    def __init__(self):
        self.step = 0
        self.role = None
        self.spawns = []
        self.err = []
        self.log = []
        self.last = None

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            if len(self.err) < 4:
                self.err.append("%s:%s" % (type(exc).__name__, str(exc)[:40]))

    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            self._core(ct)
        elif et == EntityType.BUILDER_BOT:
            self._builder(ct)

    def _core(self, ct):
        r = ct.get_current_round()
        # spawn #1 (the worker) at r1, #2 at r20, #3 at r26 (after #2 killed itself)
        want = (len(self.spawns) == 0 and r >= 1) or (r == 20) or (r == 26)
        if want:
            try:
                if ct.can_spawn(SPAWN):
                    self.spawns.append(ct.spawn_builder(SPAWN))
                    self.log.append("sp@%d" % r)
                    return
                if len(self.log) < 3:
                    ok = []
                    for dy in range(-2, 4):
                        for dx in range(-2, 4):
                            p = Position(1 + dx, 4 + dy)
                            try:
                                if ct.can_spawn(p):
                                    ok.append("%d,%d" % (p.x, p.y))
                            except Exception:
                                pass
                    self.log.append("nosp@%d ring=%s ti=%d"
                                    % (r, "/".join(ok), ct.get_global_resources()))
            except Exception as exc:
                self.err.append("S:%s" % str(exc)[:30])
        if r >= RESIGN_ROUND:
            v = [ct.read_store(i) for i in range(8)]
            d = lambda i: v[i] - 1 if v[i] else "x"        # noqa: E731
            ct.resign(
                "IDREC core=%s spawns=%s %s | a=%s b=%s c=%s d=%s step=%s | ERR %s %s"
                % (ct.get_id(), self.spawns, " ".join(self.log[:6]),
                   d(S_A), d(S_B), d(S_C), d(S_D), d(S_STEP),
                   ";".join(self.err[:3]), d(S_ERR))
            )

    def _builder(self, ct):
        me = ct.get_id()
        if self.role is None:
            self.role = "worker" if me <= 3 else "victim"
        if self.role == "victim":
            # second builder: exists for a few rounds, then deletes itself so we
            # can see whether its id is handed to the next spawn
            if ct.get_current_round() >= 23:
                ct.self_destruct()
            return

        if self.step == 0:
            if ct.can_move(Direction.EAST):
                ct.move(Direction.EAST)
                self.step = 1
            return
        if self.step == 1:
            if ct.can_move(Direction.EAST):
                ct.move(Direction.EAST)
                self.step = 2
            return
        if self.step == 2:
            if ct.can_build_barrier(P1):
                _w(ct, S_A, ct.build_barrier(P1) + 1)
                self.step = 3
            return
        if self.step == 3:
            if ct.can_destroy(P1):
                ct.destroy(P1)
                self.step = 4
            return
        if self.step == 4:
            if ct.can_build_barrier(P1):
                _w(ct, S_B, ct.build_barrier(P1) + 1)
                self.step = 5
            return
        if self.step == 5:
            if ct.can_build_barrier(P2):
                _w(ct, S_C, ct.build_barrier(P2) + 1)
                self.step = 6
            return
        if self.step == 6:
            if ct.can_destroy(P1):
                ct.destroy(P1)
                self.step = 7
            return
        if self.step == 7:
            if ct.can_build_barrier(P3):
                _w(ct, S_D, ct.build_barrier(P3) + 1)
                self.step = 8
            return
        _w(ct, S_STEP, self.step + 1)
        _w(ct, S_ERR, len(self.err) + 1)
