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
|---|---|---|
| `CORE` | Base | Team base unit |
| `BUILDER_BOT` | Mobile | Mobile worker |
| `GUNNER` | Turret | Forward-ray turret |
| `SENTINEL` | Turret | Long-range line turret |
| `LAUNCHER` | Turret | Bot-throwing utility turret |
| `HARVESTER` | Building | Generates titanium from ore tiles |
| `CONVEYOR` | Building | Basic resource conveyor |
| `SPLITTER` | Building | Rotates resource flow between 3 outputs |
| `BARRIER` | Building | Blocks movement and LOS |

```python
etype = ct.get_entity_type()
if etype == EntityType.GUNNER:
    # handle as a turret
```

## Environment

The terrain type of a tile, returned by `ct.get_tile_env()`.

| Value | Description |
|---|---|
| `Environment.EMPTY` | Traversable ground |
| `Environment.WALL` | Impassable wall |
| `Environment.ORE_TITANIUM` | Titanium ore deposit (passable, Harvester-buildable) |

## Direction

The 8 compass directions plus centre. Used for movement, building, and turret orientation.

> **Correction vs. the official docs.** The published page says Builder Bot movement is cardinal-only and recommends `Direction.is_cardinal()` / `Position.cardinal_direction_to()` to handle that. **Neither method exists** in the installed `fcode` engine — confirmed both by enumerating the real `Direction`/`Position` objects at runtime and by direct calls, which raise `AttributeError`. `Direction` does have `delta()`, `rotate_left()`, `rotate_right()`, and `opposite()` (all confirmed working). To test cardinality yourself: `d in (Direction.NORTH, Direction.SOUTH, Direction.EAST, Direction.WEST)`. To pick a legal move toward a target, use `direction_to()` and fall back to `rotate_left()`/`rotate_right()` if the result is diagonal and blocked.

Builder Bot movement is cardinal-only. A Builder Bot may only `ct.move()` in a cardinal direction — NORTH, SOUTH, EAST, or WEST. The four diagonals (NORTHEAST, NORTHWEST, SOUTHEAST, SOUTHWEST) are still valid values, and remain usable for turret facing and building orientation, but passing one to `ct.move()` raises a `GameError` (and `ct.can_move()` returns `False`).

| Value | Description |
|---|---|
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
| `direction.delta()` | `tuple[int, int]` | The `(dx, dy)` step for this direction. |
| `direction.rotate_left()` | `Direction` | This direction rotated 45° counterclockwise. |
| `direction.rotate_right()` | `Direction` | This direction rotated 45° clockwise. |
| `direction.opposite()` | `Direction` | This direction rotated 180°. |

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
| `pos.direction_to(other)` | `Direction` | The direction from `pos` toward `other`, snapped to the nearest 45-degree compass sector. May be a diagonal, so it is **not** always a legal Builder Bot move. |

```python
my_pos = ct.get_position()
target = Position(10, 5)
dist_sq = my_pos.distance_squared(target)         # e.g. 50
dir_to = my_pos.direction_to(target)              # e.g. Direction.NORTHEAST (may be diagonal)
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

Prefer using `can_*` checks before acting to avoid catching exceptions in the hot path.

Letting an exception escape `run()` uncaught is fatal to the unit. This applies to `GameError` and any other exception. Unlike a CPU-time interruption — which just skips that unit's turn and calls `run()` again fresh next round (see [Overview](../game-rules/game-rules-overview.md#cpu-time-limit)) — an uncaught exception permanently destroys the unit. It will never run again for the rest of the match.
