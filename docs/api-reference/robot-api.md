# Controller API Reference

Source: https://game.code.florent.vc/docs/robot-api

The `Controller` object (`ct`) is passed to your `run()` method every round. All game interactions go through it.

## Movement

| Method | Returns | Description |
|--------|---------|-------------|
| `ct.move(direction)` | `None` | Move one tile in the given direction. Builder Bots may only move in a cardinal direction (N/S/E/W); a diagonal direction raises. Raises on any failure. |
| `ct.can_move(direction)` | `bool` | `True` if the tile is passable and unoccupied. Always `False` for a diagonal direction. |

Compass convention: (0, 0) is the map's northwest corner — x increases eastward, y increases southward, so NORTH is `(0, −1)`, toward row 0. In the visualiser's isometric view north renders up-right on screen (straight up in the square view); the corner compass always shows the current orientation.

Builder Bots move only in the four cardinal directions: NORTH, SOUTH, EAST, WEST. Passing a diagonal (NORTHEAST, NORTHWEST, SOUTHEAST, SOUTHWEST) to `ct.move()` raises a `GameError`, and `ct.can_move()` returns `False` for it. Diagonal directions remain valid for turret facing and building orientation.

> **Correction vs. the official docs.** The published page's example uses `pos.cardinal_direction_to(target)` to "always return a cardinal step." **This method does not exist** in the installed `fcode` engine — confirmed by direct call at runtime (`AttributeError`). Use `direction_to()` and fall back to a rotated direction if it's diagonal and blocked, as below.

```python
from fcode import Direction

# Step toward a target, falling back if the ideal direction is diagonal/blocked.
desired = ct.get_position().direction_to(target)
for move_dir in (desired, desired.rotate_left(), desired.rotate_right()):
    if ct.can_move(move_dir):
        ct.move(move_dir)
        break
```

## Building & Construction

Builder Bots can construct buildings on an orthogonally adjacent tile — NORTH, SOUTH, EAST, or WEST of the bot's current position. Diagonal tiles and its own tile are not valid build targets. `ct.destroy()` follows the same orthogonal-adjacency rule. All build methods raise if the build is not possible.

| Method | Returns | Description |
|--------|---------|-------------|
| `ct.spawn_builder(pos)` | `int` (unit id) | Spawn a Builder Bot at `pos` (Core only). |
| `ct.can_spawn(pos)` | `bool` | `True` if Core can spawn a bot at `pos`. |
| `ct.build_harvester(pos)` | `None` | Build a Harvester on an orthogonally adjacent ore tile. |
| `ct.can_build_harvester(pos)` | `bool` | Check if Harvester can be built. |
| `ct.build_conveyor(pos, direction)` | `None` | Build a conveyor in the given direction. |
| `ct.can_build_conveyor(pos, direction)` | `bool` | Check if a conveyor can be built. |
| `ct.build_splitter(pos, direction)` | `None` | Build a Splitter facing `direction` (accepts only from the back). |
| `ct.can_build_splitter(pos, direction)` | `bool` | Check if a Splitter can be built. |
| `ct.build_barrier(pos)` | `None` | Build a Barrier (no facing direction). |
| `ct.can_build_barrier(pos)` | `bool` | Check if a Barrier can be built. |
| `ct.build_gunner(pos, direction)` | `None` | Build a Gunner turret facing `direction`. |
| `ct.can_build_gunner(pos, direction)` | `bool` | Check if a Gunner can be built. |
| `ct.build_sentinel(pos, direction)` | `None` | Build a Sentinel turret. |
| `ct.can_build_sentinel(pos, direction)` | `bool` | Check if a Sentinel can be built. |
| `ct.build_launcher(pos)` | `None` | Build a Launcher turret (no facing direction). |
| `ct.can_build_launcher(pos)` | `bool` | Check if a Launcher can be built. |
| `ct.destroy(pos)` | `None` | Destroy the allied building at `pos` (orthogonally adjacent). |
| `ct.can_destroy(pos)` | `bool` | Check if the building at `pos` can be destroyed. |
| `ct.build(entity_type, pos, extra=None)` | `None` | Generic build. `extra` is a `Direction`, required for conveyor/splitter/gunner/sentinel, unused otherwise. |
| `ct.can_build(entity_type, pos, extra=None)` | `bool` | Generic legality check for the above. |

## Combat

