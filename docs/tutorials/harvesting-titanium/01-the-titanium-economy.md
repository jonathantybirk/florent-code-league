# Harvesting Titanium · Step 1 of 5

Source: https://game.code.florent.vc/tutorials/harvesting-titanium/01-the-titanium-economy

## The titanium economy

Titanium is the only resource in Florent Code League. It's a single shared balance per team — every build and spawn action draws from the same pool, and every unit can read it with `ct.get_global_resources()`.

```python
import random

from fcode import Controller, Direction, Environment, EntityType

CARDINALS = [Direction.NORTH, Direction.SOUTH, Direction.EAST, Direction.WEST]

class Player:
    def run(self, ct: Controller) -> None:
        etype = ct.get_entity_type()
        if etype == EntityType.CORE:
            self._run_core(ct)
        elif etype == EntityType.BUILDER_BOT:
            self._run_builder(ct)

    def _run_core(self, ct: Controller) -> None:
        titanium = ct.get_global_resources()
        if ct.get_current_round() % 50 == 0:
            print(f"round {ct.get_current_round()}: {titanium} titanium")

        for pos in ct.get_nearby_tiles(dist_sq=2):
            if ct.can_spawn(pos):
                ct.spawn_builder(pos)
                break

    def _run_builder(self, ct: Controller) -> None:
        pos = ct.get_position()
        open_dirs = [
            d for d in CARDINALS
            if ct.can_move(d) and ct.get_tile_env(pos.add(d)) == Environment.EMPTY
        ]
        move_options = open_dirs or [d for d in CARDINALS if ct.can_move(d)]
        if move_options:
            ct.move(random.choice(move_options))
```

This is your Tutorial 1 bot, unchanged apart from the Core printing its balance every 50 rounds. `ct.get_global_resources()` returns a plain `int` — your team's current titanium balance. Every cost-related method in the API returns the same kind of plain `int`; you'll see one in a moment.

Every team also gets passive income: 10 titanium every 4 rounds, regardless of anything you build. It's small, but it means titanium always ticks upward even if your economy does nothing — which is exactly what you'll see in this step, since we haven't built a Harvester yet.

## Try it

```
fcode run starter starter
fcode watch replay.replay26
```

What you should see: the printed balance climbing slowly and steadily — roughly +10 every 4 rounds, minus whatever the Core is spending to spawn Builder Bots. That slow climb is pure passive income.

Next: find some ore.
