"""VERIFICATION probe: an INDEPENDENT re-implementation of the heartbeat lease, plus the two
assumptions st_hb never measured.

st_hb infers "0 false evictions" from "the act transcript has no gaps and only one owner ever
reports".  That is indirect.  Two things can break the lease and neither shows up as a gap:

  A1  A LIVE unit missing a turn.  The lease's whole safety argument is "the owner renews EVERY
      round it runs, and the freshest stamp a reader can see is round-1, so STALE=2 can never evict
      a living owner".  That argument is only sound if a living unit never skips a round.  Nobody
      measured that.  Every builder here records the round of its previous turn and raises an alarm
      the moment `round - prev > 1`.
  A2  A false eviction, measured DIRECTLY.  A builder that believes it is the owner and then reads a
      FRESH lease naming somebody else has been evicted while alive.  It shouts into S_EVICT.
      st_hb could only see this if it also produced a visible gap; it need not.

Also measured here and not there:
  A3  Natural deaths.  st_hb only ever killed the owner with self_destruct(), which is a cooperative
      suicide taken during the unit's own turn.  A unit shot dead by a rival is removed by the
      engine.  On a contested map the owner dies for real and the transcript gap is the honest one.
  A4  Same-round read visibility ACROSS units.  st_ver only showed that a unit cannot read its own
      same-round write.  Here the Core (lowest id on the team) writes 4242 on round 7 and every
      builder (higher id, therefore later in act order if act order is ascending id) reads the same
      slot in the same round and echoes what it saw.
  A5  The packing budget as actually observed: highest entity id in vision and highest round number.

Slots
  0  lease   (owner_id+1) << 10 | stamp
  1  acted   (actor_id+1) << 10 | round the role was performed
  2  turn-skip alarm      (id+1) << 10 | round the skip was noticed
  3  turn-skip count      (id+1) << 10 | that unit's running skip total
  4  false-eviction alarm (id+1) << 10 | round
  5  A4 writer slot   6  A4 echo slot   7  max entity id seen by a builder
  8..15  per-builder "I performed the role on round N", indexed by id % 8
"""

from fcode import Controller, Direction, EntityType, Position

S_LEASE, S_ACTED, S_SKIP, S_SKIPN, S_EVICT, S_VIS, S_ECHO, S_MAXID = range(8)
S_REP = 8

STALE = 2
OPTIMISTIC = True
NBUILD = 6           # builders spawned, one per round on rounds 0..NBUILD-1
KILL_ACT = (25, 70)   # owner renews, acts, then self_destructs the same round
KILL_MUTE = (45, 95)  # owner self_destructs without renewing
LAST = 240
VIS_ROUND = 7
VIS_MAGIC = 4242


def pack(uid, r):
    return ((uid + 1) << 10) | r


