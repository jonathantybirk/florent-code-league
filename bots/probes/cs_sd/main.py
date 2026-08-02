"""Q3/Q5 -- does the global cost scale ever go BACK DOWN?

Four different ways of removing something we paid a scale increment for, all measured by one
reporting Builder Bot parked at (5,6) on `lab/csopen`:

  1  build a BARRIER (+1pp) and voluntarily destroy() it
  2  build a CONVEYOR (+1pp) and voluntarily destroy() it
  3  build a GUNNER (+10pp) and let the GUNNER call self_destruct() on itself
  4  build a second GUNNER and destroy() it from the builder instead
  5  spawn a second BUILDER BOT (+20pp) and let it call self_destruct()

If self_destruct() refunds scale, the exploit is enormous: build cheap early, blow the unit up,
buy expensive turrets back at the low scale, repeat.  If it does not, every purchase is a
permanent tax and turtling is self-limiting.

Also measures BUILDER_BOT_SELF_DESTRUCT_DAMAGE: builder #2 walks to (5,8), orthogonally adjacent
to a permanent 30-HP barrier at (5,7), and self-destructs there.  The reporter reads that
barrier's HP before and after.

Timeline is round-gated, so entity-order effects are explicit: the reporter has the lowest id and
always acts before the turrets and before builder #2.
"""

from fcode import Controller, Direction, EntityType, GameError, Position

HOME = Position(5, 6)
WIT = Position(5, 7)      # permanent barrier, blast witness
BAR = Position(5, 5)      # build/destroy barrier
CNV = Position(4, 6)      # build/destroy conveyor
GUN = Position(6, 6)      # gunner slot
SPAWN1 = Position(3, 6)
SPAWN2 = Position(3, 7)
WALK2 = (Position(4, 7), Position(4, 8), Position(5, 8))


def e(exc):
    return type(exc).__name__[:4] + ":" + str(exc)[:20]


class Player:
    def __init__(self):
        self.n = []
        self.role = None
        self.step = 0
        self.said = False
        self.done = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.n.append("!" + e(exc))

    def s(self, ct):
        return "%.0f" % ct.get_scale_percent()

    def hp(self, ct, p):
        try:
            b = ct.get_tile_building_id(p)
            return "n" if b is None else str(ct.get_hp(b))
        except Exception:
            return "?"

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()

        if et == EntityType.CORE:
            if r == 0 and ct.can_spawn(SPAWN1):
                ct.spawn_builder(SPAWN1)
            if r == 20 and ct.can_spawn(SPAWN2):
                ct.spawn_builder(SPAWN2)
            return

        if et == EntityType.GUNNER:
            if r <= 10 and not self.said:
                self.said = True
                ct.self_destruct()
            return

        if et != EntityType.BUILDER_BOT or self.done:
            return

        if self.role is None:
            self.role = "rep" if r <= 2 else "sui"

        # ---------------- builder #2: walk next to the witness barrier, then blow up
        if self.role == "sui":
            pos = ct.get_position()
            if self.step < len(WALK2):
                tgt = WALK2[self.step]
                if pos.x == tgt.x and pos.y == tgt.y:
                    self.step += 1
                    return
                d = pos.cardinal_direction_to(tgt)
                if ct.can_move(d):
                    ct.move(d)
                return
            if r >= 24:
                ct.self_destruct()
            return

        # ---------------- reporter
        pos = ct.get_position()
        if pos.x != HOME.x or pos.y != HOME.y:
            d = pos.cardinal_direction_to(HOME)
            if ct.can_move(d):
                ct.move(d)
            return

        if r == 3:
            self.n.append("s0=" + self.s(ct))
            ct.build_barrier(WIT)
            self.n.append("wit=" + self.s(ct))
        elif r == 4:
            ct.build_barrier(BAR)
            self.n.append("bar=" + self.s(ct))
        elif r == 5:
            ti0 = ct.get_global_resources()
            ct.destroy(BAR)
            self.n.append("barDES=" + self.s(ct)
                          + "/dti" + str(ct.get_global_resources() - ti0))
        elif r == 6:
            ct.build_conveyor(CNV, Direction.EAST)
            self.n.append("cnv=" + self.s(ct))
        elif r == 7:
            ct.destroy(CNV)
            self.n.append("cnvDES=" + self.s(ct))
        elif r == 8:
            ct.build_gunner(GUN, Direction.NORTH)
            self.n.append("gun=" + self.s(ct) + "/u" + str(ct.get_unit_count()))
        elif r == 10:
            self.n.append("gunSD=" + self.s(ct) + "/u" + str(ct.get_unit_count())
                          + "/gone" + str(ct.get_tile_building_id(GUN) is None))
        elif r == 11:
            ct.build_gunner(GUN, Direction.NORTH)
            self.n.append("gun2=" + self.s(ct))
        elif r == 12:
            try:
                self.n.append("cdes=" + str(ct.can_destroy(GUN)))
                ct.destroy(GUN)
                self.n.append("gun2DES=" + self.s(ct) + "/u" + str(ct.get_unit_count()))
            except Exception as exc:
                self.n.append("gun2DES!" + e(exc))
        elif r == 26:
            self.n.append("pre=" + self.s(ct) + "/u" + str(ct.get_unit_count())
                          + "/hp" + self.hp(ct, WIT)
                          + "/bbc" + str(ct.get_builder_bot_cost()))
        elif r == 29:
            self.n.append("post=" + self.s(ct) + "/u" + str(ct.get_unit_count())
                          + "/hp" + self.hp(ct, WIT)
                          + "/bbc" + str(ct.get_builder_bot_cost()))
        elif r == 31:
            self.done = True
            ct.resign(("CSSD " + " ".join(self.n))[:495])
