"""Probe: are module-level globals shared between units?

Ground-truth claim G20 says each unit runs in its own CPython sub-interpreter, so
module globals are private and the 16-slot store (1-round lag) is the only channel.
G20 is marked CARRIED-2.2.0 and has never been re-run on 2.3.x, so this settles it.

Design: the Core mutates a module-level dict on round 2 and also bumps a module
counter every round. A Builder Bot reads both on round 8 and resigns with the
verdict. If globals are shared, the builder sees CANARY=12345 and a counter far
above its own contribution.

Reporting goes through ct.resign() because print() never reaches stdout (G29).
"""

from fcode import Controller, EntityType, GameError, Position

# Module-level state. If units share an interpreter, every unit sees these.
SHARED = {"canary": 0, "core_round": -1}
TICKS = [0]


class Player:
    def __init__(self):
        self.mine = 0
        self.reported = False

    def run(self, ct: Controller) -> None:
        try:
            self.play(ct)
        except GameError:
            pass

    def play(self, ct: Controller) -> None:
        rnd = ct.get_current_round()
        # Every unit bumps the shared counter and its own private counter.
        TICKS[0] += 1
        self.mine += 1

        etype = ct.get_entity_type()

        if etype == EntityType.CORE:
            if rnd == 2:
                SHARED["canary"] = 12345
                SHARED["core_round"] = rnd
                # Store write, to time the documented 1-round lag against it.
                ct.write_store(5, 777)
            if rnd <= 3:
                self.spawn(ct)
            return

        if etype != EntityType.BUILDER_BOT:
            return

        if rnd == 8 and not self.reported:
            self.reported = True
            canary = SHARED["canary"]
            slot5 = ct.read_store(5)
            verdict = "SHARED" if canary == 12345 else "ISOLATED"
            ct.resign(
                "G20=%s canary=%d core_round=%d ticks=%d mine=%d slot5=%d"
                % (verdict, canary, SHARED["core_round"], TICKS[0], self.mine, slot5)
            )

    def spawn(self, ct: Controller) -> None:
        pos = ct.get_position()
        for dx, dy in ((0, 2), (2, 0), (0, -2), (-2, 0), (2, 2), (-2, -2)):
            target = Position(pos.x + dx, pos.y + dy)
            if ct.can_spawn(target):
                ct.spawn_builder(target)
                return
