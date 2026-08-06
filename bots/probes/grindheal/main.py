"""TASK 1.1 -- can N friendly Builder Bots out-heal M enemy Builder Bots chewing a
forward turret?

Run this bot as BOTH sides on `maps/lab/hg<W>x<H>.map26` (built by maps/lab/mkgrind.py).
The map dimensions carry the configuration -- a probe cannot be given arguments:

    N = (H - 10) // 4      healers   (team A, west Core)
    M = (H - 10) %  4      grinders  (team B, east Core)
    W = 24 Sentinel/no-ammo   25 Gunner/no-ammo   26 Sentinel/ammo   27 Gunner/ammo

The west side builds ONE turret at T=(12,3) facing EAST and parks N healers on its
orthogonal neighbours; the east side parks M grinders on the remaining neighbours and
attacks T from round 25.  Contact is capped at four bots total because a 1x1 turret has
exactly four orthogonal neighbours, so only N + M <= 4 cells exist.

Slot assignment (never collides while N + M <= 4):
    healers  take  W(11,3), S(12,4), N(12,2)   in that order
    grinders take  E(13,3), N(12,2), S(12,4)   in that order

Healers hold their fire until the turret has lost HEAL_TRIGGER_DROP HP (or round 60),
so a single game yields the pure grind slope first and the net slope afterwards.

The turret republishes its own HP into the team store every round; the west Core reads
it (one-round write lag), run-length-encodes the per-round delta, and resigns the whole
trajectory at REPORT_ROUND.  If the turret dies the heartbeat slot freezes and the Core
records the death round.
"""

from fcode import Controller, Direction, EntityType, GameConstants, Position

T = Position(12, 3)
SLOT_W = Position(11, 3)
SLOT_N = Position(12, 2)
SLOT_E = Position(13, 3)
SLOT_S = Position(12, 4)

ATTACK_START = 25
FORCE_HEAL_ROUND = 60
HEAL_TRIGGER_DROP = 12
REPORT_ROUND = 300

S_HP = 0        # turret hp + 1
S_BEAT = 1      # turret's current round + 1  (freezes when the turret dies)
S_ENGAGE = 2    # round the first heal landed, + 1
S_ATK = 3       # turret attackable tiles: count * 16 + neighbour bitmask
S_SHOTS = 4     # turret shots fired + 1
S_HEAL = 8      # + healer index: cumulative heals landed, + 1
S_FAIL = 12     # + healer index: cumulative rounds can_heal() was False, + 1

STEP = {
    (0, -1): Direction.NORTH,
    (0, 1): Direction.SOUTH,
    (1, 0): Direction.EAST,
    (-1, 0): Direction.WEST,
}


def config(ct):
    w = ct.get_map_width()
    h = ct.get_map_height()
    idx = h - 10
    return w, h, idx // 4, idx % 4


