"""Definitive 2.3.6 passability table, part 1: terrain, own Core, own Builder Bot, own buildings.

Arena `maps/lab/passlab.map26` (maps/lab/mkpass.py). Run:

    rm -rf bots/probes/pt_own/__pycache__
    .venv/Scripts/python.exe tools/runprobe.py pt_own --map passlab --vs idle

For every target tile this records THREE independent measurements, none inferred:
  1. is_tile_passable(tile)
  2. can_move(direction_to_tile)   -- only ever taken on a round where get_move_cooldown()==0,
     so a False can never be a cooldown artefact
  3. whether move(direction) ACTUALLY relocated the unit: get_position() is sampled before the
     call, immediately after the call, and again on the following round.
plus is_tile_empty / get_tile_env / get_tile_building_id / get_tile_builder_bot_id for context,
and the verbatim GameError text when a call raises.

Output goes to a FILE, not to resign_message: resign_message is hard-truncated at 500 chars
(measured by probe `ptio`), but a bot sub-interpreter CAN open() and write (also measured by
`ptio`). resign() still fires at the end with a one-line summary.
"""

import os

from fcode import Controller, Direction, EntityType, Position

OUT = os.environ.get("PT_OUT") or (
    "C:/Users/edlun/AppData/Local/Temp/claude/"
    "c--Users-edlun-Desktop-lucky-shots-Hackathons-florent-code-league/"
    "69495691-95ef-4878-adf9-aeca64f3e3b5/scratchpad/pt_own.txt"
)

SPAWN_LEAD = Position(3, 7)
SPAWN_HELP = Position(3, 4)

CORE_STANCE = Position(3, 5)   # W -> (2,5) Core A footprint ; N -> (3,4) parked friendly builder
TERR_STANCE = Position(6, 9)   # N -> (6,8) ORE ; W -> (5,9) WALL ; E -> (7,9) EMPTY

