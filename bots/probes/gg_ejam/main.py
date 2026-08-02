"""Q1/Q2 end-to-end: jam a REAL ENEMY Gunner with 3 Ti barriers and meter the exchange rate.

Opponent must be `ggturret`, which builds a live Gunner at (15,7) facing WEST on
`maps/lab/ggopen.map26` and fires at get_gunner_target() every round from a 300-ammo pool.

Our single Builder Bot walks the y=6 lane -- which is NOT in the enemy ray -- parks at (14,6), and
keeps a barrier alive on (14,7), the nearest tile of the enemy Gunner's three-tile ray. Every time
the Gunner grinds the barrier down, the builder rebuilds it next round. The probe counts barriers
placed, titanium spent on them (read from get_barrier_cost at the moment of each build), and the
number of rounds in which the lane behind the jammer was blocked.

Because the ammo pool is not readable across teams, the enemy's spend is derived: GUNNER_AMMO_COST
is 2 and GUNNER_DAMAGE is 10, so each 30 HP barrier absorbs exactly 3 shots = 6 ammo titanium.

Run:  python tools/runprobe.py gg_ejam --map lab/ggopen --vs ggturret
"""

from fcode import Controller, Direction, EntityType, Position

JAM = Position(14, 7)
STAND = Position(14, 6)
EGUN = Position(15, 7)
SPAWN = Position(3, 6)
END = 300


class Player:
    def __init__(self):
        self.n = []
        self.spawned = False
        self.built = 0
        self.spent = 0
        self.blocked = 0
        self.gaps = 0
        self.minhp = 40
        self.done = False
        self.seen = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.n.append("T:" + type(exc).__name__ + ":" + str(exc)[:16])

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()
        if et == EntityType.CORE:
            if not self.spawned and ct.can_spawn(SPAWN):
                ct.spawn_builder(SPAWN)
                self.spawned = True
            return
        if et != EntityType.BUILDER_BOT or self.done:
            return
        pos = ct.get_position()
        if pos != STAND:
            best = None
            for d in (Direction.EAST, Direction.NORTH, Direction.SOUTH, Direction.WEST):
                nxt = pos.add(d)
                sc = nxt.distance_squared(STAND)
                if ct.can_move(d) and (best is None or sc < best[0]):
                    best = (sc, d)
            if best is not None and best[0] < pos.distance_squared(STAND):
                ct.move(best[1])
            return

        if not self.seen:
            self.seen = True
            gid = ct.get_tile_building_id(EGUN)
            # The ship rule needs the ENEMY turret's facing to know which tile to brick.
            face = "-"
            ehp = "-"
            ety = "-"
            if gid is not None:
                face = ct.get_direction(gid).value[:4]
                ehp = str(ct.get_hp(gid))
                ety = ct.get_entity_type(gid).value[:3]
            self.n.append("arr r%d egun=%s team=%s dir=%s ty=%s hp=%s" % (
                r, "1" if gid is not None else "0",
                "-" if gid is None else ("mine" if ct.get_team(gid) == ct.get_team() else "enemy"),
                face, ety, ehp))

        bid = ct.get_tile_building_id(JAM)
        if bid is None:
            self.gaps += 1
            if ct.can_build_barrier(JAM):
                self.spent += ct.get_barrier_cost()
                ct.build_barrier(JAM)
                self.built += 1
        else:
            self.blocked += 1
        self.minhp = min(self.minhp, ct.get_hp())

        if r == END:
            self.done = True
            gid = ct.get_tile_building_id(EGUN)
            self.n.append("r%d built=%d spentTi=%d blocked=%d gaps=%d myhp=%d egun=%s ti=%d" % (
                r, self.built, self.spent, self.blocked, self.gaps, self.minhp,
                "1" if gid is not None else "0", ct.get_global_resources()))
            self.n.append("enemyAmmoTi=%d scale=%d barCost=%d" % (
                self.built * 6, int(ct.get_scale_percent()), ct.get_barrier_cost()))
            ct.resign(" | ".join(self.n)[:495])
