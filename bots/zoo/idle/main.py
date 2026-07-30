"""idle -- the zoo floor. Does nothing at all, ever.

Two jobs:

1. The absolute floor. A bot that cannot beat `idle` is broken, not weak.
2. The economy yardstick. `titanium_collected` is an ABSOLUTE tiebreak metric
   (G01/G03): it counts only stacks that land on a Core footprint tile, and it
   is not scaled by what the opponent did. Against an opponent that never
   contests anything, a bot's collected total is a clean read on how much
   economy its build order actually produces.

Deliberately imports nothing. Pure stdlib, no fcode import, no state.
"""


class Player:
    def run(self, ct) -> None:
        return