class Player:
    def __init__(self):
        self.n = []
        self.done = False
        # builder state
        self.owner = False
        self.prev = None
        self.skips = 0
        self.maxid = 0
        # core state
        self.acted = []
        self.owners = []
        self.last_ar = -1
        self.last_ow = -1
        self.ids = []
        self.maxconc = 0
        self.conc = []
        self.maxround = 0

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.n.append("TOP:" + type(exc).__name__ + ":" + str(exc)[:25])

    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            self._core(ct)
        elif et == EntityType.BUILDER_BOT:
            self._builder(ct)

    # ------------------------------------------------------------------- the core
    def _core(self, ct):
        if self.done:
            return
        r = ct.get_current_round()
        self.maxround = r

        if r < NBUILD:
            self._spawn(ct)
            return
        if r == NBUILD:
            self.ids = sorted(i for i in ct.get_nearby_units()
                              if ct.get_team(i) == ct.get_team() and i != ct.get_id())
            return
        if r == VIS_ROUND:
            ct.write_store(S_VIS, VIS_MAGIC)      # A4: lowest id on the team writes
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
        if c > self.maxconc:
            self.maxconc = c
        if c > 1:
            self.conc.append(r - 1)

        if r == LAST or ct.get_hp() < 160:
            self._report(ct, r)

    def _report(self, ct, r):
        gaps = []
        for a, b in zip(self.acted, self.acted[1:]):
            if b - a > 1:
                gaps.append("%d>%d(%d)" % (a, b, b - a - 1))
        sk, skn, ev = ct.read_store(S_SKIP), ct.read_store(S_SKIPN), ct.read_store(S_EVICT)
        self.n.append("end=%d ids=%s" % (r, self.ids))
        self.n.append("acts=%d span=%s..%s" % (
            len(self.acted), self.acted[0] if self.acted else -1,
            self.acted[-1] if self.acted else -1))
        self.n.append("gaps=" + (",".join(gaps[:8]) if gaps else "NONE"))
        self.n.append("own=" + ",".join("%d@%d" % (o, a) for a, o in self.owners[:8]))
        self.n.append("conc=%d at=%s" % (self.maxconc, self.conc[:4]))
        self.n.append("A1 skip=%s(u%d,r%d) n=%s" % (
            "YES" if sk else "none", (sk >> 10) - 1 if sk else 0, sk & 1023,
            (skn & 1023) if skn else 0))
        self.n.append("A2 evict=%s(u%d,r%d)" % (
            "YES" if ev else "none", (ev >> 10) - 1 if ev else 0, ev & 1023))
        self.n.append("A4 echo=%d(1=saw,2=snapshot)" % ct.read_store(S_ECHO))
        self.n.append("A5 maxid=%d maxr=%d" % (ct.read_store(S_MAXID), self.maxround))
        self.n.append("cfg stale=%d opt=%d n=%d ka=%s km=%s" % (
            STALE, OPTIMISTIC, NBUILD, KILL_ACT, KILL_MUTE))
        self.done = True
        ct.resign("VF_OPT|" + "|".join(self.n))

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

    # ---------------------------------------------------------------- the builder
    def _builder(self, ct):
        r = ct.get_current_round()
        mine = ct.get_id()

        # ---- A1: did this LIVING unit skip a round?
        if self.prev is not None and r - self.prev > 1:
            self.skips += 1
            try:
                if ct.read_store(S_SKIP) == 0:
                    ct.write_store(S_SKIP, pack(mine, r))
                ct.write_store(S_SKIPN, pack(mine, self.skips))
            except Exception:
                pass
        self.prev = r

        # ---- A5
        try:
            hi = max(ct.get_nearby_entities() or [0])
            if hi > self.maxid:
                self.maxid = hi
                if hi > ct.read_store(S_MAXID):
                    ct.write_store(S_MAXID, hi)
        except Exception:
            pass

        # ---- A4: read, in the SAME round, a slot the Core wrote this round
        if r == VIS_ROUND:
            try:
                ct.write_store(S_ECHO, 1 if ct.read_store(S_VIS) == VIS_MAGIC else 2)
            except Exception:
                pass

        # ---- the lease
        raw = ct.read_store(S_LEASE)
        stamp = raw & 1023
        held = (raw >> 10) - 1
        fresh = raw != 0 and (r - stamp) < STALE

        if raw and held == mine:
            self.owner = True
        elif fresh:
            if self.owner:
                # A2: we were the owner and somebody live has taken the lease off us.
                try:
                    if ct.read_store(S_EVICT) == 0:
                        ct.write_store(S_EVICT, pack(mine, r))
                except Exception:
                    pass
            self.owner = False

        if self.owner:
            if r in KILL_MUTE:
                ct.self_destruct()                 # dies WITHOUT renewing
                return
            ct.write_store(S_LEASE, pack(mine, r))
            self._perform(ct, mine, r)
            if r in KILL_ACT:
                ct.self_destruct()                 # renewed and acted, then dies
            return

        if not fresh:
            ct.write_store(S_LEASE, pack(mine, r))
            if OPTIMISTIC:
                self._perform(ct, mine, r)

    def _perform(self, ct, mine, r):
        ct.write_store(S_ACTED, pack(mine, r))
        ct.write_store(S_REP + (mine % 8), r)
        try:
            if ct.can_move(Direction.EAST):
                ct.move(Direction.EAST)
        except Exception:
            pass
