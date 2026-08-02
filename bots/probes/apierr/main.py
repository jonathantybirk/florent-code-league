"""Error taxonomy: which illegal actions RAISE, and which fail silently?

An uncaught exception permanently deletes the unit (G23), so we already wrap everything.  The far more
dangerous case is the opposite one: a call that returns normally without doing anything, because then
the bot's own model of the world silently diverges from the engine's.  Every such call is a bug factory.

Each case is invoked inside a guard and scored:
    R = raised GameError    T = TypeError    V = ValueError    O = OverflowError    I = IndexError
    N = returned normally, no exception
An N is only benign if the call actually did something; the N cases are listed in the report file.

The BUILDER is the reporting unit -- notes live on one unit's Player instance and are invisible to any
other unit (M07), so the Core cannot report what the builder measured.  Core-only calls are therefore
exercised *from the builder*, which is the interesting direction anyway (wrong-unit calls).

Arena `scal`: builder homes to (6,9); ore at (6,8) and (6,10); Core A footprint (1,9)..(2,10).
Reported through ct.resign() (G29), under the 500-char cap (M06).
"""

from fcode import Controller, Direction, EntityType, GameError, Position

HOME = Position(6, 9)
NEAR2 = Position(6, 7)        # in vision (d^2=4) but NOT orthogonally adjacent
DIAG = Position(7, 8)         # diagonal neighbour
WEST = Position(5, 9)         # orthogonal, empty ground
OOB = Position(-1, -1)
CORET = Position(2, 9)        # our own Core footprint, far away


class Player:
    def __init__(self):
        self.n = []
        self.spawned = False
        self.ph = 0
        self.done = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.n.append("T:" + type(exc).__name__)

    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            if not self.spawned and ct.can_spawn(Position(3, 9)):
                ct.spawn_builder(Position(3, 9))
                self.spawned = True
            return
        if et != EntityType.BUILDER_BOT or self.done:
            return
        pos = ct.get_position()

        if self.ph == 0:
            if pos != HOME:
                d = pos.cardinal_direction_to(HOME)
                if ct.can_move(d):
                    ct.move(d)
                return
            self.ph = 1
            return

        if self.ph == 1:
            self.ph = 2
            self.add("mvdiag", ct, lambda: ct.move(Direction.NORTHEAST))
            self.add("mvctr", ct, lambda: ct.move(Direction.CENTRE))
            self.add("bnear2", ct, lambda: ct.build_barrier(NEAR2))
            self.add("bdiag", ct, lambda: ct.build_barrier(DIAG))
            self.add("bself", ct, lambda: ct.build_barrier(HOME))
            self.add("boob", ct, lambda: ct.build_barrier(OOB))
            self.add("hvnoore", ct, lambda: ct.build_harvester(WEST))
            return

        if self.ph == 2:
            self.ph = 3
            self.add("healemp", ct, lambda: ct.heal(WEST))
            self.add("healslf", ct, lambda: ct.heal(HOME))
            self.add("desemp", ct, lambda: ct.destroy(WEST))
            self.add("descore", ct, lambda: ct.destroy(CORET))
            self.add("firslf", ct, lambda: ct.fire(HOME))
            self.add("firdiag", ct, lambda: ct.fire(DIAG))
            self.add("firemp", ct, lambda: ct.fire(WEST))
            return

        if self.ph == 3:
            self.ph = 4
            self.add("rot", ct, lambda: ct.rotate(Direction.NORTH))
            self.add("gtgt", ct, lambda: ct.get_gunner_target())
            self.add("atkt", ct, lambda: ct.get_attackable_tiles())
            self.add("lnch", ct, lambda: ct.launch(HOME, WEST))
            self.add("spawn", ct, lambda: ct.spawn_builder(WEST))
            self.add("cvt", ct, lambda: ct.convert_ammo(1))
            self.add("dir", ct, lambda: ct.get_direction())
            self.add("stor", ct, lambda: ct.get_stored_resource())
            return

        if self.ph == 4:
            self.ph = 5
            self.add("envoob", ct, lambda: ct.get_tile_env(OOB))
            self.add("envfar", ct, lambda: ct.get_tile_env(Position(20, 19)))
            self.add("psoob", ct, lambda: ct.is_tile_passable(OOB))
            self.add("visoob", ct, lambda: ct.is_in_vision(OOB))
            self.add("bidoob", ct, lambda: ct.get_tile_building_id(OOB))
            self.add("hpbad", ct, lambda: ct.get_hp(99999))
            self.add("nbt400", ct, lambda: ct.get_nearby_tiles(400))
            self.add("selfdes", ct, lambda: ct.can_destroy(HOME))
            return

        if self.ph == 5:
            self.done = True
            ct.resign("ERR|" + ",".join(self.n))

    def add(self, label, ct, fn):
        self.n.append(label + "=" + self.k(fn))

    def k(self, fn):
        try:
            fn()
            return "N"
        except GameError:
            return "R"
        except TypeError:
            return "T"
        except ValueError:
            return "V"
        except OverflowError:
            return "O"
        except IndexError:
            return "I"
