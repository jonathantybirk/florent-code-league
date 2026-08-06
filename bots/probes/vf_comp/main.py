"""The case the "exactly 2 rounds" number does not cover: the CLAIMANT dies before it confirms.

Under the lease, a challenger writes its word on round K and only learns it won on round K+1, when
it reads its own id back.  If it dies in between, the losers of that same challenge cannot tell.
They read a FRESH foreign lease (stamp K, so `round - stamp` is 1) and stand down exactly as if a
healthy owner held it.  Only when the dead claimant's stamp ages out do they challenge again.

Prediction: vacancy = 2 * (1 + number of consecutive claimants that die before confirming).
So one dead claimant costs 4 vacant rounds, two cost 6, and the "exactly 2" figure is the case
where the first challenge winner survives.

This probe forces the sequence by entity id on arena `scal`, where the Core's six builders are
deterministically ids 3..8 (measured: vf_lease reports ids=[3,4,5,6,7,8] every run).

  DIE_BEFORE 3 @ 25   the owner dies at the TOP of its turn, without renewing
  DIE_AFTER  8 @ 26   the highest live id -- so the challenge winner -- dies AFTER writing its claim
  DIE_AFTER  7 @ 28   and so does the next one

Expected transcript: last act 24, then 6 vacant rounds, next act 31, owner id 6.
"""

from fcode import Controller, Direction, EntityType, Position

S_LEASE, S_ACTED = 0, 1
S_REP = 8

STALE = 2
NBUILD = 6
DIE_BEFORE = {3: 25}
DIE_AFTER = {8: 26, 7: 28}
LAST = 45


def pack(uid, r):
    return ((uid + 1) << 10) | r


class Player:
    def __init__(self):
        self.n = []
        self.done = False
        self.owner = False
        self.acted = []
        self.last_ar = -1
        self.owners = []
        self.last_ow = -1
        self.ids = []
        self.maxconc = 0

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.n.append("TOP:" + type(exc).__name__)

    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            self._core(ct)
        elif et == EntityType.BUILDER_BOT:
            self._builder(ct)

    def _core(self, ct):
        if self.done:
            return
        r = ct.get_current_round()
        if r < NBUILD:
            self._spawn(ct)
            return
        if r == NBUILD:
            self.ids = sorted(i for i in ct.get_nearby_units()
                              if ct.get_team(i) == ct.get_team() and i != ct.get_id())
            return

        w = ct.read_store(S_ACTED)
        if w:
            ar, ow = w & 1023, (w >> 10) - 1
            if ar != self.last_ar:
                self.acted.append(ar)
                self.last_ar = ar
                if ow != self.last_ow:
                    self.owners.append((ar, ow))
                    self.last_ow = ow
        c = sum(1 for i in range(8) if ct.read_store(S_REP + i) == r - 1)
        self.maxconc = max(self.maxconc, c)

        if r == LAST:
            gaps = ["%d>%d(%d)" % (a, b, b - a - 1)
                    for a, b in zip(self.acted, self.acted[1:]) if b - a > 1]
            self.done = True
            ct.resign("VFC|ids=%s|acts=%d span=%s..%s|gaps=%s|own=%s|conc=%d|before=%s after=%s" % (
                self.ids, len(self.acted),
                self.acted[0] if self.acted else -1, self.acted[-1] if self.acted else -1,
                ",".join(gaps) or "NONE",
                ",".join("%d@%d" % (o, a) for a, o in self.owners),
                self.maxconc, DIE_BEFORE, DIE_AFTER))

    def _spawn(self, ct):
        p = ct.get_position()
        for dx, dy in ((2, 0), (2, 1), (0, -1), (1, -1), (-1, 0), (-1, 1),
                       (0, 2), (1, 2), (2, 2), (-1, -1)):
            q = Position(p.x + dx, p.y + dy)
            try:
                if ct.can_spawn(q):
                    ct.spawn_builder(q)
                    return
            except Exception:
                continue

    def _builder(self, ct):
        r = ct.get_current_round()
        mine = ct.get_id()

        if DIE_BEFORE.get(mine) == r:
            ct.self_destruct()                 # dies without renewing
            return

        raw = ct.read_store(S_LEASE)
        stamp = raw & 1023
        held = (raw >> 10) - 1
        fresh = raw != 0 and (r - stamp) < STALE

        if raw and held == mine:
            self.owner = True
        elif fresh:
            self.owner = False

        if self.owner:
            ct.write_store(S_LEASE, pack(mine, r))
            ct.write_store(S_ACTED, pack(mine, r))
            ct.write_store(S_REP + (mine % 8), r)
        elif not fresh:
            ct.write_store(S_LEASE, pack(mine, r))   # challenge

        if DIE_AFTER.get(mine) == r:
            ct.self_destruct()                 # claim is buffered, then the claimant dies
