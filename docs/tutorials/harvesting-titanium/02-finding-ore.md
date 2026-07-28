# Harvesting Titanium · Step 2 of 5

Source: https://game.code.florent.vc/tutorials/harvesting-titanium/02-finding-ore

## Finding ore

Ore tiles show up as `Environment.ORE_TITANIUM` when you sense them — the same `ct.get_tile_env()` call from Tutorial 1, just checking for a different value. Let's make the Builder Bot beeline for the nearest one it can see, instead of wandering randomly once ore is in view.

> **Correction vs. the official docs.** The published page uses `pos.cardinal_direction_to(target)` below. **This method does not exist** in the installed `fcode` engine (confirmed by direct call at runtime — raises `AttributeError`). The code below uses `pos.direction_to(target)` instead, falling back to a rotated direction if it comes back diagonal.

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
        for pos in ct.get_nearby_tiles(dist_sq=2):
            if ct.can_spawn(pos):
                ct.spawn_builder(pos)
                break

    def _run_builder(self, ct: Controller) -> None:
        pos = ct.get_position()

        ore_tiles = [
            t for t in ct.get_nearby_tiles() if ct.get_tile_env(t) == Environment.ORE_TITANIUM
        ]
        if ore_tiles:
            target = min(ore_tiles, key=lambda t: pos.distance_squared(t))
            desired = pos.direction_to(target)
            for direction in (desired, desired.rotate_left(), desired.rotate_right()):
                if ct.can_move(direction):
                    ct.move(direction)
                    return

        open_dirs = [
            d for d in CARDINALS
            if ct.can_move(d) and ct.get_tile_env(pos.add(d)) == Environment.EMPTY
        ]
        move_options = open_dirs or [d for d in CARDINALS if ct.can_move(d)]
        if move_options:
            ct.move(random.choice(move_options))
```

Two `Position` helpers do the heavy lifting: `pos.distance_squared(other)` picks the closest ore tile out of everything currently visible, and `pos.direction_to(other)` converts "I want to go there" into a direction — the nearest of all 8 compass points, so it may come back diagonal. Since Builder Bots can only move on the 4 cardinal directions, we try the ideal direction first and fall back to a 45°-rotated one (`rotate_left()`/`rotate_right()`) if it's diagonal or blocked. If no ore is visible yet, we fall back to the same explore-and-avoid-walls logic from Tutorial 1.

This is a "greedy nearest" strategy — it only considers ore it can currently see, and re-evaluates every round, so a bot can flip-flop between two similarly-distant ore patches as it moves. That's fine for now.

## Try it

```
fcode run starter starter
fcode watch replay.replay26
```

What you should see: once a Builder Bot's vision touches an ore tile, it should turn and beeline toward it instead of continuing to wander.

Next: actually build a Harvester there.
