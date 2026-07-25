# Controller API Reference

Source: https://game.code.florent.vc/docs/robot-api

## Overview

The `Controller` object (`ct`) is passed to your `run()` method every round, enabling all game interactions.

## Movement

- `ct.move(direction)` → `None`: Move one tile in a given direction (cardinal only for Builder Bots)
- `ct.can_move(direction)` → `bool`: Returns `True` if the tile is passable and unoccupied

**Coordinate System:** (0, 0) is the map's northwest corner — x increases eastward, y increases southward.

Builder Bots move only in cardinal directions (NORTH, SOUTH, EAST, WEST). Diagonal directions raise a `GameError` when passed to `ct.move()`, though they remain valid for turret facing and building orientation.

## Building & Construction

Builder Bots construct on orthogonally adjacent tiles only. All build methods raise if construction isn't possible.

- `ct.spawn_builder(pos)` → `int`: Spawn a Builder Bot (Core only)
- `ct.can_spawn(pos)` → `bool`: Check if spawning is possible
- `ct.build_harvester(pos)` → `None`: Build a Harvester on adjacent ore
- `ct.can_build_harvester(pos)` → `bool`: Check legality
- `ct.build_conveyor(pos, direction)` → `None`: Build conveyor
- `ct.can_build_conveyor(pos, direction)` → `bool`: Check legality
- `ct.build_splitter(pos, direction)` → `None`: Build Splitter
- `ct.can_build_splitter(pos, direction)` → `bool`: Check legality
- `ct.build_barrier(pos)` → `None`: Build Barrier
- `ct.can_build_barrier(pos)` → `bool`: Check legality
- `ct.build_gunner(pos, direction)` → `None`: Build Gunner turret
- `ct.can_build_gunner(pos, direction)` → `bool`: Check legality
- `ct.build_sentinel(pos, direction)` → `None`: Build Sentinel turret
- `ct.can_build_sentinel(pos, direction)` → `bool`: Check legality
- `ct.build_launcher(pos)` → `None`: Build Launcher turret
- `ct.can_build_launcher(pos)` → `bool`: Check legality
- `ct.destroy(pos)` → `None`: Destroy allied building at adjacent position
- `ct.can_destroy(pos)` → `bool`: Check if destruction is possible
- `ct.build(entity_type, pos, extra=None)` → `None`: Generic build method
- `ct.can_build(entity_type, pos, extra=None)` → `bool`: Generic legality check

## Combat

- `ct.fire(target)` → `None`: Fire at target position (turrets only)
- `ct.can_fire(target)` → `bool`: Check if firing is possible
- `ct.can_fire_from(pos, direction, turret_type, target)` → `bool`: Hypothetical fire check
- `ct.get_attackable_tiles()` → `list[Position]`: List of tiles this unit can attack
- `ct.get_attackable_tiles_from(pos, direction, turret_type)` → `list[Position]`: Hypothetical version
- `ct.get_gunner_target()` → `Position | None`: Closest targetable tile in Gunner's line
- `ct.heal(pos)` → `None`: Heal friendly entities by 4 HP for 1 Ti
- `ct.can_heal(pos)` → `bool`: Check if healing is possible
- `ct.self_destruct()` → `None`: Destroy this Builder Bot (zero damage)
- `ct.rotate(direction)` → `None`: Rotate Gunner to face direction (10 Ti, 1-round cooldown)
- `ct.can_rotate(direction)` → `bool`: Check if rotation is possible
- `ct.can_launch(bot_pos, target)` → `bool`: Check if Launcher can throw bot
- `ct.launch(bot_pos, target)` → `None`: Pick up and throw Builder Bot (Launcher only)

## Vision & Sensing

