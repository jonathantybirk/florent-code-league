"""ECON Q1: price the FINAL-CONVEYOR kill in titanium and in rounds.

`a2cut` measured what a severed chain is worth: exactly 2.50 Ti/round, and the production
lost while it is severed is annihilated except for one 10-Ti stack. This probe pays the
attacker's side of that bill against a live opponent.

`a2destroy` established that `destroy()` and `heal()` are NOT team-blind (`can_destroy` is
False on an enemy building, `GameError: Cannot destroy`) while `fire()` IS. So a Builder Bot
kills a 20 HP conveyor with BUILDER_BOT_ATTACK_DAMAGE=2 -- ten shots at 2 Ti each.

Arena `maps/lab/para.map26`, opponent `a2econ`: harvester (8,5), belt (9,5)(10,5)(11,5)
(12,5) all EAST into Core B footprint tile (13,5). We walk to (12,6) and shoot (12,5) --
the last link, the one whose loss zeroes the whole upstream chain -- until it dies, then
sit still. `a2econ` never rebuilds, so `b_titanium_collected` is the clean denial figure.
"""

from fcode import Controller, Direction, EntityType, GameError, Position

TARGET = Position(12, 5)
STAND = Position(12, 6)


class Player:
    def __init__(self):
        self.spawned = False
        self.shots = 0
        self.kills = 0
        self.live = False
        self.dead = None
        self.arrived = None
        self.note = ""

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.note = type(exc).__name__[:6] + ":" + str(exc)[:18]

    def _walk(self, ct, me, gx, gy):
        order = []
        if me.x != gx:
            order.append(Direction.EAST if gx > me.x else Direction.WEST)
        if me.y != gy:
            order.append(Direction.SOUTH if gy > me.y else Direction.NORTH)
        for d in order:
            if ct.can_move(d):
                ct.move(d)
                return

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()
        if et == EntityType.CORE:
            if not self.spawned and ct.can_spawn(Position(3, 7)):
                ct.spawn_builder(Position(3, 7))
                self.spawned = True
            return
        if et != EntityType.BUILDER_BOT:
            return

        me = ct.get_position()
        if me != STAND:
            self._walk(ct, me, STAND.x, STAND.y)
            return
        if self.arrived is None:
            self.arrived = r

        bid = ct.get_tile_building_id(TARGET)
        if bid is None:
            if self.live:
                self.kills += 1
                self.live = False
                if self.dead is None:
                    self.dead = r
        else:
            self.live = True
            if ct.can_fire(TARGET):
                ct.fire(TARGET)
                self.shots += 1

        if r == 995:
            ct.resign(("SNIP arrive=%s firstkill=%s kills=%d shots=%d shotcost=%d "
                       "ti=%d up=%s %s" % (
                           self.arrived, self.dead, self.kills, self.shots,
                           self.shots * 2, ct.get_global_resources(),
                           bid is not None, self.note))[:495])
