"""Role assignment.

Almost everything in this bot is memoryless, but *role* is the one fact that must
persist, because it is a division of labour rather than a decision about the
current board. A Builder that re-derives "should I be the warden?" every round
will oscillate with its siblings and the Core will be covered by nobody.

There are two roles and the split is deliberately lopsided:

**warden** -- the first Builder the Core spawns. It stays within reach of the
Core for the whole match and does nothing else. This is not a defensive luxury:
a Sentinel deals 6 HP a round and a mender restores 4 for a flat, scale-immune
1 Ti, so a warden absorbs two thirds of the first attacker for pocket change and
buys the rounds the economy needs to become unassailable. Without one, the Core
is shelled from turn ~40 while every Builder is off laying belt.

**field** -- everyone else. Economy, siege, exploration.
"""
from __future__ import annotations

WARDEN = "warden"
FIELD = "field"

# The Core spawns the warden first, so the lowest Builder id on the team is it.
# Ids are assigned in spawn order across both teams, so this cannot be a fixed
# number -- each Builder records the lowest id it has ever seen on our side.


class RoleTracker:
    def __init__(self):
        self.lowest_seen = None
        self.role = None

    def resolve(self, ct, wm) -> str:
        if self.role is not None:
            return self.role
        try:
            me = ct.get_id()
        except Exception:
            return FIELD
        low = me
        for eid, pos, etype in wm.ally_units:
            if eid < low:
                low = eid
        if self.lowest_seen is None or low < self.lowest_seen:
            self.lowest_seen = low
        # Commit once the picture has had a few rounds to settle, so a Builder
        # that spawns before it can see its siblings does not claim the role.
        if wm.round >= 6:
            self.role = WARDEN if me == self.lowest_seen else FIELD
            return self.role
        return WARDEN if me == self.lowest_seen else FIELD
