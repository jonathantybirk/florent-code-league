"""Q3 (the involuntary half) -- when an ENEMY kills our building, do WE get the scale point back?

`a2scale` answered the same-team case (our own team-blind gunner ground down our own barrier and
our scale fell 131 -> 130).  This pair separates owner from killer completely.

This bot is the VICTIM and the reporter.  Run it as team B on `lab/cstiny` against `cs_grind`:

    runfull cs_grind --map lab/cstiny --vs cs_victim

Core B anchor is (9,4).  The builder spawns at (8,4), steps west to (7,4) and builds a BARRIER at
(6,4), which is exactly 2 tiles east of the gunner cs_grind puts at (4,4).  The victim then reads
its own scale every round and resigns the moment the barrier stops existing.

  scale returns to the pre-barrier value -> a kill REFUNDS the owner, attrition subsidises the
                                            defender's rebuild
  scale stays up                          -> a killed building is a permanent tax on its owner
"""

from fcode import Controller, Direction, EntityType, GameError, Position

SPAWN = Position(8, 4)
HOME = Position(7, 4)
BAR = Position(6, 4)


class Player:
    def __init__(self):
        self.n = []
        self.spawned = False
        self.built = False
        self.done = False
        self.hp0 = 0

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.n.append("!" + type(exc).__name__ + ":" + str(exc)[:18])

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()
        if et == EntityType.CORE:
            if not self.spawned and ct.can_spawn(SPAWN):
                ct.spawn_builder(SPAWN)
                self.spawned = True
            return
        if et != EntityType.BUILDER_BOT or self.done:
            return

        pos = ct.get_position()
        if not self.built:
            if pos.x != HOME.x or pos.y != HOME.y:
                d = pos.cardinal_direction_to(HOME)
                if ct.can_move(d):
                    ct.move(d)
                return
            self.n.append("pre=%.0f" % ct.get_scale_percent())
            ct.build_barrier(BAR)
            self.built = True
            self.n.append("bar=%.0f br=%d" % (ct.get_scale_percent(), ct.get_barrier_cost()))
            return

        bid = ct.get_tile_building_id(BAR)
        if bid is not None:
            hp = ct.get_hp(bid)
            if hp != self.hp0:
                self.hp0 = hp
                if len(self.n) < 9:
                    self.n.append("r%d hp%d s%.0f" % (r, hp, ct.get_scale_percent()))
            if r < 80:
                return
            self.done = True
            ct.resign(("CSVICTIM NEVERKILLED " + " | ".join(self.n))[:495])
            return

        self.done = True
        ct.resign(("CSVICTIM KILLED r%d s=%.1f br=%d u=%d | %s" % (
            r, ct.get_scale_percent(), ct.get_barrier_cost(), ct.get_unit_count(),
            " | ".join(self.n)))[:495])
