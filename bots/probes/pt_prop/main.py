"""Team-B prop builder for the passability sweep. Partner bot for `pt_foe`.

    rm -rf bots/probes/pt_prop/__pycache__ bots/probes/pt_foe/__pycache__
    .venv/Scripts/python.exe tools/runprobe.py pt_foe --map passlab --vs pt_prop

This bot builds nothing for itself and never converts ammo (so its turrets cannot fire).
Its only job is to put one enemy-owned object at a time on the tile that pt_foe is measuring.
The two bots share no state; they synchronise purely on get_current_round(), so the schedule
constants below MUST stay identical to the copy in pt_foe/main.py.

  B1 parks at (12,9) and builds each prop on (11,9), one per 14-round block, destroying it
     8 rounds in.
  B2 parks at (11,10) out of the way, then steps onto (11,9) so pt_foe can measure a tile
     occupied by an ENEMY builder bot.
  Later B1 walks to (12,7) and builds a harvester on the ore at (11,7).
"""

import os

from fcode import Controller, Direction, EntityType, Position

OUT = os.environ.get("PT_PROP_OUT") or (
    "C:/Users/edlun/AppData/Local/Temp/claude/"
    "c--Users-edlun-Desktop-lucky-shots-Hackathons-florent-code-league/"
    "69495691-95ef-4878-adf9-aeca64f3e3b5/scratchpad/pt_prop.txt"
)

# ---- schedule, must match pt_foe ----
BLOCK0 = 40
BLOCK_LEN = 14
FOEBOT_MOVE = 145
HARV_WALK = 160
HARV_BUILD = 180
CORE_MEASURE = 240

PROP = Position(11, 9)
B1_STANCE = Position(12, 9)
B2_PARK = Position(11, 10)
HARV_ORE = Position(11, 7)
B1_HARV_STANCE = Position(12, 7)

SPAWN_B1 = Position(18, 7)
SPAWN_B2 = Position(19, 7)

PROP_SPECS = (
    ("CONVEYOR", "conveyor", True),
    ("SPLITTER", "splitter", True),
    ("HARVESTER_SKIP", None, False),   # placeholder: harvester needs ore, done later
    ("BARRIER", "barrier", False),
    ("GUNNER", "gunner", True),
    ("SENTINEL", "sentinel", True),
    ("LAUNCHER", "launcher", False),
)

CARDINALS = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)


class Player:
    def __init__(self):
        self.role = None
        self.gen = None
        self.ct = None
        self.log = []
        self.spawned = 0
        self.dead = False

    def run(self, ct: Controller) -> None:
        self.ct = ct
        try:
            et = ct.get_entity_type()
        except Exception:
            return
        if et == EntityType.CORE:
            if self.spawned < 2:
                want = SPAWN_B1 if self.spawned == 0 else SPAWN_B2
                try:
                    if ct.can_spawn(want):
                        ct.spawn_builder(want)
                        self.spawned += 1
                except Exception:
                    pass
            return
        if et != EntityType.BUILDER_BOT or self.dead:
            return
        if self.role is None:
            self.role = "B1" if ct.get_position() == SPAWN_B1 else "B2"
        if self.gen is None:
            self.gen = self._b1() if self.role == "B1" else self._b2()
        try:
            next(self.gen)
        except StopIteration:
            self.dead = True
        except Exception as exc:
            self._note("FATAL %s %s: %s" % (self.role, type(exc).__name__, str(exc)[:150]))
            self.dead = True

    # ---- plumbing ----

    def _note(self, line):
        self.log.append(line)
        try:
            with open(OUT, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except Exception:
            pass

    def _try(self, fn, *args):
        try:
            v = fn(*args)
            return "None" if v is None else str(getattr(v, "name", v))
        except Exception as exc:
            return "%s<%s>" % (type(exc).__name__, str(exc)[:70])

    def _wait_until(self, r):
        while self.ct.get_current_round() < r:
            yield

    def _walk(self, waypoints):
        for wx, wy in waypoints:
            tgt = Position(wx, wy)
            guard = 0
            while self.ct.get_position() != tgt:
                guard += 1
                if guard > 90:
                    self._note("%s WALK_STUCK at %s -> %s"
                               % (self.role, self.ct.get_position(), tgt))
                    return
                ct = self.ct
                if ct.get_move_cooldown() == 0:
                    pos = ct.get_position()
                    d = pos.cardinal_direction_to(tgt)
                    if ct.can_move(d):
                        ct.move(d)
                    else:
                        for alt in CARDINALS:
                            if alt is not d and ct.can_move(alt) and \
                                    pos.add(alt).distance_squared(tgt) < pos.distance_squared(tgt):
                                ct.move(alt)
                                break
                yield

    # ---- B1: the prop builder ----

    def _b1(self):
        self._note("B1 start round %d at %s" % (self.ct.get_current_round(), self.ct.get_position()))
        yield from self._walk([(18, 9), (B1_STANCE.x, B1_STANCE.y)])
        self._note("B1 at stance %s round %d" % (self.ct.get_position(), self.ct.get_current_round()))

        for k, (label, kind, needs_dir) in enumerate(PROP_SPECS):
            r = BLOCK0 + BLOCK_LEN * k
            yield from self._wait_until(r)
            if kind is None:
                continue
            while not self.ct.can_act():
                yield
            ct = self.ct
            args = (PROP, Direction.NORTH) if needs_dir else (PROP,)
            res = self._try(getattr(ct, "build_" + kind), *args)
            self._note("B1 r%d build %s at %s -> %s" % (ct.get_current_round(), label, PROP, res))
            yield from self._wait_until(r + 9)
            ct = self.ct
            self._note("B1 r%d destroy %s -> %s"
                       % (ct.get_current_round(), label, self._try(ct.destroy, PROP)))
            yield

        # ---- enemy harvester on the ore at (11,7) ----
        yield from self._wait_until(HARV_WALK)
        yield from self._walk([(12, 8), (B1_HARV_STANCE.x, B1_HARV_STANCE.y)])
        yield from self._wait_until(HARV_BUILD)
        while not self.ct.can_act():
            yield
        ct = self.ct
        self._note("B1 r%d build HARVESTER at %s -> %s"
                   % (ct.get_current_round(), HARV_ORE, self._try(ct.build_harvester, HARV_ORE)))
        while True:
            yield

    # ---- B2: the enemy builder bot that gets stood next to ----

    def _b2(self):
        self._note("B2 start round %d at %s" % (self.ct.get_current_round(), self.ct.get_position()))
        yield from self._walk([(19, 10), (B2_PARK.x, B2_PARK.y)])
        self._note("B2 parked %s round %d" % (self.ct.get_position(), self.ct.get_current_round()))
        yield from self._wait_until(FOEBOT_MOVE)
        yield from self._walk([(PROP.x, PROP.y)])
        self._note("B2 r%d now on %s" % (self.ct.get_current_round(), self.ct.get_position()))
        while True:
            yield
