"""AREA 3a follow-up: can the Core HEAL or DESTROY at CORE_ACTION_RADIUS_SQ = 8?

corelab: Core A anchor (6,9), footprint (6,9)(7,9)(6,10)(7,10).
r0  Core spawns a builder on ring tile (8,9).
r1+ builder builds a barrier at (9,9)  (d^2 = 4 from footprint tile (7,9)),
    then shoots it twice to damage it (builder attack = 2 dmg, team-blind test).
r10 Core reports can_heal / heal / can_destroy / destroy against that barrier,
    plus the same for a tile at d^2 = 8 and one at d^2 = 9.
"""

from fcode import Controller, Direction, EntityType, GameError, Position

BAR = Position(9, 9)      # d^2 = 4 from footprint (7,9)
HOME = Position(8, 9)


def e(exc):
    return type(exc).__name__[:4] + ":" + str(exc)[:18]


class Player:
    def __init__(self):
        self.n = []
        self.done = False
        self.spawned = False
        self.built = False
        self.shots = 0

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.n.append("T:" + e(exc))

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()

        if et == EntityType.BUILDER_BOT:
            if not self.built:
                if ct.can_build_barrier(BAR):
                    ct.build_barrier(BAR)
                    self.built = True
                return
            if self.shots < 2 and ct.can_fire(BAR):
                ct.fire(BAR)
                self.shots += 1
            return

        if et != EntityType.CORE or self.done:
            return

        if r == 0 and not self.spawned:
            if ct.can_spawn(HOME):
                ct.spawn_builder(HOME)
                self.spawned = True
            return

        if r != 10:
            return
        self.done = True

        bid = ct.get_tile_building_id(BAR)
        self.n.append("bar id=%s hp=%s" % (bid, ct.get_hp(bid) if bid else "-"))

        def t(label, fn):
            try:
                self.n.append("%s=%s" % (label, str(fn())[:14]))
            except Exception as exc:
                self.n.append("%s!%s" % (label, e(exc)))

        t("canheal4", lambda: ct.can_heal(BAR))
        t("heal4", lambda: ct.heal(BAR))
        t("hpafter", lambda: ct.get_hp(ct.get_tile_building_id(BAR)))
        t("candes4", lambda: ct.can_destroy(BAR))
        t("des4", lambda: ct.destroy(BAR))
        t("stillthere", lambda: ct.get_tile_building_id(BAR))
        ct.resign("GGP|" + "|".join(self.n))
