"""Q8: how dangerous is the team-blind fire path in practice, and what guard removes the risk?

Every turret API ignores team (G10), so a naive `t = get_gunner_target(); fire(t)` policy will shoot
our own units. This probe measures the WORST case on purpose: a forward Gunner facing the enemy,
with a stream of our own Builder Bots marching down the same axis and crossing its ray.

Roles are assigned by the round a Builder Bot first sees itself (module globals are not shared,
G20): the first builder walks four tiles toward the enemy, plants the Gunner facing that way, and
then keeps marching straight through its own firing line. The five later builders march the same
lane. The Core tops up the global ammo pool so the Gunner really fires.

The Gunner reports (M07). Every round it classifies get_gunner_target() with get_team() -- the guard
that is available and costs one comparison -- and then fires NAIVELY anyway, so both numbers come
out of one run: `fr` = acquisitions/shots on our own team, `en` = on the enemy.

The last builder is a deliberate HAZARD: it scans its vision for a friendly Gunner, reads its facing
with get_direction(), and parks itself two tiles down that Gunner's ray. That turns the abstract
"turrets are team-blind" into a measured kill.

Run:  python tools/runprobe.py gg_self --map sprint --vs luc1
"""

from fcode import Controller, Direction, EntityType, Position

CARD = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)
END = 400


class Player:
    def __init__(self):
        self.spawned = 0
        self.birth = None
        self.home = None
        self.aim = None
        self.gbuilt = False
        self.steps = 0
        self.fr_acq = 0
        self.en_acq = 0
        self.no_acq = 0
        self.fr_shot = 0
        self.en_shot = 0
        self.fr_dmg = 0
        self.en_dmg = 0
        self.done = False
        self.note = ""

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.note = type(exc).__name__ + ":" + str(exc)[:20]

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()
        if et == EntityType.CORE:
            self._core(ct, r)
            return
        if et == EntityType.BUILDER_BOT:
            self._builder(ct, r)
            return
        if et == EntityType.GUNNER:
            self._gunner(ct, r)

    def _core(self, ct, r):
        if r % 6 == 0 and self.spawned < 6:
            p = ct.get_position()
            for dx in (-1, 0, 1, 2):
                for dy in (-1, 0, 1, 2):
                    q = Position(p.x + dx, p.y + dy)
                    if ct.can_spawn(q):
                        ct.spawn_builder(q)
                        self.spawned += 1
                        return
        if r % 10 == 0 and ct.can_convert_ammo(20):
            ct.convert_ammo(20)

    def _far(self, ct):
        # Mirror of the birth tile: on every map in the pool the enemy core sits opposite ours.
        return Position(ct.get_map_width() - 1 - self.home.x,
                        ct.get_map_height() - 1 - self.home.y)

    def _builder(self, ct, r):
        pos = ct.get_position()
        if self.birth is None:
            self.birth = r
            self.home = pos
            tgt = self._far(ct)
            dx = tgt.x - pos.x
            dy = tgt.y - pos.y
            if abs(dx) >= abs(dy):
                self.aim = Direction.EAST if dx > 0 else Direction.WEST
            else:
                self.aim = Direction.SOUTH if dy > 0 else Direction.NORTH
        if self.birth <= 3 and not self.gbuilt and self.steps >= 4:
            ahead = pos.add(self.aim)
            if ct.can_build_gunner(ahead, self.aim):
                ct.build_gunner(ahead, self.aim)
                self.gbuilt = True
                return
            self.gbuilt = True
            return
        if self.birth is not None and self.birth > 25:
            self._hazard(ct, pos)
            return
        tgt = self._far(ct)
        best = None
        for d in CARD:
            nxt = pos.add(d)
            sc = nxt.distance_squared(tgt)
            if ct.can_move(d) and (best is None or sc < best[0]):
                best = (sc, d)
        if best is not None and best[0] < pos.distance_squared(tgt):
            ct.move(best[1])
            self.steps += 1

    def _hazard(self, ct, pos):
        """Walk into the ray of the nearest friendly Gunner, two tiles out."""
        tgt = None
        for bid in ct.get_nearby_buildings():
            if ct.get_entity_type(bid) != EntityType.GUNNER:
                continue
            if ct.get_team(bid) != ct.get_team():
                continue
            gp = ct.get_position(bid)
            dx, dy = ct.get_direction(bid).delta()
            tgt = Position(gp.x + 2 * dx, gp.y + 2 * dy)
            break
        if tgt is None:
            tgt = self._far(ct)
        best = None
        for d in CARD:
            nxt = pos.add(d)
            sc = nxt.distance_squared(tgt)
            if ct.can_move(d) and (best is None or sc < best[0]):
                best = (sc, d)
        if best is not None and best[0] < pos.distance_squared(tgt):
            ct.move(best[1])

    def _gunner(self, ct, r):
        if self.done:
            return
        t = ct.get_gunner_target()
        if t is None:
            self.no_acq += 1
        else:
            eid = ct.get_tile_builder_bot_id(t)
            if eid is None:
                eid = ct.get_tile_building_id(t)
            mine = eid is not None and ct.get_team(eid) == ct.get_team()
            if mine:
                self.fr_acq += 1
            else:
                self.en_acq += 1
            if ct.can_fire(t):
                hp0 = 0 if eid is None else ct.get_hp(eid)
                ct.fire(t)
                nid = ct.get_tile_builder_bot_id(t)
                if nid is None:
                    nid = ct.get_tile_building_id(t)
                hp1 = 0 if nid is None else ct.get_hp(nid)
                d = max(0, hp0 - hp1)
                if mine:
                    self.fr_shot += 1
                    self.fr_dmg += d
                else:
                    self.en_shot += 1
                    self.en_dmg += d
        if r >= END:
            self.done = True
            tot = self.fr_acq + self.en_acq
            ct.resign(("SELF acq=%d fr=%d en=%d none=%d | shots fr=%d en=%d | dmg fr=%d en=%d"
                       " | frRate=%d%% ammo=%d | %s") % (
                tot, self.fr_acq, self.en_acq, self.no_acq, self.fr_shot, self.en_shot,
                self.fr_dmg, self.en_dmg,
                0 if tot == 0 else (100 * self.fr_acq) // tot,
                ct.get_global_ammo(), self.note)[:495])
