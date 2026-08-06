"""DECISIVE: does a Sentinel's shot pass through WALLs, and a Gunner's not?

Two agents disagreed. `recovered-area-3` claims a Sentinel sealed on all four sides
killed a Core through a barrier and two walls, and cites
`docs/official/docs/game-rules-turrets.txt:83` ("unlike a Gunner's, is never blocked
by walls or units in the way"). The turret hunt reported the opposite -- "turrets shoot
through nothing but empty ground and bare ore" -- but tested Gunners and generalised.
Docs have been wrong 14 times already, so this settles it in-engine.

Arena `maps/lab/sentwall.map26` (built by `maps/lab/mksent.py`):

    x:  0 1 2 3 4 5 6 7 8 9 10 11
    y=3 . A A . . # # . . B B  .        A = our Core, B = enemy Core
    y=4 . A A . S # # . . B B  .        S = our Sentinel, facing EAST
    y=3 . . . . G # # . . . .  .        G = our Gunner,   facing EAST

Sentinel on (4,4) EAST reaches 5 cardinal tiles -> (5,4)..(9,4); (5,4) and (6,4) are
WALL and (9,4) is an enemy Core footprint tile. A Gunner on the same column reaches
only 3, so it can never touch the Core -- any Core damage here crossed two walls.

Reported by the Sentinel via resign():
  SATK  -- its attackable tiles (the direct blocking evidence)
  GATK  -- the Gunner's attackable-tile count, relayed through store slot 1 (1-round lag)
  CF    -- can_fire on the enemy Core footprint tile (9,4)
  HP    -- enemy Core HP samples; a fall proves the shot crossed the wall band
"""

from fcode import Controller, Direction, EntityType, Position

SENT = Position(4, 4)
GUN = Position(4, 3)
SPAWN = Position(3, 4)
TARGET = Position(9, 4)
SLOT_GUN = 1
REPORT_ROUND = 40


class Player:
    def __init__(self):
        self.step = 0
        self.shots = 0
        self.satk = None
        self.cf = None
        self.hp = []
        self.gatk = None
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
            self._sentinel(ct)
        elif et == EntityType.GUNNER:
            self._gunner(ct)

    def _core(self, ct):
        if ct.get_current_round() <= 2 and ct.can_spawn(SPAWN):
            ct.spawn_builder(SPAWN)
            return
        # turrets fire from the GLOBAL ammo pool -- an unfed Sentinel reports
        # can_fire=False forever, which reads exactly like "the wall blocks it"
        try:
            if ct.get_global_ammo() < 300 and ct.can_convert_ammo(50):
                ct.convert_ammo(50)
        except Exception:
            pass

    def _builder(self, ct):
        # one action per round, so walk the construction as a state machine
        if self.step == 0:
            if ct.can_build_sentinel(SENT, Direction.EAST):
                ct.build_sentinel(SENT, Direction.EAST)
                self.step = 1
            return
        if self.step == 1:
            if ct.can_move(Direction.NORTH):
                ct.move(Direction.NORTH)
                self.step = 2
            return
        if self.step == 2:
            if ct.can_build_gunner(GUN, Direction.EAST):
                ct.build_gunner(GUN, Direction.EAST)
                self.step = 3
            return

    def _gunner(self, ct):
        # publish our attackable-tile count so the Sentinel can report it
        try:
            tiles = ct.get_attackable_tiles()
            ct.set_stored_resource(SLOT_GUN, len(tiles) + 1)
        except Exception:
            pass

    def _sentinel(self, ct):
        r = ct.get_current_round()
        if self.satk is None:
            try:
                self.satk = ["%d,%d" % (p.x, p.y) for p in ct.get_attackable_tiles()]
            except Exception as exc:
                self.satk = ["ERR " + type(exc).__name__]
        try:
            cf = ct.can_fire(TARGET)
            if self.cf is None or cf:
                self.cf = "%s@r%d" % (cf, r)
        except Exception as exc:
            self.cf = "ERR " + type(exc).__name__

        # sample enemy Core HP: it is the only enemy building in vision
        if r % 20 == 0:
            for bid in ct.get_nearby_buildings():
                try:
                    if (ct.get_entity_type(bid) == EntityType.CORE
                            and ct.get_team(bid) != ct.get_team()):
                        self.hp.append("r%d:%d" % (r, ct.get_hp(bid)))
                except Exception:
                    pass

        try:
            g = ct.get_stored_resource(SLOT_GUN)
            if g:
                self.gatk = g - 1
        except Exception:
            pass

        try:
            if ct.can_fire(TARGET):
                ct.fire(TARGET)
                self.shots += 1
        except Exception:
            pass

        if r >= REPORT_ROUND:
            ct.resign(
                "SATK=%s | CF=%s | SHOTS=%d | GATK=%s | HP=%s | ERR=%s"
                % (",".join(self.satk or []), self.cf, self.shots,
                   self.gatk, " ".join(self.hp[:8]), ";".join(self.err))
            )
