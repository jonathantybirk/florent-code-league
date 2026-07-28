# Your First Bot

Source: https://game.code.florent.vc/docs/cli-first-bot

## Scaffold a Starter Project

Execute `fcode starter` to create a project with an `fcode.toml` file, `maps/` folder, and starter bot at `bots/starter/main.py`.

The basic structure includes:

```python
from fcode import Controller, Direction, EntityType

class Player:
    def __init__(self):
        pass  # initialise per-unit state here

    def run(self, ct: Controller) -> None:
        pass  # called once per round for each of your units
```

## How the Engine Calls Your Bot

The engine instantiates one `Player` object **per unit** when the match begins. During each round, it invokes `run()` on every active unit **in spawn order** (Core first), supplying a fresh `Controller` instance.

- `__init__` stores per-unit persistent state (e.g., movement targets)
- `run()` handles all gameplay actions via the `Controller` argument
- Cross-unit state uses the Global Communication Store

## A Minimal Working Bot

This example shows handling two common unit types:

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

## What's Available in `run()`

The `Controller` provides access to:

- **Sensing** — examine the map, locate adjacent units and buildings, identify tile properties
- **Acting** — perform movement, construction, combat, healing, spawning
- **Information** — retrieve your unit's health, coordinates, team affiliation, current round, available resources
- **Debugging** — render visual indicators and markers in the match visualizer

Consult the Controller API Reference for complete method documentation.
