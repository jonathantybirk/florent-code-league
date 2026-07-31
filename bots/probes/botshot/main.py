"""Probe: can a Builder Bot's 2.3.3 adjacent attack hit an enemy BUILDER BOT, or only a building?

`fcode/_types.py` says of `can_fire`: "Builder bots may only target an orthogonally adjacent tile
(not diagonal, not their own tile), and only damage the building on it." If that last clause is
literal, then a tile holding an enemy bot and NO building is either an illegal target or a legal
one that deals zero damage -- and a bot-first target priority would be shooting at nothing, or
worse, shadowing the enemy Core behind it.

Walks one Builder Bot east/toward the enemy Core until an enemy Builder Bot is orthogonally
adjacent, then reports, for that tile:
    canfire, the target's HP before and after, and our titanium delta.
Opponent must be `bots/probes/sit2`, which parks exactly one bot and builds nothing.
"""

from fcode import Controller, Direction, EntityType, Position

CARDS = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)


def e(exc):
    return type(exc).__name__ + ":" + str(exc)[:28]


class Player:
    def __init__(self):
        self.n = []
        self.spawned = False
        self.done = False
        self.hp0 = None
        self.ti0 = None
        self.tgt = None

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.n.append("TOP:" + e(exc))

    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            if not self.spawned:
                pos = ct.get_position()
                w, h = ct.get_map_width(), ct.get_map_height()
                for dx in range(-1, 3):
                    for dy in range(-1, 3):
                        t = Position(pos.x + dx, pos.y + dy)
                        if not (0 <= t.x < w and 0 <= t.y < h):
                            continue
                        try:
                            if ct.can_spawn(t):
                                ct.spawn_builder(t)
                                self.spawned = True
                                return
                        except Exception:
                            continue
            return
        if et != EntityType.BUILDER_BOT or self.done:
            return

        pos = ct.get_position()

        # Phase 2: the shot has been taken; read the result and report.
        if self.tgt is not None:
            self.done = True
            hp1 = None
            try:
                bid = ct.get_tile_builder_bot_id(self.tgt)
                if bid is not None:
                    hp1 = ct.get_hp(bid)
            except Exception as exc:
                self.n.append("HPAFTER " + e(exc))
            self.n.append("after hp=%s dTi=%s" % (
                hp1, ct.get_global_resources() - self.ti0))
            ct.resign(" | ".join(self.n[:8]))
            return

        # Phase 1: look for an orthogonally adjacent enemy Builder Bot on a tile with no building.
        for d in CARDS:
            t = pos.add(d)
            try:
                bid = ct.get_tile_builder_bot_id(t)
            except Exception:
                continue
            if bid is None:
                continue
            try:
                if ct.get_team(bid) == ct.get_team():
                    continue
                bld = ct.get_tile_building_id(t)
            except Exception:
                continue
            self.n.append("found enemy bot at %d,%d building=%s" % (t.x, t.y, bld))
            try:
                self.hp0 = ct.get_hp(bid)
            except Exception as exc:
                self.n.append("HP0 " + e(exc))
            self.ti0 = ct.get_global_resources()
            try:
                self.n.append("canfire=%s hp0=%s" % (ct.can_fire(t), self.hp0))
            except Exception as exc:
                self.n.append("CANFIRE " + e(exc))
            try:
                ct.fire(t)
                self.n.append("FIRE ok")
            except Exception as exc:
                self.n.append("FIRE " + e(exc))
                self.done = True
                ct.resign(" | ".join(self.n[:8]))
                return
            self.tgt = t
            return

        # Otherwise walk east, then south/north as a crude detour.
        for d in (Direction.EAST, Direction.SOUTH, Direction.NORTH, Direction.WEST):
            try:
                if ct.can_move(d):
                    ct.move(d)
                    return
            except Exception:
                continue
