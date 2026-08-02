"""AREA-2 probe: CORE_ACTION_RADIUS_SQ = 8 -- what can the Core actually DO at range 2?
Plus the spawn-ring denial mechanism, asked of our own Core so the answer is unambiguous.

Arena openfield, Core A anchor (1,9), footprint (1,9)(2,9)(1,10)(2,10).
Builder spawns on ring tile (3,9); it builds a barrier on ring tile (3,8) and shoots it once so
the barrier is damaged (heal becomes a legal question).

  A1  can_spawn on a ring tile carrying OUR barrier        -> spawn denial by building
  A2  can_spawn on a ring tile carrying OUR builder bot    -> spawn denial by body
  A3  can_spawn on an empty ring tile                      -> control
  A4  Core: can_heal / can_destroy / can_build_barrier / can_fire / get_attackable_tiles
"""

from fcode import Controller, Direction, EntityType, GameError, Position


def e(exc):
    return type(exc).__name__ + ":" + str(exc)[:16]


def q(fn, *a):
    try:
        return str(fn(*a))
    except Exception as exc:
        return e(exc)


class Player:
    def __init__(self):
        self.n = []
        self.spawned = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.n.append("TOP:" + e(exc))

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()

        if et == EntityType.BUILDER_BOT:
            if r == 1:
                if ct.can_build_barrier(Position(3, 8)):
                    ct.build_barrier(Position(3, 8))
            elif r == 2:
                if ct.can_fire(Position(3, 8)):
                    ct.fire(Position(3, 8))
            return

        if et != EntityType.CORE:
            return

        if r == 0:
            self.n.append("A3 pre spawn38=%s spawn39=%s" % (
                q(ct.can_spawn, Position(3, 8)), q(ct.can_spawn, Position(3, 9))))
            if ct.can_spawn(Position(3, 9)):
                ct.spawn_builder(Position(3, 9))
                self.spawned = True
            return

        if r == 4:
            b = Position(3, 8)
            self.n.append("A1 bar38 spawn=%s A2 bot39 spawn=%s A3 empty310=%s" % (
                q(ct.can_spawn, b), q(ct.can_spawn, Position(3, 9)),
                q(ct.can_spawn, Position(3, 10))))
            self.n.append("A4 heal=%s des=%s bar=%s" % (
                q(ct.can_heal, b), q(ct.can_destroy, b),
                q(ct.can_build_barrier, Position(3, 10))))
            self.n.append("A4 fire=%s atk=%s cd=%s" % (
                q(ct.can_fire, b), q(ct.get_attackable_tiles), q(ct.get_action_cooldown)))
            return

        if r == 5:
            b = Position(3, 8)
            hp0 = q(ct.get_hp, ct.get_tile_building_id(b))
            try:
                ct.heal(b)
                self.n.append("A4 CORE HEALED %s->%s" % (
                    hp0, q(ct.get_hp, ct.get_tile_building_id(b))))
            except Exception as exc:
                self.n.append("A4 heal " + e(exc))
            try:
                ct.destroy(b)
                self.n.append("A4 CORE DESTROYED")
            except Exception as exc:
                self.n.append("A4 des " + e(exc))
            ct.resign(" | ".join(self.n)[:495])
            return
