# Your First Bot

Source: https://game.code.florent.vc/docs/cli-first-bot

## Scaffold a starter project

```
fcode starter
```

This scaffolds a project in the current directory — an `fcode.toml`, a `maps/` folder, and a working starter bot at `bots/starter/main.py`. Open `bots/starter/main.py` — the structure looks like this:

```python
from fcode import Controller, Direction, EntityType

class Player:
    def __init__(self):
        pass  # initialise per-unit state here

    def run(self, ct: Controller) -> None:
        pass  # called once per round for each of your units
```

## How the engine calls your bot

The engine creates one `Player` instance per unit at the start of the match. Every round, it calls `run()` on each living unit in the order that unit was spawned (the Core acts first, since it exists from round one), passing a fresh `Controller` object.

- `__init__` is for per-unit persistent state (e.g. a movement target the unit is working toward).
- `run()` is where all game actions happen. Everything goes through the `Controller` argument (`ct`).
- For state shared across all your bots, use the [Global Communication Store](../api-reference/global-comms.md).

## A minimal working bot

This starter bot demonstrates the two most common unit types:

```python
from fcode import Controller, Direction, EntityType
import random

class Player:
    def __init__(self):
        self.move_dir = Direction.NORTH

    def run(self, ct: Controller) -> None:
        etype = ct.get_entity_type()

        if etype == EntityType.CORE:
            self._run_core(ct)
        elif etype == EntityType.BUILDER_BOT:
            self._run_builder(ct)

    def _run_core(self, ct: Controller) -> None:
        # Spawn a Builder Bot on any adjacent passable tile
        for pos in ct.get_nearby_tiles(dist_sq=2):
            if ct.can_spawn(pos):
                ct.spawn_builder(pos)
                return

    def _run_builder(self, ct: Controller) -> None:
        # Try to keep moving; bounce off walls. Builder bots move only in
        # the four cardinal directions.
        if ct.can_move(self.move_dir):
            ct.move(self.move_dir)
        else:
            self.move_dir = random.choice(
                [Direction.NORTH, Direction.SOUTH, Direction.EAST, Direction.WEST]
            )
```

## What's available in `run()`

The Controller exposes methods for:

- **Sensing** — read the map, find nearby units and buildings, check tile types
- **Acting** — move, build, attack, heal, spawn units
- **Information** — query your own HP, position, team, round number, resources
- **Debugging** — draw indicator lines and dots in the visualiser

See the full [Controller API Reference](../api-reference/robot-api.md) for every method.
