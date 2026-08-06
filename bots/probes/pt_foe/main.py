"""Definitive 2.3.6 passability table, part 2: ENEMY Core, buildings and builder bot.

Arena `maps/lab/passlab.map26`. Partner bot `pt_prop` supplies the enemy-owned props.

    rm -rf bots/probes/pt_foe/__pycache__ bots/probes/pt_prop/__pycache__
    .venv/Scripts/python.exe tools/runprobe.py pt_foe --map passlab --vs pt_prop

Same three independent measurements per tile as pt_own:
  1. is_tile_passable(tile)
  2. can_move(direction)     -- only on a round with get_move_cooldown()==0
  3. did move(direction) actually relocate the unit (position sampled before, immediately
     after the call, and again next round)
Every row also reports get_entity_type / get_team of whatever occupies the tile, so the row
label is proved rather than assumed.

Synchronisation with pt_prop is by round number only (no shared state exists between teams);
the schedule constants below MUST match the copy in pt_prop/main.py.
"""

import os

from fcode import Controller, Direction, EntityType, Position

OUT = os.environ.get("PT_FOE_OUT") or (
    "C:/Users/edlun/AppData/Local/Temp/claude/"
    "c--Users-edlun-Desktop-lucky-shots-Hackathons-florent-code-league/"
    "69495691-95ef-4878-adf9-aeca64f3e3b5/scratchpad/pt_foe.txt"
)

# ---- schedule, must match pt_prop ----
BLOCK0 = 40
BLOCK_LEN = 14
FOEBOT_MOVE = 145
FOEBOT_MEASURE = 152
HARV_WALK = 160
HARV_BUILD = 180
HARV_MEASURE = 186
CORE_WALK = 200
CORE_MEASURE = 245
END = 265

SPAWN_LEAD = Position(3, 7)
A_STANCE = Position(10, 9)
PROP = Position(11, 9)
A_HARV_STANCE = Position(10, 7)
HARV_ORE = Position(11, 7)
A_CORE_STANCE = Position(18, 5)
FOE_CORE_TILE = Position(19, 5)

FOE_SPECS = (
    ("FOE_CONVEYOR", True),
    ("FOE_SPLITTER", True),
    (None, False),                 # slot 2 is the harvester, measured later on ore
    ("FOE_BARRIER", True),
    ("FOE_GUNNER", True),
    ("FOE_SENTINEL", True),
    ("FOE_LAUNCHER", True),
)

CARDINALS = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)


