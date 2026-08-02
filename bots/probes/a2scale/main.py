"""AREA-2 (e): does the global COST SCALE fall when a building DIES to DAMAGE?

REPAIRED 2026-08-02.  The old arena `openfield` was lost with the first hunt's lab maps, so this
probe was running on whatever map it was handed and reporting nothing.  It now runs on
`maps/lab/csopen` (26x14, zero walls, Core A anchor (1,6)), rebuilt by `maps/lab/mkcs.py`.

`cs_sd` established that VOLUNTARY removal refunds the scale in full: destroy() a barrier and the
scale drops the 1 point it cost, self_destruct() a gunner and it drops 10, self_destruct() a
builder bot and it drops 20 -- with no titanium refund at all.  The strategically decisive
question is the involuntary case: if a building is KILLED, does its owner get the scale back?

  YES -> every building an opponent grinds down makes our next build CHEAPER, and conversely
         killing their stuff subsidises their rebuild.  Attrition is partly self-defeating.
  NO  -> a killed building is a permanent tax on its owner and grinding is doubly good.

Setup: the builder spawns at (3,6), walks east to (5,6), builds a BARRIER at (5,5) and a GUNNER
at (5,7) facing NORTH, then steps EAST to (6,6) out of the gunner's ray.  The Core converts
ammunition, and the team-blind gunner (G10) grinds our own barrier 30 -> 20 -> 10 -> dead while
the builder watches the scale every round.
"""

from fcode import Controller, Direction, EntityType, GameError, Position

SPAWN = Position(3, 6)
HOME = Position(5, 6)
BAR = Position(5, 5)
GUN = Position(5, 7)


def e(exc):
    return type(exc).__name__[:4] + ":" + str(exc)[:20]


class Player:
    def __init__(self):
        self.n = []
        self.spawned = False
        self.phase = 0
        self.done = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.n.append("TOP:" + e(exc))

    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            if not self.spawned and ct.can_spawn(SPAWN):
                ct.spawn_builder(SPAWN)
                self.spawned = True
            try:
                if ct.get_global_ammo() < 20 and ct.can_convert_ammo(20):
                    ct.convert_ammo(20)
            except Exception:
                pass
            return

        if et == EntityType.GUNNER:
            try:
                tgt = ct.get_gunner_target()
                if tgt is not None and ct.can_fire(tgt):
                    ct.fire(tgt)
            except Exception:
                pass
            return

        if et != EntityType.BUILDER_BOT or self.done:
            return

        pos = ct.get_position()
        if self.phase == 0:
            if pos.x != HOME.x or pos.y != HOME.y:
                d = pos.cardinal_direction_to(HOME)
                if ct.can_move(d):
                    ct.move(d)
                return
            self.n.append("s0=%.0f" % ct.get_scale_percent())
            ct.build_barrier(BAR)
            self.n.append("bar=%.0f" % ct.get_scale_percent())
            self.phase = 1
            return

        if self.phase == 1:
            ct.build_gunner(GUN, Direction.NORTH)
            self.n.append("gun=%.0f" % ct.get_scale_percent())
            self.phase = 2
            return

        if self.phase == 2:
            if ct.can_move(Direction.EAST):
                ct.move(Direction.EAST)
                self.phase = 3
            return

        bid = None
        try:
            bid = ct.get_tile_building_id(BAR)
        except Exception:
            return
        if bid is not None:
            hp = ct.get_hp(bid)
            tag = "r%d h%d s%.0f" % (ct.get_current_round(), hp, ct.get_scale_percent())
            if not self.n or self.n[-1][:2] != "r%d" % ct.get_current_round():
                if len(self.n) < 14:
                    self.n.append(tag)
            return
        self.done = True
        self.n.append("KILLED r%d s=%.1f bc=%d ti=%d u=%d" % (
            ct.get_current_round(), ct.get_scale_percent(), ct.get_barrier_cost(),
            ct.get_global_resources(), ct.get_unit_count()))
        ct.resign(("A2SCALE " + " | ".join(self.n))[:495])
