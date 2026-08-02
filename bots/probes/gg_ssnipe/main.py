"""Q6/Q7: can a SENTINEL hit an enemy Core from five tiles out, and what does the damage cost?

This is the one job a Gunner cannot do: r^2=32 puts a Sentinel's fifth ray tile on the enemy Core
footprint from a standoff of 5, two tiles further back than a Gunner's 3.

Arena `maps/lab/ggopen.map26`. Core B's footprint is {(25,7),(26,7),(25,8),(26,8)}. Our builder
plants a Sentinel at (20,7) facing EAST; its ray is (21,7)..(25,7), so the fifth tile is a Core
footprint tile. The Core converts 300 titanium to ammo (Sentinel costs 10 per shot).

The Sentinel reports (M07). Because the enemy Core sits at d^2=25, inside the Sentinel's own
r^2=32 vision, the probe can read the victim's HP directly every round. It stops firing once the
Core is under 60 HP and resigns with the ledger, so the game never ends before the report lands.

Run:  python tools/runprobe.py gg_ssnipe --map lab/ggopen
"""

from fcode import Controller, Direction, EntityType, Position

SENT = Position(20, 7)
STAND = Position(20, 6)
TGT = Position(25, 7)
SPAWN = Position(3, 6)
E = Direction.EAST


class Player:
    def __init__(self):
        self.n = []
        self.spawned = False
        self.fed = False
        self.built = False
        self.shots = 0
        self.first = -1
        self.last = -1
        self.hp0 = None
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
            if not self.fed and r >= 5 and ct.can_convert_ammo(300):
                ct.convert_ammo(300)
                self.fed = True
            return
        if et == EntityType.BUILDER_BOT:
            pos = ct.get_position()
            if self.built:
                return
            if pos == STAND:
                if ct.get_tile_building_id(SENT) is not None:
                    self.built = True
                elif ct.can_build_sentinel(SENT, E):
                    ct.build_sentinel(SENT, E)
                    self.built = True
                return
            best = None
            for d in (Direction.EAST, Direction.NORTH, Direction.SOUTH, Direction.WEST):
                nxt = pos.add(d)
                sc = nxt.distance_squared(STAND)
                if ct.can_move(d) and (best is None or sc < best[0]):
                    best = (sc, d)
            if best is not None and best[0] < pos.distance_squared(STAND):
                ct.move(best[1])
            return
        if et == EntityType.SENTINEL:
            self._sent(ct, r)

    def _sent(self, ct, r):
        if self.done:
            return
        cid = ct.get_tile_building_id(TGT)
        if cid is None:
            self.n.append("r%d NOCORE" % r)
            self.done = True
            ct.resign(" | ".join(self.n)[:495])
            return
        hp = ct.get_hp(cid)
        if self.hp0 is None:
            self.hp0 = hp
            self.n.append("r%d coreHP=%d team=%s cf=%s d2=%d" % (
                r, hp, "mine" if ct.get_team(cid) == ct.get_team() else "enemy",
                "1" if ct.can_fire(TGT) else "0", SENT.distance_squared(TGT)))
        if hp > 60 and ct.can_fire(TGT):
            ct.fire(TGT)
            self.shots += 1
            if self.first < 0:
                self.first = r
            self.last = r
            return
        if hp <= 60 or r >= 400:
            self.done = True
            self.n.append("sh=%d r%d..%d dmgTot=%d hp=%d am=%d perShot=%d" % (
                self.shots, self.first, self.last, self.hp0 - hp, hp,
                ct.get_global_ammo(),
                0 if self.shots == 0 else (self.hp0 - hp) // self.shots))
            ct.resign(" | ".join(self.n)[:495])
