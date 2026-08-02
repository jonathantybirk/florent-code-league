"""A4SIT -- do nothing but STAND on your own Core ring. Zero titanium spent after the builders.

Hypothesis under test. `bot/main.py::_run_rush` decides a firing tile is taken by looking at
`self._building_at(bpos)` ONLY. A Builder Bot is not a building, so a body parked on the chosen
firing tile passes that check, the executor walks to it, `can_build_gunner` refuses, and the branch
returns True having spent the round WITHOUT touching `rush_stuck` and WITHOUT blacklisting the tile.
The documented give-up for this branch was deliberately left out ("It MEASURED WORSE: 29-13 against
31-11"), so there is nothing to break the loop.

If that is right, a handful of stationary bodies on the ring tiles the attacker's planner ranks
first should cost it its entire offence, for zero titanium and zero cleverness.

Bodies also BLOCK a Gunner line in their own right -- the 2.3.3 `can_fire` docstring says "builder
bots and buildings are both targetable and blocking" -- so each one is worth a Barrier for as long
as it lives (40 HP against a Barrier's 30).
"""

from fcode import Controller, EntityType, Position

S_X, S_Y = 0, 1
N_BUILDERS = 6


def foot_of(a):
    return ((a[0], a[1]), (a[0] + 1, a[1]), (a[0], a[1] + 1), (a[0] + 1, a[1] + 1))


class Player:
    def __init__(self):
        self.spawned = 0

    def run(self, ct: Controller) -> None:
        try:
            if ct.get_entity_type() != EntityType.CORE:
                return                     # builders: stand still, forever
        except Exception:
            return
        try:
            self._core(ct)
        except Exception:
            return

    def _core(self, ct):
        p = ct.get_position()
        ct.write_store(S_X, p.x + 1)
        ct.write_store(S_Y, p.y + 1)
        if self.spawned >= N_BUILDERS:
            return
        try:
            if ct.get_action_cooldown() != 0:
                return
            if ct.get_global_resources() < ct.get_builder_bot_cost():
                return
            w, h = ct.get_map_width(), ct.get_map_height()
        except Exception:
            return
        a = (p.x, p.y)
        f = set(foot_of(a))
        cx, cy = (w - 1) / 2.0, (h - 1) / 2.0
        ring = []
        for dx in range(-1, 3):
            for dy in range(-1, 3):
                t = (a[0] + dx, a[1] + dy)
                if t in f or not (0 <= t[0] < w and 0 <= t[1] < h):
                    continue
                ring.append(t)
        # nearest the middle of the board first: that is the side the attack comes from, and the
        # side whose ring tiles a standoff-minimising planner ranks first.
        ring.sort(key=lambda t: (t[0] - cx) ** 2 + (t[1] - cy) ** 2)
        for t in ring:
            tp = Position(t[0], t[1])
            try:
                if ct.can_spawn(tp):
                    ct.spawn_builder(tp)
                    self.spawned += 1
                    return
            except Exception:
                continue
