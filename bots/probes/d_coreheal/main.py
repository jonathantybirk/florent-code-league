"""DEFENCE Q8 -- can menders out-heal a SENTINEL that is shooting the Core through the wall?

`d_sent2`/`d_wallshot` showed sentinels ignore barriers AND terrain walls, so no static obstacle
protects a Core from one.  The only remaining defence is repair: `d_bhit` showed a builder can
heal the Core (+4 HP for 1 Ti) and `d_heal` showed heals STACK within a round.  Sentinel output
is 18 damage every 3 rounds = 6 HP/round for 3.33 Ti/round, so two menders (+8 HP/round for
2 Ti/round) should hold -- and should do it at a LOWER burn rate than the attacker.

Arena `maps/lab/dopen.map26`, vs noop.  Core A anchor (2,5).  SENTINEL at (7,5) facing WEST,
line (6,5)(5,5)(4,5)(3,5)(2,5).  Menders sit on ring tiles (3,4) and (2,7) -- both orthogonally
adjacent to a Core footprint tile and both OUTSIDE the y=5 firing line.  Race runs r30..r150.
The CORE is the reporter (M07); menders relay heal counts through store slots 0 and 1.
"""

from fcode import Controller, Direction, EntityType, Position

DIRS = {(0, -1): Direction.NORTH, (1, 0): Direction.EAST,
        (0, 1): Direction.SOUTH, (-1, 0): Direction.WEST}
SENT = Position(7, 5)
TARGET = Position(3, 5)
SPAWNS = (Position(4, 7), Position(3, 4), Position(2, 7))
ROUTES = {(4, 7): [(5, 7), (6, 7), (7, 7), (7, 6)], (3, 4): [], (2, 7): []}
HEALTGT = {(3, 4): Position(3, 5), (2, 7): Position(2, 6)}
SLOTS = {(3, 4): 0, (2, 7): 1}
RACE0, RACE1, REPORT = 30, 150, 155


class Player:
    def __init__(self):
        self.spawned = 0
        self.home = None
        self.route = None
        self.leg = 0
        self.built = False
        self.heals = 0
        self.hp = None
        self.hpmin = 500
        self.hits = 0
        self.tot = 0
        self.ti0 = 0
        self.conv = 0

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception:
            return

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()

        if et == EntityType.CORE:
            hp = ct.get_hp()
            if self.hp is None:
                self.hp = hp
            elif hp != self.hp:
                if hp < self.hp:
                    self.hits += 1
                    self.tot += self.hp - hp
                self.hp = hp
            if hp < self.hpmin:
                self.hpmin = hp
            if self.spawned < 3:
                p = SPAWNS[self.spawned]
                if ct.can_spawn(p):
                    ct.spawn_builder(p)
                    self.spawned += 1
                return
            if ct.get_global_ammo() < 40 and ct.can_convert_ammo(150):
                ct.convert_ammo(150)
                self.conv += 150
                return
            if r == RACE0:
                self.ti0 = ct.get_global_resources()
            if r == REPORT:
                ct.resign("DCOREHEAL rounds=%d hits=%d dmg=%d hp=%d/500 hpmin=%d "
                          "heals=%d/%d ti r30=%d r155=%d conv=%d"
                          % (RACE1 - RACE0 + 1, self.hits, self.tot, self.hp,
                             self.hpmin, ct.read_store(0), ct.read_store(1),
                             self.ti0, ct.get_global_resources(), self.conv))
            return

        if et == EntityType.BUILDER_BOT:
            p = ct.get_position()
            if self.home is None:
                key = (p.x, p.y)
                if key not in ROUTES:
                    return
                self.home = key
                self.route = ROUTES[key]
            if self.leg < len(self.route):
                if (p.x, p.y) == self.route[self.leg]:
                    self.leg += 1
                if self.leg < len(self.route):
                    t = self.route[self.leg]
                    d = DIRS.get((t[0] - p.x, t[1] - p.y))
                    if d is not None and ct.can_move(d):
                        ct.move(d)
                    return
            if self.home == (4, 7):
                if not self.built and ct.can_build_sentinel(SENT, Direction.WEST):
                    ct.build_sentinel(SENT, Direction.WEST)
                    self.built = True
                return
            tgt = HEALTGT[self.home]
            if RACE0 <= r <= RACE1 and ct.can_heal(tgt):
                ct.heal(tgt)
                self.heals += 1
            ct.write_store(SLOTS[self.home], self.heals)
            return

        if et != EntityType.SENTINEL:
            return
        if RACE0 <= r <= RACE1 and ct.can_fire(TARGET):
            ct.fire(TARGET)