class Player:
    def __init__(self):
        self.role = None
        self.west = None
        self.path = None
        self.leg = 0
        self.built = False
        self.done = False
        self.heals = 0
        self.fails = 0
        self.hits = 0
        self.engaged = False
        self.hidx = 0
        self.published = False
        # Core-only bookkeeping
        self.spawned = set()
        self.trace = []
        self.beats = []
        self.ti = {}
        self.info = ""
        self.err = []

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            if len(self.err) < 5:
                self.err.append("%s:%s" % (type(exc).__name__, str(exc)[:48]))

    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            self._core(ct)
        elif et == EntityType.BUILDER_BOT:
            self._builder(ct)
        elif et in (EntityType.SENTINEL, EntityType.GUNNER):
            self._turret(ct)

    # ---------------------------------------------------------------- core ---
    def _core(self, ct):
        w, h, healers, grinders = config(ct)
        r = ct.get_current_round()
        if self.west is None:
            self.west = ct.get_position().x < w // 2
            if self.west:
                self.info = "cost_sent=%d cost_gun=%d cost_bot=%d scale=%.2f" % (
                    ct.get_sentinel_cost(),
                    ct.get_gunner_cost(),
                    ct.get_builder_bot_cost(),
                    ct.get_scale_percent(),
                )

        if self.west:
            plan = [(0, Position(3, 2))]
            for i, y in enumerate((3, 5, 4)):
                if i < healers:
                    plan.append((2 + 2 * i, Position(3, y)))
        else:
            plan = []
            for i, y in enumerate((3, 4, 5)):
                if i < grinders:
                    plan.append((2 * i, Position(3 if False else w - 4, y)))

        for i, (when, pos) in enumerate(plan):
            if i in self.spawned or r < when:
                continue
            if ct.can_spawn(pos):
                ct.spawn_builder(pos)
                self.spawned.add(i)
            break

        if self.west:
            if w >= 26 and ct.get_global_ammo() < 100 and ct.can_convert_ammo(40):
                ct.convert_ammo(40)
            self.trace.append(ct.read_store(S_HP) - 1)
            self.beats.append(ct.read_store(S_BEAT) - 1)
            if r in (20, 30, 50, 100, 150, 200, 250, REPORT_ROUND):
                self.ti[r] = ct.get_global_resources()
            if r >= REPORT_ROUND:
                ct.resign(self._report(ct, w, h, healers, grinders))

    def _report(self, ct, w, h, healers, grinders):
        kind = "SENT" if w in (24, 26) else "GUN"
        ammo = 1 if w >= 26 else 0
        hp = [v for v in self.trace]
        beat = self.beats
        alive_until = -1
        for i in range(1, len(beat)):
            if beat[i] > beat[i - 1]:
                alive_until = i
        born = -1
        for i, v in enumerate(hp):
            if v >= 0:
                born = i
                break
        if born < 0:
            return "CFG %s N=%d M=%d %dx%d ammo=%d | TURRET NEVER BUILT | %s | ERR=%s" % (
                kind, healers, grinders, w, h, ammo, self.info, ";".join(self.err))

        dead = -1
        if alive_until < len(beat) - 3:
            dead = alive_until
        seq = hp[born:alive_until + 1]
        # run-length encode the per-round delta
        parts = []
        run_v, run_n = None, 0
        for i in range(1, len(seq)):
            d = seq[i] - seq[i - 1]
            if d == run_v:
                run_n += 1
            else:
                if run_v is not None:
                    parts.append("%+d%s" % (run_v, "x%d" % run_n if run_n > 1 else ""))
                run_v, run_n = d, 1
        if run_v is not None:
            parts.append("%+d%s" % (run_v, "x%d" % run_n if run_n > 1 else ""))

        atk = ct.read_store(S_ATK)
        heals = sum(max(0, ct.read_store(S_HEAL + i) - 1) for i in range(3))
        fails = sum(max(0, ct.read_store(S_FAIL + i) - 1) for i in range(3))
        return (
            "CFG %s N=%d M=%d %dx%d ammo=%d | BORN=r%d HP0=%d END=%d MIN=%d DEAD=r%d "
            "| TRACE(r%d..)=%s | ENGAGE=r%d HEALS=%d NOTI=%d SHOTS=%d ATK=%d/%d "
            "| TIA=%s | %s | ERR=%s"
            % (
                kind, healers, grinders, w, h, ammo,
                born, seq[0], seq[-1], min(seq), dead,
                born, " ".join(parts) or "flat",
                ct.read_store(S_ENGAGE) - 1, heals, fails,
                max(0, ct.read_store(S_SHOTS) - 1), atk // 16, atk % 16,
                ",".join("r%d:%d" % (k, self.ti[k]) for k in sorted(self.ti)),
                self.info, ";".join(self.err),
            )
        )

    # ------------------------------------------------------------- builder ---
    def _builder(self, ct):
        w, h, healers, grinders = config(ct)
        p = ct.get_position()
        if self.role is None:
            self.west = p.x < w // 2
            if self.west:
                self.role = {2: "build", 3: "hW", 5: "hS", 4: "hN"}.get(p.y, "idle")
            else:
                self.role = {3: "gE", 4: "gN", 5: "gS"}.get(p.y, "idle")
            self.hidx = {"hW": 0, "hS": 1, "hN": 2}.get(self.role, 0)
            self.path = {
                "build": [Position(4, 2), Position(11, 2), SLOT_W],
                "hW": [Position(4, 3), SLOT_W],
                "hS": [Position(4, 5), Position(4, 6), Position(12, 6), SLOT_S],
                "hN": [Position(4, 4), Position(4, 0), Position(12, 0), SLOT_N],
                "gE": [Position(w - 5, 3), SLOT_E],
                "gN": [Position(w - 5, 4), Position(w - 5, 1),
                       Position(12, 1), SLOT_N],
                "gS": [Position(w - 5, 5), Position(w - 5, 7),
                       Position(12, 7), SLOT_S],
            }.get(self.role, [])

        if self.done:
            return

        if self.leg < len(self.path):
            goal = self.path[self.leg]
            if p == goal:
                self.leg += 1
                if self.leg < len(self.path):
                    goal = self.path[self.leg]
                else:
                    goal = None
            if goal is not None:
                dx = (goal.x > p.x) - (goal.x < p.x)
                dy = (goal.y > p.y) - (goal.y < p.y)
                d = STEP.get((dx, 0) if dx else (0, dy))
                if d is not None and ct.can_move(d):
                    ct.move(d)
                return

        if self.role == "build":
            kind = "SENT" if w in (24, 26) else "GUN"
            if not self.built:
                ok = (ct.can_build_sentinel(T, Direction.EAST) if kind == "SENT"
                      else ct.can_build_gunner(T, Direction.EAST))
                if ok:
                    if kind == "SENT":
                        ct.build_sentinel(T, Direction.EAST)
                    else:
                        ct.build_gunner(T, Direction.EAST)
                    self.built = True
                return
            self.done = True
            ct.self_destruct()
            return

        if self.role.startswith("h"):
            bid = ct.get_tile_building_id(T)
            if bid is None:
                return
            r = ct.get_current_round()
            if not self.engaged:
                hp = ct.get_hp(bid)
                if hp <= ct.get_max_hp(bid) - HEAL_TRIGGER_DROP or r >= FORCE_HEAL_ROUND:
                    self.engaged = True
                else:
                    return
            if ct.can_heal(T):
                ct.heal(T)
                self.heals += 1
                if not self.published:
                    self.published = True
                    ct.write_store(S_ENGAGE, r + 1)
            else:
                self.fails += 1
            ct.write_store(S_HEAL + self.hidx, self.heals + 1)
            ct.write_store(S_FAIL + self.hidx, self.fails + 1)
            return

        if self.role.startswith("g"):
            if ct.get_current_round() < ATTACK_START:
                return
            if ct.can_fire(T):
                ct.fire(T)
                self.hits += 1
            return

    # -------------------------------------------------------------- turret ---
    def _turret(self, ct):
        r = ct.get_current_round()
        ct.write_store(S_HP, ct.get_hp() + 1)
        ct.write_store(S_BEAT, r + 1)
        if not self.published:
            self.published = True
            tiles = set()
            for q in ct.get_attackable_tiles():
                tiles.add((q.x, q.y))
            mask = 0
            for bit, q in enumerate((SLOT_E, SLOT_N, SLOT_S, SLOT_W)):
                if (q.x, q.y) in tiles:
                    mask |= 1 << bit
            ct.write_store(S_ATK, len(tiles) * 16 + mask)
        w = ct.get_map_width()
        if w >= 26:
            for q in (SLOT_E, SLOT_N, SLOT_S, SLOT_W):
                if ct.can_fire(q):
                    ct.fire(q)
                    self.hits += 1
                    break
            ct.write_store(S_SHOTS, self.hits + 1)
