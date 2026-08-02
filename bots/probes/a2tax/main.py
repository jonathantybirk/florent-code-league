"""ECON Q4: the real cost of the harvester economy -- the GLOBAL COST-SCALE TAX.

A harvester is +5 percentage points of global cost scale and each conveyor is +1 (G07),
and the scale applies to EVERY entity type. This probe reads the live cost table
(`get_*_cost()`) after each build so the tax on the *next* purchase is measured, not
inferred from the formula.

Arena `maps/lab/scal.map26` (24x20): Core A anchor (1,9), ore at (6,8) and (6,10); a builder
standing on (6,9) is orthogonally adjacent to both ore tiles.

Checkpoints: base (nothing built) -> +builder -> +harvester1 -> +harvester2 -> +2 conveyors.
Reports scale and the gunner / sentinel / launcher / builder-bot price at each step, which
is exactly the bill a fighting bot pays for owning an economy.
"""

from fcode import Controller, Direction, EntityType, GameError, Position

SPAWN = Position(3, 9)
STAND = Position(6, 9)
H1 = Position(6, 8)
H2 = Position(6, 10)
C1 = Position(7, 9)
C2 = Position(5, 9)


class Player:
    def __init__(self):
        self.spawned = False
        self.rows = []
        self.phase = 0
        self.note = ""

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.note = type(exc).__name__[:6] + ":" + str(exc)[:18]

    def _row(self, ct, tag):
        self.rows.append("%s s%.0f g%d se%d l%d b%d h%d c%d" % (
            tag, ct.get_scale_percent(), ct.get_gunner_cost(), ct.get_sentinel_cost(),
            ct.get_launcher_cost(), ct.get_builder_bot_cost(), ct.get_harvester_cost(),
            ct.get_conveyor_cost()))

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()
        if et == EntityType.CORE:
            # No cost row here: the Core's Player instance is a different sub-interpreter
            # and its notes never reach the reporting builder (M07). Base costs are the
            # GameConstants themselves; the builder's first row is the +builder state.
            if not self.spawned and ct.can_spawn(SPAWN):
                ct.spawn_builder(SPAWN)
                self.spawned = True
            return
        if et != EntityType.BUILDER_BOT:
            return

        me = ct.get_position()
        if me != STAND:
            if not self.rows:
                self._row(ct, "+bot")
            if ct.can_move(Direction.EAST):
                ct.move(Direction.EAST)
            return

        if self.phase == 0:
            if not self.rows:
                self._row(ct, "+bot")
            ct.build_harvester(H1)
            self._row(ct, "+h1")
            self.phase = 1
            return
        if self.phase == 1:
            ct.build_harvester(H2)
            self._row(ct, "+h2")
            self.phase = 2
            return
        if self.phase == 2:
            ct.build_conveyor(C1, Direction.WEST)
            self._row(ct, "+c1")
            self.phase = 3
            return
        if self.phase == 3:
            ct.build_conveyor(C2, Direction.WEST)
            self._row(ct, "+c2")
            self.phase = 4
            return
        if self.phase == 4:
            ct.resign((" | ".join(self.rows) + " " + self.note)[:495])
            self.phase = 5
