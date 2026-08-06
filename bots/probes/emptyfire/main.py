"""Will a turret fire at an EMPTY tile inside its own attack line?

Noticed while running the first-strike duels (du_s_v0): a Sentinel whose target
had already been destroyed went on firing every 2 rounds for another 34 rounds,
burning 10 ammo a shot.  A Gunner in the identical setup stopped the round its
target died.  This isolates that.

Arena maps/lab/firstshot.map26, no opponent unit anywhere near.  One builder
builds a Sentinel at (6,4) EAST and a Gunner at (6,3) EAST; both look down a
completely empty lane.  For each turret we report:

  ATK   -- get_attackable_tiles()
  CF    -- can_fire() on every one of those tiles (all empty ground)
  FIRE  -- did fire() succeed, and what did global ammo do

Reported by the CORE via resign() -- print() is swallowed (HARNESS.md).
"""

from fcode import Controller, Direction, EntityType, Position

SPAWN = Position(3, 4)
SENT = Position(6, 4)
GUN = Position(6, 3)
RESIGN_ROUND = 40

S_SENT, S_GUN = 0, 1
SLOTS = 8


def _wstr(ct, base, text):
    """pack an ASCII string into consecutive store slots, 4 chars per u32"""
    text = text[:4 * SLOTS]
    for i in range(SLOTS):
        chunk = text[4 * i:4 * i + 4]
        v = 0
        for c in chunk:
            v = (v << 8) | (ord(c) & 0x7F)
        try:
            ct.write_store(base + i, v)
        except Exception:
            pass


def _rstr(ct, base):
    out = []
    for i in range(SLOTS):
        try:
            v = ct.read_store(base + i)
        except Exception:
            v = 0
        chunk = []
        while v:
            chunk.append(chr(v & 0xFF))
            v >>= 8
        out.append("".join(reversed(chunk)))
    return "".join(out)


class Player:
    def __init__(self):
        self.step = 0
        self.spawned = None
        self.done = False
        self.err = []

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            if len(self.err) < 4:
                self.err.append("%s:%s" % (type(exc).__name__, str(exc)[:40]))

    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            self._core(ct)
        elif et == EntityType.BUILDER_BOT:
            self._builder(ct)
        elif et == EntityType.SENTINEL:
            self._turret(ct, 0)
        elif et == EntityType.GUNNER:
            self._turret(ct, 8)

    def _core(self, ct):
        r = ct.get_current_round()
        if self.spawned is None and r >= 1 and ct.can_spawn(SPAWN):
            self.spawned = ct.spawn_builder(SPAWN)
            return
        try:
            if ct.get_global_ammo() < 200 and ct.get_global_resources() > 150:
                if ct.can_convert_ammo(50):
                    ct.convert_ammo(50)
        except Exception:
            pass
        if r >= RESIGN_ROUND:
            ct.resign("EMPTYFIRE SENT[%s] GUN[%s] E%s"
                      % (_rstr(ct, 0), _rstr(ct, 8), ";".join(self.err[:2])))

    def _builder(self, ct):
        if self.step == 0:
            if ct.can_move(Direction.EAST):
                ct.move(Direction.EAST)
                self.step = 1
            return
        if self.step == 1:
            if ct.can_move(Direction.EAST):
                ct.move(Direction.EAST)
                self.step = 2
            return
        if self.step == 2:
            if ct.can_build_sentinel(SENT, Direction.EAST):
                ct.build_sentinel(SENT, Direction.EAST)
                self.step = 3
            return
        if self.step == 3:
            if ct.can_move(Direction.NORTH):
                ct.move(Direction.NORTH)
                self.step = 4
            return
        if self.step == 4:
            if ct.can_build_gunner(GUN, Direction.EAST):
                ct.build_gunner(GUN, Direction.EAST)
                self.step = 5
            return

    def _turret(self, ct, base):
        if self.done:
            return
        r = ct.get_current_round()
        try:
            tiles = ct.get_attackable_tiles()
            cf = "".join("1" if ct.can_fire(p) else "0" for p in tiles)
            occupied = "".join(
                "1" if (ct.get_tile_building_id(p) is not None
                        or ct.get_tile_builder_bot_id(p) is not None) else "0"
                for p in tiles)
            a0 = ct.get_global_ammo()
            fired = "n"
            if tiles and ct.can_fire(tiles[0]):
                try:
                    ct.fire(tiles[0])
                    fired = "y"
                except Exception:
                    fired = "R"
            a1 = ct.get_global_ammo()
            _wstr(ct, base, "n%d cf%s oc%s f%s d%d" % (len(tiles), cf, occupied,
                                                       fired, a0 - a1))
            self.done = True
        except Exception as exc:
            _wstr(ct, base, "E" + type(exc).__name__[:10])
            self.done = True
