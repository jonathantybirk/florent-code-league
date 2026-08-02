"""AREA-2: is destroy() / heal() TEAM-BLIND the way every turret API is (G10)?

If a Builder Bot can `destroy()` an orthogonally adjacent ENEMY building, that deletes a
20-HP conveyor or a 30-HP harvester instantly, for zero titanium and zero cooldown -- versus
10 attacks at 2 Ti each.  That would be the cheapest denial primitive in the game.

Arena `close`, opponent `a2vic` (enemy conveyor at (6,5), enemy barrier at (7,4)).
Our builder spawns at (3,5) and walks to (5,5), which is orthogonally adjacent to (6,5).
"""

from fcode import Controller, Direction, EntityType, GameError, Position

T = Position(6, 5)


def e(exc):
    return type(exc).__name__[:4] + ":" + str(exc)[:22]


class Player:
    def __init__(self):
        self.n = []
        self.spawned = False
        self.phase = 0

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.n.append("TOP:" + e(exc))

    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            if not self.spawned and ct.can_spawn(Position(3, 5)):
                ct.spawn_builder(Position(3, 5))
                self.spawned = True
            return
        if et != EntityType.BUILDER_BOT:
            return

        pos = ct.get_position()
        if pos.x < 5:
            if ct.can_move(Direction.EAST):
                ct.move(Direction.EAST)
            return

        def t(label, fn):
            try:
                self.n.append("%s=%s" % (label, str(fn())[:16]))
            except Exception as exc:
                self.n.append("%s!%s" % (label, e(exc)))

        if self.phase == 0:
            bid = None
            try:
                bid = ct.get_tile_building_id(T)
            except Exception:
                pass
            if bid is None:
                return
            self.n.append("tgt bid=%s" % bid)
            t("team", lambda: ct.get_team(bid))
            t("mine", lambda: ct.get_team())
            t("hp", lambda: ct.get_hp(bid))
            t("cdes", lambda: ct.can_destroy(T))
            t("chl", lambda: ct.can_heal(T))
            t("cfire", lambda: ct.can_fire(T))
            self.phase = 1
            return

        if self.phase == 1:
            t("DES", lambda: ct.destroy(T))
            t("after", lambda: ct.get_tile_building_id(T))
            t("ti", lambda: ct.get_global_resources())
            self.phase = 2
            return

        if self.phase == 2:
            t("HEAL", lambda: ct.heal(T))
            t("FIRE", lambda: ct.fire(T))
            t("hp2", lambda: ct.get_hp(ct.get_tile_building_id(T)))
            t("cd", lambda: ct.get_action_cooldown())
            ct.resign("|".join(self.n)[:495])
            self.phase = 3
            return