# (label, build method, needs a Direction, lane x). Prop is built at (x, 9) from stance (x, 10).
BUILD_SPECS = (
    ("OWN_CONVEYOR", "conveyor", True, 7),
    ("OWN_SPLITTER", "splitter", True, 8),
    ("OWN_HARVESTER", "harvester", False, 9),    # (9,9) is ORE
    ("OWN_BARRIER", "barrier", False, 10),
    ("OWN_GUNNER", "gunner", True, 11),
    ("OWN_SENTINEL", "sentinel", True, 12),
    ("OWN_LAUNCHER", "launcher", False, 13),
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

    # ---------- plumbing ----------

    def run(self, ct: Controller) -> None:
        self.ct = ct
        try:
            et = ct.get_entity_type()
        except Exception:
            return
        if et == EntityType.CORE:
            self._core(ct)
            return
        if et != EntityType.BUILDER_BOT or self.dead:
            return
        if self.role is None:
            self.role = "LEAD" if ct.get_position() == SPAWN_LEAD else "PARK"
        if self.role == "PARK":
            return
        if self.gen is None:
            self.gen = self._script()
        try:
            next(self.gen)
        except StopIteration:
            self.dead = True
        except Exception as exc:
            self.log.append("FATAL %s: %s" % (type(exc).__name__, str(exc)[:200]))
            self.dead = True
            self._flush()

    def _core(self, ct):
        if self.spawned >= 2:
            return
        want = SPAWN_LEAD if self.spawned == 0 else SPAWN_HELP
        try:
            if ct.can_spawn(want):
                ct.spawn_builder(want)
                self.spawned += 1
        except Exception:
            pass

    def _flush(self):
        try:
            with open(OUT, "w", encoding="utf-8") as fh:
                fh.write("\n".join(self.log) + "\n")
        except Exception:
            pass

    def _try(self, fn, *args):
        """Call fn, returning a printable result or the verbatim exception."""
        try:
            return show(fn(*args))
        except Exception as exc:
            return "%s<%s>" % (type(exc).__name__, str(exc)[:90])

    def _occupant(self, ct, tile):
        """Prove what is on the tile: entity id + type + team, for building and builder alike."""
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

    def _note(self, line):
        self.log.append(line)
        self._flush()

    # ---------- movement ----------

    def _walk(self, waypoints):
        """Walk a list of (x,y) waypoints; each leg must be a clear straight cardinal run."""
        for wx, wy in waypoints:
            tgt = Position(wx, wy)
            guard = 0
            while self.ct.get_position() != tgt:
                guard += 1
                if guard > 80:
                    self._note("WALK_STUCK at %s heading to %s"
                               % (show(self.ct.get_position()), show(tgt)))
                    return False
                ct = self.ct
                if ct.get_move_cooldown() == 0:
                    pos = ct.get_position()
                    d = pos.cardinal_direction_to(tgt)
                    if ct.can_move(d):
                        ct.move(d)
                    else:
                        for alt in CARDINALS:
                            if alt is d:
                                continue
                            if pos.add(alt).distance_squared(tgt) < pos.distance_squared(tgt) \
                                    and ct.can_move(alt):
                                ct.move(alt)
                                break
                yield
        return True

    def _idle_until_can_move(self):
        while self.ct.get_move_cooldown() != 0:
            yield

    def _idle_until_can_act(self):
        while not self.ct.can_act():
            yield

    # ---------- the measurement primitive ----------

    def _measure(self, label, tile, d, move_back=True):
        """Record passable / can_move / did-move for `tile`, reached by cardinal `d`."""
        yield from self._idle_until_can_move()
        ct = self.ct
        home = ct.get_position()
        parts = [
            "%-14s tile=%s from=%s dir=%-9s" % (label, show(tile), show(home),
                                                d.name if d is not None else "-"),
            "is_tile_passable=%s" % self._try(ct.is_tile_passable, tile),
            "is_tile_empty=%s" % self._try(ct.is_tile_empty, tile),
            "env=%s" % self._try(ct.get_tile_env, tile),
            self._occupant(ct, tile),
            "move_cd=%d" % ct.get_move_cooldown(),
        ]
        if d is None:
            self._note("  ".join(parts) + "  can_move=-  move()=-  RELOCATED=-")
            return
        parts.append("can_move=%s" % self._try(ct.can_move, d))
        parts.append("move()=%s" % self._try(ct.move, d))
        parts.append("pos_same_round=%s" % show(ct.get_position()))
        yield
        ct = self.ct
        landed = ct.get_position()
        parts.append("pos_next_round=%s" % show(landed))
        parts.append("RELOCATED=%s" % show(landed == tile))
        self._note("  ".join(parts))
        if landed != home and move_back:
            yield from self._walk([(home.x, home.y)])

    # ---------- the script ----------

    def _script(self):
        ct = self.ct
        self._note("=== pt_own : 2.3.6 passability, own side ===")
        self._note("map %dx%d  round=%d  my_id=%d  vision_sq=%d  titanium=%d"
                   % (ct.get_map_width(), ct.get_map_height(), ct.get_current_round(),
                      ct.get_id(), ct.get_vision_radius_sq(), ct.get_global_resources()))

        # ---- stance 1: (3,5). Own Core west, parked friendly builder north. ----
        yield from self._walk([(3, 6), (3, 5)])
        self._note("-- stance CORE_STANCE (3,5) --")

        self._note("SELFTILE       tile=%s  is_tile_passable=%s  is_tile_empty=%s"
                   % (show(self.ct.get_position()),
                      self._try(self.ct.is_tile_passable, self.ct.get_position()),
                      self._try(self.ct.is_tile_empty, self.ct.get_position())))

        # Out-of-bounds and out-of-vision behaviour of the predicates.
        ct = self.ct
        for name, p in (("OOB_X_NEG", Position(-1, 5)),
                        ("OOB_Y_NEG", Position(3, -1)),
                        ("OOB_X_MAX", Position(ct.get_map_width(), 5)),
                        ("FAR_ENEMY_CORE", Position(19, 5))):
            self._note("%-14s tile=%s  is_tile_passable=%s  is_tile_empty=%s  env=%s  d_sq=%d"
                       % (name, show(p),
                          self._try(ct.is_tile_passable, p),
                          self._try(ct.is_tile_empty, p),
                          self._try(ct.get_tile_env, p),
                          ct.get_position().distance_squared(p)))

        yield from self._measure("OWN_CORE", Position(2, 5), Direction.WEST)
        yield from self._measure("OWN_BUILDERBOT", SPAWN_HELP, Direction.NORTH)

        # Diagonals and CENTRE, from a stance where (4,4) is plainly EMPTY.
        yield from self._idle_until_can_move()
        ct = self.ct
        here = ct.get_position()
        for dname, d, tile in (("DIAG_NE", Direction.NORTHEAST, Position(4, 4)),
                               ("DIAG_SE", Direction.SOUTHEAST, Position(4, 6)),
                               ("CENTRE", Direction.CENTRE, here)):
            self._note("%-14s tile=%s from=%s dir=%-9s  is_tile_passable=%s  move_cd=%d  "
                       "can_move=%s  move()=%s  pos_after=%s"
                       % (dname, show(tile), show(here), d.name,
                          self._try(ct.is_tile_passable, tile),
                          ct.get_move_cooldown(),
                          self._try(ct.can_move, d),
                          self._try(ct.move, d),
                          show(ct.get_position())))
        yield
        self._note("DIAG_AFTER     pos_next_round=%s (expected (3,5) if diagonals are illegal)"
                   % show(self.ct.get_position()))
        if self.ct.get_position() != CORE_STANCE:
            yield from self._walk([(CORE_STANCE.x, CORE_STANCE.y)])

        # ---- stance 2: (6,9). Terrain. ----
        yield from self._walk([(3, 10), (6, 10), (6, 9)])
        self._note("-- stance TERR_STANCE (6,9) --")
        yield from self._measure("EMPTY", Position(7, 9), Direction.EAST)
        yield from self._measure("ORE_TITANIUM", Position(6, 8), Direction.NORTH)
        yield from self._measure("WALL", Position(5, 9), Direction.WEST)

        # ---- trap: how far can the three predicates legally be called? ----
        yield from self._idle_until_can_move()
        ct = self.ct
        here = ct.get_position()
        ok_d, raise_d = set(), set()
        for dx in range(-6, 7):
            for dy in range(-6, 7):
                p = Position(here.x + dx, here.y + dy)
                if not (0 <= p.x < ct.get_map_width() and 0 <= p.y < ct.get_map_height()):
                    continue
                dsq = here.distance_squared(p)
                try:
                    ct.is_tile_passable(p)
                    ok_d.add(dsq)
                except Exception:
                    raise_d.add(dsq)
        self._note("VISION_GATE from %s vision_radius_sq=%d  is_tile_passable OK for d_sq in %s"
                   % (show(here), ct.get_vision_radius_sq(), sorted(ok_d)))
        self._note("VISION_GATE raises GameError for d_sq in %s ; is_in_vision(d_sq=20)=%s "
                   "is_in_vision(d_sq=25)=%s ; len(get_nearby_tiles())=%s"
                   % (sorted(raise_d),
                      self._try(ct.is_in_vision, Position(here.x + 4, here.y + 2)),
                      self._try(ct.is_in_vision, Position(here.x + 3, here.y + 4)),
                      self._try(lambda: len(ct.get_nearby_tiles()))))

        # ---- trap: does can_move conflate "impassable" with "still on move cooldown"? ----
        yield from self._walk([(6, 10)])
        yield from self._idle_until_can_move()
        ct = self.ct
        self._note("COOLDOWN pre-move  pos=%s move_cd=%d can_move(EAST)=%s"
                   % (show(ct.get_position()), ct.get_move_cooldown(),
                      self._try(ct.can_move, Direction.EAST)))
        self._note("COOLDOWN post-move pos=%s move()=%s -> pos=%s move_cd=%d "
                   "can_move(EAST)=%s (tile (8,10) is EMPTY)  second move()=%s -> pos=%s"
                   % (show(ct.get_position()), self._try(ct.move, Direction.EAST),
                      show(ct.get_position()), ct.get_move_cooldown(),
                      self._try(ct.can_move, Direction.EAST),
                      self._try(ct.move, Direction.EAST), show(ct.get_position())))
        yield
        ct = self.ct
        self._note("COOLDOWN next round pos=%s move_cd=%d can_move(EAST)=%s"
                   % (show(ct.get_position()), ct.get_move_cooldown(),
                      self._try(ct.can_move, Direction.EAST)))

        # ---- lane row 10: one own building per stance, prop built to the NORTH ----
        yield from self._walk([(6, 10)])
        for label, kind, needs_dir, lx in BUILD_SPECS:
            yield from self._walk([(lx, 10)])
            prop = Position(lx, 9)
            yield from self._idle_until_can_act()
            ct = self.ct
            canb = self._try(getattr(ct, "can_build_" + kind),
                             *((prop, Direction.NORTH) if needs_dir else (prop,)))
            built = self._try(getattr(ct, "build_" + kind),
                              *((prop, Direction.NORTH) if needs_dir else (prop,)))
            self._note("BUILD %-13s at %s  can_build=%s  build=%s  titanium_left=%d"
                       % (label, show(prop), canb, built, ct.get_global_resources()))
            yield
            yield from self._measure(label, prop, Direction.NORTH)
            ct = self.ct
            self._note("       %-13s can_destroy=%s destroy=%s"
                       % (label,
                          self._try(ct.can_destroy, prop),
                          self._try(ct.destroy, prop)))
            yield

        self._note("=== pt_own complete at round %d ===" % self.ct.get_current_round())
        self._flush()
        self.ct.resign("pt_own done r%d lines=%d -> file"
                       % (self.ct.get_current_round(), len(self.log)))