| Method | Returns | Description |
|--------|---------|-------------|
| `ct.fire(target)` | `None` | Fire at `target` position (turrets only). |
| `ct.can_fire(target)` | `bool` | Check if this unit can fire at `target` (including having enough ammo). |
| `ct.can_fire_from(pos, direction, turret_type, target)` | `bool` | Hypothetical version of `can_fire`: whether a turret of `turret_type` (`EntityType.GUNNER`, `SENTINEL`, or `LAUNCHER`) at `pos` facing `direction` could hit `target`. Uses current map occupancy/walls but ignores ammo and cooldown. |
| `ct.get_attackable_tiles()` | `list[Position]` | List of tiles this unit can currently attack (raw pattern — ignores ammo, cooldown, and occupancy). Raises if this unit is not a turret. |
| `ct.get_attackable_tiles_from(pos, direction, turret_type)` | `list[Position]` | Hypothetical version of `get_attackable_tiles` for a turret of `turret_type` at `pos` facing `direction`. Launchers ignore `direction`. |
| `ct.get_gunner_target()` | `Position \| None` | Closest targetable tile in a Gunner's facing line, or `None` if nothing is in range. Gunner only — raises on any other unit. |
| `ct.heal(pos)` | `None` | Heal all friendly entities (building and/or Builder Bot) on `pos` by 4 HP for 1 Ti. |
| `ct.can_heal(pos)` | `bool` | Check if healing is possible. |
| `ct.self_destruct()` | `None` | Destroy this Builder Bot. Deals zero damage — not a weapon. |
| `ct.rotate(direction)` | `None` | Rotate a Gunner to face `direction` (10 Ti, 1-round cooldown). Gunner only — errors on any other unit. |
| `ct.can_rotate(direction)` | `bool` | Check if rotation is possible (Gunner only). |
| `ct.can_launch(bot_pos, target)` | `bool` | Check if this Launcher can pick up the bot at `bot_pos` (must be adjacent, incl. diagonal) and throw it to `target` (within throw range, bot-passable). |
| `ct.launch(bot_pos, target)` | `None` | Pick up the Builder Bot at `bot_pos` and throw it to `target` (Launcher only). |

> **Correction vs. the official docs.** The published page's `ct.fire()` description says Gunners and Sentinels "spend from your team's global ammunition balance." **There is no global ammunition balance** — ammo is titanium stored per-turret and delivered by conveyor. See [Turrets](../game-rules/game-rules-turrets.md) for the corrected mechanic.

## Vision & Sensing

| Method | Returns | Description |
|--------|---------|-------------|
| `ct.get_nearby_tiles(dist_sq=None)` | `list[Position]` | Tiles within vision (or `dist_sq` if specified). |
| `ct.get_nearby_entities(dist_sq=None)` | `list[int]` | IDs of entities within range. |
| `ct.get_nearby_buildings(dist_sq=None)` | `list[int]` | IDs of buildings within range. |
| `ct.get_nearby_units(dist_sq=None)` | `list[int]` | IDs of mobile units within range. |
| `ct.is_in_vision(pos)` | `bool` | `True` if `pos` is within this unit's vision radius. |
| `ct.get_tile_env(pos)` | `Environment` | Environment type of a tile (`EMPTY`, `WALL`, `ORE_TITANIUM`). |
| `ct.get_tile_building_id(pos)` | `int \| None` | ID of the building at `pos`, or `None`. |
| `ct.get_tile_builder_bot_id(pos)` | `int \| None` | ID of the Builder Bot at `pos`, or `None`. |
| `ct.is_tile_empty(pos)` | `bool` | `True` if no unit or building occupies `pos`. |
| `ct.is_tile_passable(pos)` | `bool` | `True` if a Builder Bot can stand on `pos`. |
| `ct.get_stored_resource(id=None)` | `ResourceType \| None` | Resource type held by a conveyor or splitter (this unit or `id`), or `None` if empty. Raises if the entity has no storage. |
| `ct.get_stored_resource_id(id=None)` | `int \| None` | ID of the resource stack held by a conveyor or splitter (distinct from entity IDs), or `None` if empty. Raises if the entity has no storage. |

## Unit Information