def show(v):
    if v is None:
        return "None"
    if isinstance(v, bool):
        return "True" if v else "False"
    if isinstance(v, Position):
        return "(%d,%d)" % (v.x, v.y)
    if hasattr(v, "name"):
        return v.name
    return str(v)


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
            if self.spawned == 0:
                try:
                    if ct.can_spawn(SPAWN_LEAD):
                        ct.spawn_builder(SPAWN_LEAD)
                        self.spawned = 1
                except Exception:
                    pass
            return
        if et != EntityType.BUILDER_BOT or self.dead:
            return
        if self.gen is None:
            self.gen = self._script()
        try:
            next(self.gen)
        except StopIteration:
            self.dead = True
        except Exception as exc:
            self._note("FATAL %s: %s" % (type(exc).__name__, str(exc)[:200]))
            self.dead = True

    # ---- plumbing ----

    def _note(self, line):
        self.log.append(line)
        try:
            with open(OUT, "w", encoding="utf-8") as fh:
                fh.write("\n".join(self.log) + "\n")
        except Exception:
            pass

    def _try(self, fn, *args):
        try:
            return show(fn(*args))
        except Exception as exc:
            return "%s<%s>" % (type(exc).__name__, str(exc)[:90])

    def _occupant(self, ct, tile):
        """Prove what is on the tile: entity type + team, for building and builder alike."""
        bits = []
        for getter in ("get_tile_building_id", "get_tile_builder_bot_id"):
            try:
                eid = getattr(ct, getter)(tile)
            except Exception as exc:
                bits.append("%s=%s" % (getter[9:], type(exc).__name__))
                continue
            if eid is None:
                bits.append("%s=None" % getter[9:])
            else:
                bits.append("%s=%s/%s/%s" % (getter[9:], eid,
                                             self._try(ct.get_entity_type, eid),
                                             self._try(ct.get_team, eid)))
        return "  ".join(bits)

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
                    self._note("WALK_STUCK at %s -> %s r%d"
                               % (show(self.ct.get_position()), show(tgt),
                                  self.ct.get_current_round()))
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

    def _measure(self, label, tile, d):
        while self.ct.get_move_cooldown() != 0:
            yield
        ct = self.ct
        home = ct.get_position()
        parts = [
            "%-14s tile=%s from=%s dir=%-5s" % (label, show(tile), show(home), d.name),
            "is_tile_passable=%s" % self._try(ct.is_tile_passable, tile),
            "is_tile_empty=%s" % self._try(ct.is_tile_empty, tile),
            "env=%s" % self._try(ct.get_tile_env, tile),
            self._occupant(ct, tile),
            "move_cd=%d" % ct.get_move_cooldown(),
            "can_move=%s" % self._try(ct.can_move, d),
            "move()=%s" % self._try(ct.move, d),
            "pos_same_round=%s" % show(ct.get_position()),
        ]
        yield
        ct = self.ct
        landed = ct.get_position()
        parts.append("pos_next_round=%s" % show(landed))
        parts.append("RELOCATED=%s" % show(landed == tile))
        self._note("  ".join(parts))
        if landed != home:
            yield from self._walk([(home.x, home.y)])

    # ---- script ----

    def _script(self):
        ct = self.ct
        self._note("=== pt_foe : 2.3.6 passability, enemy side ===")
        self._note("round=%d my_id=%d team=%s" % (ct.get_current_round(), ct.get_id(),
                                                  show(ct.get_team())))

        # Cross-check of pt_own's surprising own-Core result, from a second stance.
        yield from self._walk([(3, 6)])
        yield from self._measure("OWN_CORE_2", Position(2, 6), Direction.WEST)

        yield from self._walk([(3, 10), (A_STANCE.x, 10), (A_STANCE.x, A_STANCE.y)])
        self._note("A at stance %s round %d" % (show(self.ct.get_position()),
                                                self.ct.get_current_round()))

        for k, (label, _unused) in enumerate(FOE_SPECS):
            r = BLOCK0 + BLOCK_LEN * k
            yield from self._wait_until(r + 3)
            if label is None:
                continue
            if self.ct.get_position() != A_STANCE:
                yield from self._walk([(A_STANCE.x, A_STANCE.y)])
            yield from self._measure(label, PROP, Direction.EAST)

        # ---- tile occupied by an ENEMY builder bot ----
        yield from self._wait_until(FOEBOT_MEASURE)
        if self.ct.get_position() != A_STANCE:
            yield from self._walk([(A_STANCE.x, A_STANCE.y)])
        yield from self._measure("FOE_BUILDERBOT", PROP, Direction.EAST)

        # ---- enemy harvester on ore ----
        yield from self._wait_until(HARV_WALK)
        yield from self._walk([(A_HARV_STANCE.x, A_HARV_STANCE.y)])
        yield from self._wait_until(HARV_MEASURE)
        yield from self._measure("FOE_HARVESTER", HARV_ORE, Direction.EAST)

        # ---- enemy core ----
        yield from self._wait_until(CORE_WALK)
        yield from self._walk([(10, 3), (18, 3), (18, 4), (A_CORE_STANCE.x, A_CORE_STANCE.y)])
        self._note("A at enemy-core stance %s round %d"
                   % (show(self.ct.get_position()), self.ct.get_current_round()))
        yield from self._wait_until(CORE_MEASURE)
        yield from self._measure("FOE_CORE", FOE_CORE_TILE, Direction.EAST)
        yield from self._walk([(18, 6)])
        yield from self._measure("FOE_CORE_2", Position(19, 6), Direction.EAST)

        self._note("=== pt_foe complete at round %d ===" % self.ct.get_current_round())
        self.ct.resign("pt_foe done r%d lines=%d -> file"
                       % (self.ct.get_current_round(), len(self.log)))
