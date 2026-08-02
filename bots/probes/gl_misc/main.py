"""AREA 1 / probe 4: launcher edge cases nobody has measured.

Arena `openfield` (24x20). Launcher at (11,8), built from (11,9).
Conveyors at (12,9) and (10,9) -- both inside the Launcher's r^2<=2 pickup ring.

  X1  can_launch() a builder that is STANDING ON a conveyor?
  X2  can we throw a builder ONTO a conveyor tile (walkable building)?
  X3  two launches in ONE round from one Launcher -- is the ceiling really 1?
  X4  is the Launcher's own tile a legal throw target? a barrier tile? a wall?
  X5  can a Launcher launch ITSELF or a non-builder entity?
  X6  after landing on a conveyor, can the bot still act that round?
"""

from fcode import Controller, Direction, EntityType, GameError, Position

PARK = Position(11, 9)
LAUNCH = Position(11, 8)
CONV_E = Position(12, 9)
CONV_W = Position(10, 9)
BARR = Position(11, 10)


def en(exc):
    return type(exc).__name__ + ":" + str(exc)[:26]


def tf(ct, fn, *a):
    try:
        return "1" if fn(*a) else "0"
    except Exception as exc:
        return "E<" + en(exc) + ">"


class Player:
    def __init__(self):
        self.spawned = False
        self.stage = 0
        self.done = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            print("LP|TOP %s" % en(exc))

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()
        if et == EntityType.CORE:
            if not self.spawned and ct.can_spawn(Position(3, 9)):
                ct.spawn_builder(Position(3, 9))
                self.spawned = True
            return
        if et == EntityType.BUILDER_BOT:
            self._builder(ct, r)
            return
        if et == EntityType.LAUNCHER:
            self._launcher(ct, r)
            return

    def _builder(self, ct, r):
        pos = ct.get_position()
        if self.stage == 0:
            if pos != PARK:
                self._step(ct, pos, PARK)
                return
            if ct.can_build_launcher(LAUNCH):
                ct.build_launcher(LAUNCH)
                self.stage = 1
            return
        if self.stage == 1:
            if ct.can_build_conveyor(CONV_E, Direction.EAST):
                ct.build_conveyor(CONV_E, Direction.EAST)
                self.stage = 2
            return
        if self.stage == 2:
            if ct.can_build_conveyor(CONV_W, Direction.WEST):
                ct.build_conveyor(CONV_W, Direction.WEST)
                self.stage = 3
            return
        if self.stage == 3:
            if ct.can_build_barrier(BARR):
                ct.build_barrier(BARR)
                self.stage = 4
            return
        if self.stage == 4:
            # step EAST onto the conveyor at (12,9)
            if pos == CONV_E:
                bl = ct.get_tile_building_id(pos)
                print("LP|r%d BOT standing on conveyor at %s,%s building=%s" % (
                    r, pos.x, pos.y, bl))
                self.stage = 5
                return
            if ct.can_move(Direction.EAST):
                ct.move(Direction.EAST)
            return
        # stage 5+: report where we are each round (did a throw move us?)
        print("LP|r%d BOT at %s,%s cd_act=%d cd_mov=%d hp=%d" % (
            r, pos.x, pos.y, ct.get_action_cooldown(), ct.get_move_cooldown(), ct.get_hp()))

    def _launcher(self, ct, r):
        if self.done or r < 22:
            return
        bot = None
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                q = Position(LAUNCH.x + dx, LAUNCH.y + dy)
                try:
                    bid = ct.get_tile_builder_bot_id(q)
                except Exception:
                    continue
                if bid is not None:
                    bot = q
        if bot is None:
            return
        self.done = True
        print("LP|r%d bot found at %s,%s" % (r, bot.x, bot.y))
        print("LP|X1 launch-a-bot-on-a-conveyor can_launch(%s,%s -> 11,7)=%s" % (
            bot.x, bot.y, tf(ct, ct.can_launch, bot, Position(11, 7))))
        print("LP|X2 target-IS-a-conveyor can_launch(-> %s,%s)=%s" % (
            CONV_W.x, CONV_W.y, tf(ct, ct.can_launch, bot, CONV_W)))
        print("LP|X4a target-is-launcher-own-tile=%s" % tf(ct, ct.can_launch, bot, LAUNCH))
        print("LP|X4b target-is-barrier(%s,%s)=%s" % (
            BARR.x, BARR.y, tf(ct, ct.can_launch, bot, BARR)))
        print("LP|X4c target-is-source-tile=%s" % tf(ct, ct.can_launch, bot, bot))
        print("LP|X4d target-out-of-bounds(-1,-1)=%s" % tf(ct, ct.can_launch, bot, Position(-1, -1)))
        print("LP|X5a src-is-launcher-itself=%s" % tf(ct, ct.can_launch, LAUNCH, Position(11, 7)))
        print("LP|X5b src-is-empty-tile=%s" % tf(ct, ct.can_launch, Position(10, 7), Position(11, 7)))
        print("LP|X5c src-is-conveyor-no-bot=%s" % tf(ct, ct.can_launch, CONV_W, Position(11, 7)))
        # X2 for real: throw onto the WEST conveyor tile
        try:
            ct.launch(bot, CONV_W)
            print("LP|X2 LAUNCH onto conveyor OK; tile now bot=%s bld=%s" % (
                ct.get_tile_builder_bot_id(CONV_W), ct.get_tile_building_id(CONV_W)))
        except Exception as exc:
            print("LP|X2 LAUNCH onto conveyor FAILED %s" % en(exc))
            return
        # X3: immediately try a second launch in the same round
        print("LP|X3 second-launch-same-round can_launch=%s" % tf(
            ct, ct.can_launch, CONV_W, Position(11, 7)))
        try:
            ct.launch(CONV_W, Position(11, 7))
            print("LP|X3 SECOND LAUNCH SUCCEEDED -- cooldown is NOT 1")
        except Exception as exc:
            print("LP|X3 second launch raised %s" % en(exc))
        print("LP|X3 launcher act_cd=%d" % ct.get_action_cooldown())

    def _step(self, ct, pos, goal):
        dx = goal.x - pos.x
        dy = goal.y - pos.y
        opts = []
        if abs(dx) >= abs(dy):
            if dx:
                opts.append(Direction.EAST if dx > 0 else Direction.WEST)
            if dy:
                opts.append(Direction.SOUTH if dy > 0 else Direction.NORTH)
        else:
            if dy:
                opts.append(Direction.SOUTH if dy > 0 else Direction.NORTH)
            if dx:
                opts.append(Direction.EAST if dx > 0 else Direction.WEST)
        for d in opts:
            if ct.can_move(d):
                ct.move(d)
                return
