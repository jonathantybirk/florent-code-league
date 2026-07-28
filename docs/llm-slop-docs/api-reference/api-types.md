# Types & Enums

Source: https://game.code.florent.vc/docs/api-types

## Overview

All types are importable directly from `fcode`:

```python
from fcode import Controller, Team, EntityType, Environment, Direction, Position, GameError
```

## Team

Identifies which side a unit belongs to.

| Value | Description |
|-------|-------------|
| `Team.A` | Team A |
| `Team.B` | Team B |

```python
if ct.get_team() == Team.A:
    # we are team A
```

## EntityType

The type of a unit or building.

| Value | Category | Description |
|-------|----------|-------------|
| `CORE` | Base | Team base unit |
| `BUILDER_BOT` | Mobile | Mobile worker |
| `GUNNER` | Turret | Forward-ray turret |
| `SENTINEL` | Turret | Long-range line turret |
| `LAUNCHER` | Turret | Bot-throwing utility turret |
| `HARVESTER` | Building | Generates titanium from ore tiles |
| `CONVEYOR` | Building | Basic resource conveyor |
| `SPLITTER` | Building | One input side (the back); rotates resource flow between its 3 outputs |
| `BARRIER` | Building | Blocks movement and LOS |

```python
etype = ct.get_entity_type()
if etype == EntityType.GUNNER:
    # handle as a turret
```

## Environment

The terrain type of a tile, returned by `ct.get_tile_env()`.

| Value | Description |
|-------|-------------|
| `Environment.EMPTY` | Traversable ground |
| `Environment.WALL` | Impassable wall |
| `Environment.ORE_TITANIUM` | Titanium ore deposit (passable, Harvester-buildable) |

## Direction

The 8 compass directions plus centre. Used for movement, building, and turret orientation.

> Builder Bot movement is cardinal-only. A Builder Bot may only `ct.move()` in a cardinal direction — `NORTH`, `SOUTH`, `EAST`, or `WEST`.

| Value | Description |
|-------|-------------|
| `Direction.NORTH` | Up |
| `Direction.SOUTH` | Down |
| `Direction.EAST` | Right |
| `Direction.WEST` | Left |
| `Direction.NORTHEAST` | Up-right |
| `Direction.NORTHWEST` | Up-left |
| `Direction.SOUTHEAST` | Down-right |
| `Direction.SOUTHWEST` | Down-left |
| `Direction.CENTRE` | No movement (current tile) |

| Method | Returns | Description |
|--------|---------|-------------|
| `direction.is_cardinal()` | `bool` | `True` only for `NORTH`, `SOUTH`, `EAST`, `WEST` (a legal Builder Bot move). |

## Position

A 2D grid coordinate.

```python
pos = Position(x=3, y=7)
```

| Attribute / Method | Returns | Description |
|-------------------|---------|-------------|
| `pos.x` | `int` | Column (0-indexed from left) |
| `pos.y` | `int` | Row (0-indexed from top) |
| `pos.add(direction)` | `Position` | Returns the adjacent position in `direction`. |
| `pos.distance_squared(other)` | `int` | Squared Euclidean distance to `other`. Avoids floating point. |
| `pos.direction_to(other)` | `Direction` | The direction from `pos` toward `other`. May be a diagonal, so it is **not** always a legal Builder Bot move. |
| `pos.cardinal_direction_to(other)` | `Direction` | A legal cardinal step from `pos` toward `other` (or `CENTRE` if already there). Prefer this for choosing a move. |

```python
my_pos = ct.get_position()
target = Position(10, 5)
dist_sq = my_pos.distance_squared(target)         # e.g. 50
dir_to = my_pos.direction_to(target)              # e.g. Direction.NORTHEAST (may be diagonal)
move_dir = my_pos.cardinal_direction_to(target)   # e.g. Direction.NORTH (always a legal move)
```

## GameError

Raised when an action is not valid (e.g. moving into a wall, building without sufficient titanium).

```python
from fcode import GameError

try:
    ct.move(Direction.NORTH)
except GameError as e:
    # handle gracefully
    pass
```

> Letting an exception escape `run()` uncaught is fatal to the unit. This applies to `GameError` and any other exception.
