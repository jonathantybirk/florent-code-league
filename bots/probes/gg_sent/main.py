"""Q6 (game-objects item 17): the Sentinel standoff. Can a Sentinel kill a Gunner that cannot
reach back, and what does the kill actually cost?

Arena `maps/lab/ggopen.map26`. One builder puts OUR Sentinel at (10,7) facing EAST and OUR Gunner
at (15,7) facing WEST -- 5 tiles apart, inside the Sentinel's 5-tile cardinal reach and outside
the Gunner's 3-tile reach. Turret APIs are team-blind (G10) so a friendly duel measures exactly
what an enemy duel would. The Gunner branch of this Player never fires, so the standoff is clean.

The Sentinel reports (M07). It records the geometry both ways with can_fire_from (ammo-independent),
then, once the Core has converted ammo, fires every round it legally can and logs each shot's round,
the target's remaining HP and the ammo pool.

Run:  python tools/runprobe.py gg_sent --map lab/ggopen
"""

from fcode import Controller, Direction, EntityType, Position

SENT = Position(10, 7)
GUNP = Position(15, 7)
E = Direction.EAST
W = Direction.WEST
G = EntityType.GUNNER
S = EntityType.SENTINEL
SPAWN = Position(3, 6)

SCRIPT = [
    (Position(10, 6), ("sent", SENT)),
    (Position(15, 6), ("gun", GUNP)),
    (Position(15, 4), None),
]


class Player:
    def __init__(self):
        self.n = []
        self.spawned = False
        self.s = 0
        self.shots = 0
        self.geo = False
        self.done = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.n.append("T:" + type(exc).__name__ + ":" + str(exc)[:18])

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()
        if et == EntityType.CORE:
            if not self.spawned and ct.can_spawn(SPAWN):
                ct.spawn_builder(SPAWN)
                self.spawned = True
                return
            if r == 40 and ct.can_convert_ammo(60):
                ct.convert_ammo(60)
            return
        if et == EntityType.BUILDER_BOT:
            self._builder(ct)
            return
        if et == EntityType.SENTINEL:
            self._sent(ct, r)

    def goto(self, ct, tgt):
        pos = ct.get_position()
        if pos == tgt:
            return True
        best = None
        for d in (Direction.EAST, Direction.WEST, Direction.NORTH, Direction.SOUTH):
            nxt = pos.add(d)
            sc = nxt.distance_squared(tgt)
            if ct.can_move(d) and (best is None or sc < best[0]):
                best = (sc, d)
        if best is not None and best[0] < pos.distance_squared(tgt):
            ct.move(best[1])
        return False

    def _builder(self, ct):
        if self.s >= len(SCRIPT):
            return
        station, act = SCRIPT[self.s]
        if not self.goto(ct, station):
            return
        if act is None:
            self.s += 1
            return
        kind, p = act
        if ct.get_tile_building_id(p) is not None:
            self.s += 1
            return
        if kind == "sent" and ct.can_build_sentinel(p, E):
            ct.build_sentinel(p, E)
            self.s += 1
        elif kind == "gun" and ct.can_build_gunner(p, W):
            ct.build_gunner(p, W)
            self.s += 1

    def _sent(self, ct, r):
        if self.done:
            return
        if r == 35 and not self.geo:
            self.geo = True
            self.n.append("d5 SgunG=%s GsunS=%s Gmax3=%s Gmax4=%s Smax5=%s Smax6=%s cd=%d" % (
                "1" if ct.can_fire_from(SENT, E, S, GUNP) else "0",
                "1" if ct.can_fire_from(GUNP, W, G, SENT) else "0",
                "1" if ct.can_fire_from(GUNP, W, G, Position(12, 7)) else "0",
                "1" if ct.can_fire_from(GUNP, W, G, Position(11, 7)) else "0",
                "1" if ct.can_fire_from(SENT, E, S, Position(15, 7)) else "0",
                "1" if ct.can_fire_from(SENT, E, S, Position(16, 7)) else "0",
                ct.get_action_cooldown()))
        if r > 40:
            bid = ct.get_tile_building_id(GUNP)
            if bid is not None and ct.can_fire(GUNP):
                ct.fire(GUNP)
                self.shots += 1
                nb = ct.get_tile_building_id(GUNP)
                self.n.append("s%d r%d hp%s am%d" % (
                    self.shots, r, "0" if nb is None else str(ct.get_hp(nb)),
                    ct.get_global_ammo()))
        if r == 70:
            self.done = True
            bid = ct.get_tile_building_id(GUNP)
            self.n.append("FIN gone=%s sh=%d am=%d ti=%d" % (
                "1" if bid is None else "0", self.shots,
                ct.get_global_ammo(), ct.get_global_resources()))
            ct.resign(" | ".join(self.n)[:495])