| Method | Returns | Description |
|--------|---------|-------------|
| `ct.get_position(id=None)` | `Position` | Position of this unit (or `id` if given). |
| `ct.get_entity_type(id=None)` | `EntityType` | Type of this unit (or `id` if given). |
| `ct.get_hp(id=None)` | `int` | Current HP of this unit (or `id`). |
| `ct.get_max_hp(id=None)` | `int` | Maximum HP. |
| `ct.get_direction(id=None)` | `Direction` | Facing direction (turrets). |
| `ct.get_id()` | `int` | This unit's ID. |
| `ct.get_team(id=None)` | `Team` | Team of this unit (or `id`). |
| `ct.get_vision_radius_sq(id=None)` | `int` | Vision radius squared. |
| `ct.get_action_cooldown()` | `int` | Rounds until this unit can act again. |
| `ct.get_move_cooldown()` | `int` | Rounds until this unit can move again. |
| `ct.get_unit_count()` | `int` | Total number of your team's units. |

> **Correction vs. the official docs.** The published page also lists `ct.can_act()` as a way to check whether the action cooldown is clear. **This method does not exist** in the installed `fcode` engine — confirmed by direct call at runtime (`AttributeError`). Use `ct.get_action_cooldown() == 0` instead.

For Builder Bots, acting and moving are mutually exclusive per round — a successful build/attack/heal blocks that round's move (and vice versa), so `get_action_cooldown()` and `get_move_cooldown()` reflect only their own trigger even though `can_move()`/`can_build_*()`/`can_fire()`/`can_heal()` already account for both. If `can_move()` returns `False` for a reason that isn't obvious, check `get_action_cooldown()` directly — it may be that this round's action already locked movement.

## Communication Store

Each team has 16 private integer slots shared by all of its units.

| Method | Returns | Description |
|--------|---------|-------------|
| `ct.read_store(index)` | `int` | Read the value at `index` (0–15) from your team's store, as of the start of this round. |
| `ct.write_store(index, value)` | `None` | Buffer a write of `value` to `index` (0–15). Takes effect at the start of next round, visible to all units. |

## Resources & Economy

| Method | Returns | Description |
|--------|---------|-------------|
| `ct.get_global_resources()` | `int` | Current titanium balance for your team. |
| `ct.get_ammo_amount(id=None)` | `int` | Current ammo (titanium) held by this turret (or `id`). |
| `ct.get_ammo_type(id=None)` | `ResourceType \| None` | Resource type held as ammo by this turret, or `None` if empty. |
| `ct.get_scale_percent()` | `float` | Current cost scale factor as a **percentage** (100.0 with nothing built — see the [correction note](../game-rules/game-rules-resources.md#cost-scaling)), increases as your team builds entities, not over time. |
| `ct.get_builder_bot_cost()` | `int` | Titanium cost to spawn a Builder Bot. |
| `ct.get_harvester_cost()` | `int` | Titanium cost to build a Harvester. |
| `ct.get_gunner_cost()` | `int` | Titanium cost to build a Gunner. |
| `ct.get_sentinel_cost()` | `int` | Titanium cost to build a Sentinel. |
| `ct.get_launcher_cost()` | `int` | Titanium cost to build a Launcher. |
| `ct.get_conveyor_cost()` | `int` | Titanium cost to build a conveyor. |
| `ct.get_splitter_cost()` | `int` | Titanium cost to build a Splitter. |
| `ct.get_barrier_cost()` | `int` | Titanium cost to build a Barrier. |

> **Correction vs. the official docs.** The published page lists `ct.get_global_ammo()`, `ct.convert_ammo(amount)`, and `ct.can_convert_ammo(amount)` here, with an example that tops up ammo from the Core each round. **These do not exist** in the installed `fcode` engine (confirmed by enumerating the real `Controller` object — none of the three names appear, and calling them raises `AttributeError`). Ammo is per-turret titanium delivered by conveyor; query it per-turret with `ct.get_ammo_amount()` / `ct.get_ammo_type()` as listed above.

## Map & Match

| Method | Returns | Description |
|--------|---------|-------------|
| `ct.get_map_width()` | `int` | Map width in tiles. |
| `ct.get_map_height()` | `int` | Map height in tiles. |
| `ct.get_current_round()` | `int` | Current round number (0-indexed — 0 on the first round). |
| `ct.get_cpu_time_elapsed()` | `int` | Microseconds of CPU time used this turn. |

## Debugging

| Method | Returns | Description |
|--------|---------|-------------|
| `ct.draw_indicator_line(pos_a, pos_b, r, g, b)` | `None` | Draw a coloured line in the visualiser. |
| `ct.draw_indicator_dot(pos, r, g, b)` | `None` | Draw a coloured dot in the visualiser. |
| `ct.resign(message=None)` | `None` | Forfeit the match immediately. |
