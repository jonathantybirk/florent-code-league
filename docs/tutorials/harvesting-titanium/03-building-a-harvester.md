# Harvesting Titanium · Step 3 of 5

Source: https://game.code.florent.vc/tutorials/harvesting-titanium/03-building-a-harvester

## Building a Harvester

Once a Builder Bot is orthogonally adjacent to an ore tile — NORTH, SOUTH, EAST, or WEST of its position, never diagonal and never its own tile — it can build a Harvester there with `ct.build_harvester(pos)`.

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

        for d in CARDINALS:
            tile = pos.add(d)
            if ct.get_tile_env(tile) == Environment.ORE_TITANIUM and ct.can_build_harvester(tile):
                ct.build_harvester(tile)
                return

        ore_tiles = [
            t for t in ct.get_nearby_tiles() if ct.get_tile_env(t) == Environment.ORE_TITANIUM
        ]
        if ore_tiles:
            target = min(ore_tiles, key=lambda t: pos.distance_squared(t))
            direction = pos.direction_to(target)
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

We check the four orthogonally adjacent tiles first — if one is ore and buildable, build immediately and stop for this round. Otherwise we fall through to the same seek-and-explore logic as before.

## Try it

```
fcode run starter starter
fcode watch replay.replay26
```

Watch the match summary line at the end of `fcode run` — it prints something like:

```
Titanium     136 (0 mined)    147 (0 mined)
```

That "0 mined" is not a bug — it's the whole point of this step. Your Harvester is built and ready to output a stack every 4 rounds, but that titanium has nowhere to go. A Harvester only feeds the tiles directly next to it, and unless one of those tiles happens to be your Core, it just sits idle — output ready, going nowhere, not actually wasting anything. Nothing in your printed balance will move because of it.

This is by design: harvesting and delivering are two separate problems. Solving delivery — routing a Harvester's output back to your Core — is the entire subject of the next tutorial.

Next: Conveyors, and the cost of not planning your economy layout.
