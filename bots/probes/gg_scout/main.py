"""AREA 1 / GobbleGlitch probe: WHERE do real rivals actually stand near our Core?

A defensive Launcher only intercepts what walks into its 8-tile pickup ring
(measured r^2<=2, gl_pickup2).  Before building a defensive-launcher doctrine we
must know whether real opponents ever put a Builder Bot inside such a ring.

This probe is a pure observer: the Core spawns one Builder Bot (so the match is
not a walkover from unit starvation) and then, every round, the CORE logs every
ENEMY unit and every ENEMY building inside its own vision (r^2=36, 6 tiles).

Offline we then compute, for every candidate Launcher tile near our Core, how
many enemy-builder-rounds fell inside its pickup ring.  That is the interception
opportunity, measured against opponents nobody tuned against.

Exfil: 'LP|' lines out of the .replay26.
"""

from fcode import Controller, Direction, EntityType, GameError, Position


def en(exc):
    return type(exc).__name__ + ":" + str(exc)[:24]


class Player:
    def __init__(self):
        self.spawned = 0
        self.said = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            print("LP|TOP %s" % en(exc))

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()
        if et != EntityType.CORE:
            return
        if not self.said:
            p = ct.get_position()
            print("LP|MAP w=%d h=%d core=%d,%d" % (
                ct.get_map_width(), ct.get_map_height(), p.x, p.y))
            self.said = True
        me = ct.get_team()
        parts = []
        for uid in ct.get_nearby_units():
            if ct.get_team(uid) == me:
                continue
            q = ct.get_position(uid)
            parts.append("u%d:%d,%d" % (uid, q.x, q.y))
        for bidx in ct.get_nearby_buildings():
            if ct.get_team(bidx) == me:
                continue
            q = ct.get_position(bidx)
            parts.append("b%d:%d,%d:%s" % (
                bidx, q.x, q.y, str(ct.get_entity_type(bidx))[11:15]))
        if parts:
            print("LP|E r%d %s" % (r, " ".join(parts)))
        if self.spawned < 2 and ct.get_current_round() < 40:
            for dx in (-1, 0, 1, 2):
                for dy in (-1, 0, 1, 2):
                    q = Position(ct.get_position().x + dx, ct.get_position().y + dy)
                    if q.x < 0 or q.y < 0:
                        continue
                    if ct.can_spawn(q):
                        ct.spawn_builder(q)
                        self.spawned += 1
                        return
