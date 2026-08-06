"""Why was the role vacant for FOUR rounds on aurora vs tempest, when every other handover took two?

vf_lease measured a 44>49 gap there.  The arithmetic explanation -- "the round-46 challenge winner
died before it could confirm on round 47" -- is an INFERENCE from the gap size.  This probe measures
it: every builder stamps a private slot with the round number on EVERY turn it takes, alive or not
acting, so the Core can print the live roster next to the lease word for each round of the gap.

aurora/tempest is deterministic (fcode 2.3.6, verified: the id roster is [3,5,8,10,13,14] on every
run), so the per-builder slots are hard-wired by id.  If id 13 stops stamping after round 46 while
the lease word still reads (13, 46), the claimant died holding an unconfirmed claim and the other
builders stood down in front of a corpse's fresh timestamp.
"""

from fcode import Controller, Direction, EntityType, Position

S_LEASE, S_ACTED = 0, 1
SEAT = {13: 2, 10: 3, 14: 4, 5: 5, 8: 6, 3: 7}   # id -> private "I ran this round" slot

STALE = 2
NBUILD = 6
KILL_ACT = (25, 70)
KILL_MUTE = (45, 95)
LO, HI = 43, 51


def pack(uid, r):
    return ((uid + 1) << 10) | r


class Player:
    def __init__(self):
        self.n = []
        self.done = False
        self.owner = False
        self.log = []

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

        if LO <= r <= HI:
            lease = ct.read_store(S_LEASE)
            acted = ct.read_store(S_ACTED)
            live = "".join(str(u) + "," for u, s in sorted(SEAT.items())
                           if ct.read_store(s) == r - 1)
            self.log.append("r%d L=%s%s A=%s%s live=%s" % (
                r, (lease >> 10) - 1 if lease else "-", "@%d" % (lease & 1023) if lease else "",
                (acted >> 10) - 1 if acted else "-", "@%d" % (acted & 1023) if acted else "",
                live or "none"))

        if r == HI + 1:
            self.done = True
            ct.resign("VFW|" + "|".join(self.log))

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
        seat = SEAT.get(mine)
        if seat is not None:
            ct.write_store(seat, r)          # proof of life, every round, owner or not

        raw = ct.read_store(S_LEASE)
        stamp = raw & 1023
        held = (raw >> 10) - 1
        fresh = raw != 0 and (r - stamp) < STALE

        if raw and held == mine:
            self.owner = True
        elif fresh:
            self.owner = False

        if self.owner:
            if r in KILL_MUTE:
                ct.self_destruct()
                return
            ct.write_store(S_LEASE, pack(mine, r))
            ct.write_store(S_ACTED, pack(mine, r))
            try:
                if ct.can_move(Direction.EAST):
                    ct.move(Direction.EAST)
            except Exception:
                pass
            if r in KILL_ACT:
                ct.self_destruct()
            return

        if not fresh:
            ct.write_store(S_LEASE, pack(mine, r))
