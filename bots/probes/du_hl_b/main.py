"""VERIFY probe, side B: the side that LOSES the entity-id race but keeps a
builder adjacent to its Sentinel healing it every round.

maps/lab/firstshot.map26.  B's core is id 2, so it always acts after A's core:
B's builder holds id 4 (A's holds 3) and B's Sentinel is therefore created
second on the shared build round and holds the HIGHER turret id.  Under the bare
duel that is a guaranteed loss.

B spawns a SECOND builder on round 2 (id 5 -- still below both turret ids, so it
acts before either turret fires) which walks to (9,5), orthogonally adjacent to
B's turret tile (9,4) and OFF the y=4 firing lane that A's Sentinel covers
((7,4)..(11,4)).  From round 21 it calls heal(9,4): +4 HP for 1 Ti, one action
per round (GameConstants.HEAL_AMOUNT = 4, BUILDER_BOT_HEAL_COST = 1).

HEAL = False turns the second builder into an inert control with the identical
entity-id layout, so the only difference between the two runs is the healing.
"""

from fcode import Controller, Direction, EntityType, Position

HEAL = True

SPAWN = Position(12, 4)
HSPAWN = Position(12, 5)
TPOS = Position(9, 4)
ETPOS = Position(6, 4)
HPOS = Position(9, 5)
FACING = Direction.WEST
WALK = Direction.WEST
BUILD_ROUND = 20
HEAL_FROM = 21


class Player:
    def __init__(self):
        self.err = []
        self.spawned = 0
        self.step = 0
        self.role = None
        self.shots = 0

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            if len(self.err) < 6:
                self.err.append("%s:%s" % (type(exc).__name__, str(exc)[:50]))

    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            self._core(ct)
        elif et == EntityType.BUILDER_BOT:
            self._builder(ct)
        elif et in (EntityType.SENTINEL, EntityType.GUNNER):
            self._turret(ct)

    def _core(self, ct):
        r = ct.get_current_round()
        if self.spawned == 0 and r >= 1 and ct.can_spawn(SPAWN):
            ct.spawn_builder(SPAWN)
            self.spawned = 1
            return
        if self.spawned == 1 and r >= 2 and ct.can_spawn(HSPAWN):
            ct.spawn_builder(HSPAWN)
            self.spawned = 2
            return
        try:
            if (ct.get_global_ammo() < 300 and ct.get_global_resources() > 200
                    and ct.can_convert_ammo(50)):
                ct.convert_ammo(50)
        except Exception:
            pass

    def _builder(self, ct):
        if self.role is None:
            # the turret builder is spawned first and therefore holds the lower id
            self.role = "turret" if ct.get_id() <= 4 else "healer"
        if self.role == "healer":
            self._healer(ct)
            return

        r = ct.get_current_round()
        if self.step < 2:
            if ct.can_move(WALK):
                ct.move(WALK)
                self.step += 1
            return
        if self.step == 2:
            if r < BUILD_ROUND:
                return
            try:
                if not ct.can_build_sentinel(TPOS, FACING):
                    return
                ct.build_sentinel(TPOS, FACING)
            except Exception as exc:
                self.err.append("B:%s" % str(exc)[:30])
                return
            self.step = 3
            return
        if self.step == 3:
            if ct.can_move(Direction.NORTH):
                ct.move(Direction.NORTH)
            self.step = 4
            return

    def _healer(self, ct):
        r = ct.get_current_round()
        pos = ct.get_position()
        if pos != HPOS:
            if pos.x > HPOS.x and ct.can_move(Direction.WEST):
                ct.move(Direction.WEST)
            return
        if not HEAL or r < HEAL_FROM:
            return
        try:
            if ct.can_heal(TPOS):
                ct.heal(TPOS)
        except Exception as exc:
            if len(self.err) < 6:
                self.err.append("H:%s" % str(exc)[:30])

    def _turret(self, ct):
        try:
            b = ct.get_tile_building_id(ETPOS)
            if b is not None and ct.can_fire(ETPOS):
                ct.fire(ETPOS)
                self.shots += 1
        except Exception as exc:
            if len(self.err) < 6:
                self.err.append("F:%s" % str(exc)[:30])
