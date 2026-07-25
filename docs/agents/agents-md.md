# AGENTS.md

Source: https://game.code.florent.vc/docs/agents-md

## Overview

This page provides guidance for AI coding tools (Claude Code, Cursor, GitHub Copilot) to understand a competitive robotics game. Developers should copy this content into their bot project as `AGENTS.md`, `CLAUDE.md`, or `.cursorrules`.

## Game Fundamentals

Players write a single Python class with a `run(self, ct: Controller)` method. The method executes once per round for every living unit. A team wins by destroying the enemy core, or having the better tiebreakers after round 1000.

The game features:

- Rectangular symmetric grids (8x8 to 30x30)
- One resource type: titanium
- Teams start with 500 titanium and receive 10 passive titanium every 4 rounds
- Maximum 50 living units per team
- Each unit receives 10ms CPU time per turn

## Core Game Rules

**Map tiles** include empty spaces, walls (block building), and ore tiles (for harvester placement only).

**Resources and ammunition:** the single resource is titanium, which moves physically through conveyors/splitters/harvesters. Ammo **is titanium** stored **per-turret** and must be **delivered to each turret via conveyors** — it is NOT a team-global pool and there is NO Core conversion mechanic. (The official docs incorrectly describe a team-wide ammo pool filled by the Core; `convert_ammo`/`can_convert_ammo`/`get_global_ammo` do not exist in the engine. Use the per-turret `get_ammo_amount()` / `get_ammo_type()`.)

**Units include** the core, builder bots, gunners, sentinels, and launchers. Buildings = everything except builder bots; they're immovable.

**Cooldowns** decrease by 1 each round; actions require cooldown == 0.

**Cost scaling** applies multipliers based on entity category: conveyors/splitters/barriers (+1%), harvesters (+5%), gunners/launchers (+10%), builder bots/sentinels (+20%).

## Entity Reference

| Entity | HP | Base Cost | Scale |
|--------|----|-----------| ------|
| Core | 500 | — | — |
| Builder bot | 40 | 30 Ti | +20% |
| Conveyor | 20 | 3 Ti | +1% |
| Splitter | 20 | 6 Ti | +1% |
| Harvester | 30 | 20 Ti | +5% |
| Barrier | 30 | 3 Ti | +1% |
| Gunner | 40 | 10 Ti | +10% |
| Sentinel | 30 | 30 Ti | +20% |
| Launcher | 30 | 20 Ti | +10% |

The core has 2x2 footprint; vision r²=36, action r²=8; spawns ≤1 builder bot/turn on an adjacent tile.

## Controller API

### Information Queries

Methods include `get_team()`, `get_position()`, `get_id()`, `get_action_cooldown()`, `get_move_cooldown()`, `get_vision_radius_sq()`, `get_hp()`, `get_max_hp()`, `get_entity_type()`, `get_direction()`, `get_stored_resource()`, and numerous tile/nearby entity queries.

### Builder Bot Actions

Actions per turn (one per turn, cooldown-gated):

- **Build**: any building type on an orthogonally adjacent empty tile — not diagonal
- **Attack**: 2 Ti → 2 dmg to the building on an orthogonally adjacent tile
- **Heal**: 1 Ti → +4 HP to all friendly entities on an orthogonally adjacent tile
- **Destroy**: Free, unlimited, no cooldown
- **Self-destruct**: No damage dealt

### Movement

Builder bots move only in cardinal directions (north, south, east, west). Diagonal movement raises `GameError`.

### Turret Methods

Gunners and sentinels spend team global ammunition (2 and 10 per shot respectively). Launchers use no ammunition. Methods include `can_fire()`, `fire()`, `can_rotate()`, `rotate()` (gunner-only), and launcher-specific `can_launch()` and `launch()`.

### Core Methods

- `can_spawn(position)` / `spawn_builder(position)`: Spawn adjacent to footprint
- The Core has no ammo-conversion methods. (`can_convert_ammo` / `convert_ammo` do not exist — see the ammunition correction above.)

### Communication Store

`read_store(index)` and `write_store(index, value)` access 16 shared integer slots (index 0–15). Writes are buffered — visible only from the next round.

### Debugging

`draw_indicator_line()` and `draw_indicator_dot()` visualize in replays. `print()` is captured to replay; use stderr for console-only output.

## Key Types and Constants

**Direction**: NORTH, NORTHEAST, EAST, SOUTHEAST, SOUTH, SOUTHWEST, WEST, NORTHWEST, CENTRE with compass convention: (0, 0) is the map's northwest corner, x grows east and y grows south.

**Position**: NamedTuple with methods `.add(direction)`, `.distance_squared()`, `.direction_to()`, `.cardinal_direction_to()`.

**EntityType**: BUILDER_BOT, CORE, GUNNER, SENTINEL, LAUNCHER, CONVEYOR, SPLITTER, HARVESTER, BARRIER.

**Environment**: EMPTY, WALL, ORE_TITANIUM.

**Team**: A, B.

**GameConstants**: MAX_TURNS=1000, STACK_SIZE=10, STARTING_TITANIUM=500, MAX_TEAM_UNITS=50, PASSIVE_TITANIUM_AMOUNT=10, PASSIVE_TITANIUM_INTERVAL=4, STORE_SIZE=16.

**GameError**: Raised by illegal actions; feasible to check first with matching `can_*()` predicates.

## Minimal Idiomatic Example

```python
from fcode import Controller, Direction, EntityType, Environment, Position

class Player:
    def run(self, ct: Controller) -> None:
        kind = ct.get_entity_type()
        if kind == EntityType.CORE:
            self._core_turn(ct)
        elif kind == EntityType.BUILDER_BOT:
            self._builder_turn(ct)

    def _core_turn(self, ct: Controller) -> None:
        # NOTE: there is no Core ammo conversion. Ammo is per-turret and
        # supplied via conveyors — the Core only spawns Builder Bots.
        if ct.get_action_cooldown() != 0:
            return
        if ct.get_global_resources() < ct.get_builder_bot_cost():
            return
        for d in Direction:
            if d == Direction.CENTRE:
                continue
            target = ct.get_position().add(d)
            if ct.can_spawn(target):
                ct.spawn_builder(target)
                return

    def _builder_turn(self, ct: Controller) -> None:
        if ct.get_action_cooldown() == 0:
            for tile in ct.get_nearby_tiles(dist_sq=2):
                if ct.get_tile_env(tile) == Environment.ORE_TITANIUM and ct.can_build_harvester(tile):
                    ct.build_harvester(tile)
                    return
        if ct.get_move_cooldown() == 0:
            for d in (Direction.NORTH, Direction.SOUTH, Direction.EAST, Direction.WEST):
                if ct.can_move(d):
                    ct.move(d)
                    return
```

## Notes for Coding Agents

- Entry point: top-level `class Player` with `run(self, ct: Controller)` in main.py
- Always gate actions with matching `can_*()` checks before mutating methods
- Prefer `get_*_cost()` getters and `GameConstants` over hardcoded numbers
- Branch on `ct.get_entity_type()` at the top of `run()`
- Respect 10ms CPU budget per unit per turn; avoid unbounded loops
- Stay consistent with documented API rather than inventing methods
