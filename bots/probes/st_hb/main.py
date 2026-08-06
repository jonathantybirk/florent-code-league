"""A role claim that SURVIVES THE CLAIMANT'S DEATH: a one-slot lease with a round stamp.

The shipped protocol writes `owner_id + 1` into a slot and never touches it again.  When that unit
dies the slot still names it, every other builder reads a non-zero claim, stands down forever, and
the role is never performed again.  `st_id` shows why the obvious repair does not work: get_hp(id)
on a LIVE teammate raises GameError the moment it leaves the caller's vision, so no unit can ask
"is the claimant still alive?".  Liveness has to travel in the store.

THE LEASE.  One slot, same slot the id used to sit in, no extra budget:

    word = (owner_id + 1) << 10 | (round the owner last renewed)      # round < 1024, u32 is 32 bits

  * the owner rewrites the word EVERY round it runs, so a fresh word proves the owner ran last round
  * a reader treats the lease as expired when `round - stamp >= STALE`.  Writes land one round late,
    so the freshest stamp a reader can ever see is `round - 1`; STALE = 2 is therefore the tightest
    threshold that can never evict a living owner.
  * an expired or zero lease is CHALLENGED by writing your own word.  Every idle builder challenges
    in the same round; the store keeps exactly one of them (highest entity id -- measured in st_id),
    so the race needs no tie-break and no confirm handshake.  The losers read a foreign id the next
    round, see a fresh lease, and stand down.

WHAT THIS PROBE MEASURES.  Four builders, one ATTACKER role (walk east and stamp S_ACTED).  The
owner is killed twice: on round 20 it renews, acts, and self_destructs in the same round (the
realistic case -- a unit shot dead has already taken its turn), and on round 40 it self_destructs
without renewing (killed before acting).  The Core reads the transcript out of the store and
resigns with: every round the role was performed, every owner change, the gap after each kill, and
the peak number of simultaneous owners (each builder reports into its own slot 8 + id % 4, so
double ownership cannot hide behind a slot collision).

Arena `scal`.
"""

from fcode import Controller, Direction, EntityType, Position

S_LEASE = 0          # (owner_id + 1) << 10 | stamp
S_ACTED = 1          # (actor_id + 1) << 10 | the round the role was actually performed
S_REP = 8            # 8..15 -- per-builder "I acted on round N" report, indexed by id % 8

STALE = 2            # challenge once round - stamp >= this
OPTIMISTIC = False   # act on the round you challenge, before you know you won
KILL_ACT = 20         # owner renews, acts, then dies in the same round
KILL_MUTE = 40        # owner dies without renewing
SPAWN_UNTIL = 3      # spawn one builder a round on rounds 0..SPAWN_UNTIL
LAST = 60


def pack(uid, r):
    return ((uid + 1) << 10) | r


class Player:
    def __init__(self):
        self.n = []
        self.done = False
        self.owner = False
        self.acted = []
        self.owners = []
        self.last_ar = -1
        self.last_ow = -1
        self.ids = []
        self.conc = []
        self.maxconc = 0

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

    # ---------------------------------------------------------------------- core
    def _core(self, ct):
        if self.done:
            return
        r = ct.get_current_round()

        if r <= SPAWN_UNTIL:
            self._spawn(ct)
            return
        if r == SPAWN_UNTIL + 1:
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
        if c > self.maxconc:
            self.maxconc = c
        if c > 1:
            self.conc.append(r - 1)

        # Report before a real opponent kills the Core, or the whole run is lost (HARNESS).
        if r == LAST or ct.get_hp() < 140:
            gaps = []
            for a, b in zip(self.acted, self.acted[1:]):
                if b - a > 1:
                    gaps.append("%d>%d(%d)" % (a, b, b - a - 1))
            self.n.append("ids=%s mod8=%s" % (self.ids, [i % 8 for i in self.ids]))
            self.n.append("acts=%d span=%d..%d" % (
                len(self.acted), self.acted[0] if self.acted else -1,
                self.acted[-1] if self.acted else -1))
            self.n.append("gaps=" + (",".join(gaps) if gaps else "none"))
            self.n.append("owners=" + ",".join("%d@%d" % (o, a) for a, o in self.owners[:6]))
            self.n.append("maxconc=%d at=%s" % (self.maxconc, self.conc[:6]))
            self.n.append("stale=%d opt=%d kill=%d,%d" % (STALE, OPTIMISTIC, KILL_ACT, KILL_MUTE))
            self.done = True
            ct.resign("HB|" + "|".join(self.n))

    def _spawn(self, ct):
        p = ct.get_position()
        for dx, dy in ((2, 0), (2, 1), (0, -1), (1, -1), (-1, 0), (-1, 1), (0, 2), (1, 2)):
            q = Position(p.x + dx, p.y + dy)
            try:
                if ct.can_spawn(q):
                    ct.spawn_builder(q)
                    return
            except Exception:
                continue

    # ------------------------------------------------------------------- builder
    def _builder(self, ct):
        r = ct.get_current_round()
        mine = ct.get_id()
        raw = ct.read_store(S_LEASE)
        stamp = raw & 1023
        held = (raw >> 10) - 1
        fresh = raw != 0 and (r - stamp) < STALE

        if raw and held == mine:
            self.owner = True                 # our own claim came back: the role is ours
        elif fresh:
            self.owner = False                # somebody live holds it

        if self.owner:
            if r == KILL_MUTE:
                ct.self_destruct()            # dies WITHOUT renewing
                return
            ct.write_store(S_LEASE, pack(mine, r))
            self._perform(ct, mine, r)
            if r == KILL_ACT:
                ct.self_destruct()            # renewed and acted, then dies
            return

        if not fresh:
            ct.write_store(S_LEASE, pack(mine, r))     # challenge; resolved next round
            if OPTIMISTIC:
                self._perform(ct, mine, r)

    def _perform(self, ct, mine, r):
        """The role itself: advance east and record that the role happened this round."""
        ct.write_store(S_ACTED, pack(mine, r))
        ct.write_store(S_REP + (mine % 8), r)
        try:
            if ct.can_move(Direction.EAST):
                ct.move(Direction.EAST)
        except Exception:
            pass
