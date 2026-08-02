"""Which titanium costs are SCALE-EXEMPT?

`cs_rot` showed gunner rotation is charged a flat 10 Ti at scale 210 while a new gunner costs 21.
This probe checks the other three recurring spends the same way, all at scale ~200:

  builder ATTACK   BUILDER_BOT_ATTACK_COST = 2   -> flat 2, or floor(scale/100 * 2) = 4?
  builder HEAL     BUILDER_BOT_HEAL_COST   = 1   -> flat 1, or 2?  and is HEAL_AMOUNT still 4?
  convert_ammo(n)  documented 1:1              -> flat 1:1, or scaled titanium per ammo?

Arena `lab/csopen`.  The Core spawns five Builder Bots so the team scale is 200% before anything
is measured; builder #0 walks to (5,6) and puts a 30-HP barrier at (5,5) to attack and heal.  The
Core's convert_ammo() measurement is relayed to the reporting builder through the 16-slot store
(one-round write lag, G20): slot 4 = titanium spent, slot 5 = ammo gained, slot 6 = ready flag.
"""

from fcode import Controller, Direction, EntityType, GameError, Position

HOME = Position(5, 6)
BAR = Position(5, 5)
RING = (Position(3, 6), Position(3, 5), Position(3, 7), Position(3, 8), Position(0, 6))
CONVERT = 25


def e(exc):
    return type(exc).__name__[:4] + ":" + str(exc)[:20]


class Player:
    def __init__(self):
        self.n = []
        self.role = None
        self.done = False
        self.converted = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.n.append("!" + e(exc))

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()

        if et == EntityType.CORE:
            if r < len(RING) and ct.can_spawn(RING[r]):
                ct.spawn_builder(RING[r])
            if r == 10 and not self.converted:
                self.converted = True
                ti0 = ct.get_global_resources()
                am0 = ct.get_global_ammo()
                try:
                    ct.convert_ammo(CONVERT)
                    ct.write_store(4, ti0 - ct.get_global_resources())
                    ct.write_store(5, ct.get_global_ammo() - am0)
                    ct.write_store(6, 1)
                except Exception:
                    ct.write_store(6, 2)
            return

        if et != EntityType.BUILDER_BOT or self.done:
            return
        if self.role is None:
            self.role = "b0" if r <= 1 else "sit"
        if self.role != "b0":
            return

        pos = ct.get_position()
        if pos.x != HOME.x or pos.y != HOME.y:
            d = pos.cardinal_direction_to(HOME)
            if ct.can_move(d):
                ct.move(d)
            return

        def hp():
            b = ct.get_tile_building_id(BAR)
            return -1 if b is None else ct.get_hp(b)

        if r == 6:
            self.n.append("s=%.0f" % ct.get_scale_percent())
            ct.build_barrier(BAR)
            self.n.append("bar s=%.0f hp=%d brcost=%d" % (
                ct.get_scale_percent(), hp(), ct.get_barrier_cost()))
        elif r == 7:
            ti0 = ct.get_global_resources()
            h0 = hp()
            ct.fire(BAR)
            self.n.append("ATK dti=%d dhp=%d" % (
                ct.get_global_resources() - ti0, hp() - h0))
        elif r == 8:
            ti0 = ct.get_global_resources()
            h0 = hp()
            ct.fire(BAR)
            self.n.append("ATK2 dti=%d dhp=%d" % (
                ct.get_global_resources() - ti0, hp() - h0))
        elif r == 9:
            ti0 = ct.get_global_resources()
            h0 = hp()
            ct.heal(BAR)
            self.n.append("HEAL dti=%d dhp=%d" % (
                ct.get_global_resources() - ti0, hp() - h0))
        elif r == 12:
            self.n.append("CONV flag=%d dti=%d dammo=%d ask=%d s=%.0f" % (
                ct.read_store(6), ct.read_store(4), ct.read_store(5),
                CONVERT, ct.get_scale_percent()))
        elif r == 14:
            self.done = True
            ct.resign(("CSEXEMPT " + " | ".join(self.n))[:495])
