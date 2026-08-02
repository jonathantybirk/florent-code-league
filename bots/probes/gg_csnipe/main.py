"""Q7: can a GUNNER hit an enemy Core, and at what rate? The range-3 control for gg_ssnipe.

Same arena and same victim as `gg_ssnipe` so the two ledgers are directly comparable:
`maps/lab/ggopen.map26`, Core B footprint {(25,7),(26,7),(25,8),(26,8)}. Here the turret is a
Gunner at (22,7) facing EAST -- ray (23,7),(24,7),(25,7), so the Core footprint tile sits on the
third and last tile of its reach.

Supersedes `coresnipe`, whose arena `close` no longer exists.

The Gunner reports (M07), reading the victim Core's HP directly (it is at d^2=9, inside the
Gunner's r^2=13 vision), and stops at HP<=60 so the game does not end before the report lands.

Run:  python tools/runprobe.py gg_csnipe --map lab/ggopen
"""

from fcode import Controller, Direction, EntityType, Position

GUN = Position(22, 7)
STAND = Position(22, 6)
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
            if not self.fed and r >= 5 and ct.can_convert_ammo(120):
                ct.convert_ammo(120)
                self.fed = True
            return
        if et == EntityType.BUILDER_BOT:
            pos = ct.get_position()
            if self.built:
                return
            if pos == STAND:
                if ct.get_tile_building_id(GUN) is not None:
                    self.built = True
                elif ct.can_build_gunner(GUN, E):
                    ct.build_gunner(GUN, E)
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
        if et == EntityType.GUNNER:
            self._gun(ct, r)

    def _gun(self, ct, r):
        if self.done:
            return
        cid = ct.get_tile_building_id(TGT)
        if cid is None:
            self.done = True
            ct.resign("r%d NOCORE" % r)
            return
        hp = ct.get_hp(cid)
        if self.hp0 is None:
            self.hp0 = hp
            t = ct.get_gunner_target()
            self.n.append("r%d coreHP=%d team=%s cf=%s tgt=%s d2=%d" % (
                r, hp, "mine" if ct.get_team(cid) == ct.get_team() else "enemy",
                "1" if ct.can_fire(TGT) else "0",
                "-" if t is None else "%d,%d" % (t.x, t.y), GUN.distance_squared(TGT)))
        if hp > 60 and ct.can_fire(TGT):
            ct.fire(TGT)
            self.shots += 1
            if self.first < 0:
                self.first = r
            self.last = r
            return
        if hp <= 60 or r >= 400:
            self.done = True
            self.n.append("sh=%d r%d..%d dmgTot=%d hp=%d am=%d perShot=%d ti=%d" % (
                self.shots, self.first, self.last, self.hp0 - hp, hp,
                ct.get_global_ammo(),
                0 if self.shots == 0 else (self.hp0 - hp) // self.shots,
                ct.get_global_resources()))
            ct.resign(" | ".join(self.n)[:495])