- `ct.get_nearby_tiles(dist_sq=None)` → `list[Position]`: Tiles within vision range
- `ct.get_nearby_entities(dist_sq=None)` → `list[int]`: Entity IDs within range
- `ct.get_nearby_buildings(dist_sq=None)` → `list[int]`: Building IDs within range
- `ct.get_nearby_units(dist_sq=None)` → `list[int]`: Mobile unit IDs within range
- `ct.is_in_vision(pos)` → `bool`: Check if position is within vision radius
- `ct.get_tile_env(pos)` → `Environment`: Environment type (EMPTY, WALL, ORE_TITANIUM)
- `ct.get_tile_building_id(pos)` → `int | None`: Building ID at position or `None`
- `ct.get_tile_builder_bot_id(pos)` → `int | None`: Builder Bot ID at position or `None`
- `ct.is_tile_empty(pos)` → `bool`: Check if tile is unoccupied
- `ct.is_tile_passable(pos)` → `bool`: Check if Builder Bot can stand there
- `ct.get_stored_resource(id=None)` → `ResourceType | None`: Resource held by conveyor/splitter
- `ct.get_stored_resource_id(id=None)` → `int | None`: Resource stack ID

## Unit Information

- `ct.get_position(id=None)` → `Position`: Unit position
- `ct.get_entity_type(id=None)` → `EntityType`: Unit type
- `ct.get_hp(id=None)` → `int`: Current HP
- `ct.get_max_hp(id=None)` → `int`: Maximum HP
- `ct.get_direction(id=None)` → `Direction`: Facing direction (turrets)
- `ct.get_id()` → `int`: This unit's ID
- `ct.get_team(id=None)` → `Team`: Unit's team
- `ct.get_vision_radius_sq(id=None)` → `int`: Vision radius squared
- `ct.get_action_cooldown()` → `int`: Rounds until unit can act again
- `ct.get_move_cooldown()` → `int`: Rounds until unit can move again
- `ct.can_act()` → `bool`: Check if action cooldown is clear
- `ct.get_unit_count()` → `int`: Total number of team's units
- `ct.get_ammo_amount()` → `int`: Ammo currently held by **this turret** (turrets only)
- `ct.get_ammo_type()` → `ResourceType | None`: Resource loaded as ammo in this turret, or `None` if empty (turrets only)

**Note:** For Builder Bots, acting and moving are mutually exclusive per round.

## Communication Store

Each team has 16 private integer slots shared by all units.

- `ct.read_store(index)` → `int`: Read value at index (0–15)
- `ct.write_store(index, value)` → `None`: Buffer write for next round

## Resources & Economy

> **Correction vs. the official docs.** The published page lists `ct.get_global_ammo()`, `ct.convert_ammo(amount)`, and `ct.can_convert_ammo(amount)`. **These do not exist** in the installed `fcode` engine — there is no team-wide ammo balance and no titanium→ammo conversion. Ammo **is titanium**, stored per-turret and delivered by conveyors; query it with `ct.get_ammo_amount()` / `ct.get_ammo_type()` (listed under Unit Information). See [Turrets](../game-rules/game-rules-turrets.md).

- `ct.get_global_resources()` → `int`: Current titanium balance
- `ct.get_scale_percent()` → `float`: Current cost scale factor
- `ct.get_builder_bot_cost()` → `int`: Titanium cost to spawn Builder Bot
- `ct.get_harvester_cost()` → `int`: Titanium cost to build Harvester
- `ct.get_gunner_cost()` → `int`: Titanium cost to build Gunner
- `ct.get_sentinel_cost()` → `int`: Titanium cost to build Sentinel
- `ct.get_launcher_cost()` → `int`: Titanium cost to build Launcher
- `ct.get_conveyor_cost()` → `int`: Titanium cost to build conveyor
- `ct.get_splitter_cost()` → `int`: Titanium cost to build Splitter
- `ct.get_barrier_cost()` → `int`: Titanium cost to build Barrier

## Map & Match

- `ct.get_map_width()` → `int`: Map width in tiles
- `ct.get_map_height()` → `int`: Map height in tiles
- `ct.get_current_round()` → `int`: Current round number (0-indexed)
- `ct.get_cpu_time_elapsed()` → `int`: Microseconds of CPU time used this turn

## Debugging

- `ct.draw_indicator_line(pos_a, pos_b, r, g, b)` → `None`: Draw colored line in visualizer
- `ct.draw_indicator_dot(pos, r, g, b)` → `None`: Draw colored dot in visualizer
- `ct.resign(message=None)` → `None`: Forfeit the match immediately
