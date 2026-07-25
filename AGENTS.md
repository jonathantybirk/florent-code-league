# AGENTS.md — Florent Code League

Context for AI coding tools (Claude Code, Cursor, GitHub Copilot) working in this repo. Sourced from the platform's own `/docs/agents-md` page.

## Game fundamentals

Two teams control robot fleets on symmetric grids (8×8 to 30×30, randomly drawn from the competition's map pool — not fixed or predictable). Write a single Python `Player` class with a `run(self, ct: Controller)` method. Victory: destroy the enemy Core, or win on tiebreakers after 1000 rounds (titanium collected → harvesters owned → titanium stored → coin flip).

**Constraints:**
- Bots are Python only; entry point is `main.py` containing the `Player` class.
- Each unit gets 10ms CPU time per turn (+5% banked extra).
- Maximum 50 living units per team (Core included).
- Ladder matches are best-of-five series; maps may differ between games in the same series.

## Core game rules

**Resources & economy:** starting titanium 500/team, +10 passive every 4 rounds. Single resource type: titanium. Ammunition is generated only via Core `convert_ammo()` (1 titanium = 1 ammo), starts at 0. Global communication store: 16 integer slots, private per team, shared by all of a team's units, one-round write delay.

**Unit types:**
1. **Core** (2×2 footprint, 500 HP) — spawns builder bots, converts titanium to ammo. Vision r²=36, spawn r²=2.
2. **Builder Bots** (40 HP, 30 Ti) — only mobile units; build/heal/destroy. Vision r²=20, action r²=2. Movement is 8-directional including diagonals (verified against the actual engine — the platform's own docs incorrectly say cardinal-only; don't trust that claim anywhere on the doc site).
3. **Turrets** (immovable): Gunner (40 HP/10 Ti, vision&attack r²=13, 2 ammo/shot, can rotate), Sentinel (30 HP/30 Ti, vision&attack r²=32, 10 ammo/shot, fixed facing), Launcher (30 HP/20 Ti, throws builder bots, no ammo, no facing).
4. **Economic buildings:** Harvester (30 HP/20 Ti, built on ore, outputs 10 Ti every 4 rounds), Conveyor (20 HP/3 Ti, cardinal-facing pipeline), Splitter (20 HP/6 Ti, rotates output among 3 directions), Barrier (30 HP/3 Ti, blocks movement+LOS).

**Cost scaling:** `effective_cost = floor(scale × base_cost)`, scale starts at 1.0 and rises as you build — conveyors/splitters/barriers +1% each, harvesters +5% each, gunners/launchers +10% each, builder bots/sentinels +20% each. Destroying an entity lowers the scale back. Early expansion is disproportionately valuable — always use `get_*_cost()` getters, never hardcode costs.

## Controller API — key categories

- **Info:** `get_team()`, `get_position()`, `get_hp()`, `get_entity_type()`, `get_vision_radius_sq()`, `get_tile_env()`, `get_current_round()`, `get_global_resources()`, `get_global_ammo()`
- **Movement (builder bots only):** `can_move()`, `move()` — cardinal-only
- **Building:** `can_build_conveyor()`, `build_harvester()`, etc.; generic `can_build()`/`build()`
- **Actions:** `heal()`, `destroy()`, `self_destruct()`
- **Turrets:** `can_fire()`, `fire()`, `can_rotate()`/`rotate()` (Gunner only), `can_launch()`/`launch()` (Launcher only)
- **Core:** `can_spawn()`, `spawn_builder()`, `can_convert_ammo()`, `convert_ammo()`
- **Communication:** `read_store()`, `write_store()` (16 slots, index 0–15)

Full reference: [docs/game-docs.md](docs/game-docs.md) in this repo (scraped from the platform docs), or `.venv/.../fcode/data/docs/spec.md` for the engine's own spec.

## Minimal example

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
        if ct.get_global_ammo() < 20 and ct.can_convert_ammo(10):
            ct.convert_ammo(10)
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

## Best practices

- Gate every mutation with a `can_*()` check before calling the action method.
- Use cost getters and `GameConstants` instead of magic numbers.
- Branch on entity type at the top of `run()`.
- Builder bots can move in all 8 directions (incl. diagonals) — use `Position.direction_to()`, not `cardinal_direction_to()`, when pathing them.
- Avoid unbounded loops; stay well inside the 10ms per-unit CPU budget.
- Use the communication store for cross-unit coordination — remember the one-round write delay.
- Never assume today's practice maps (`maps/*.map26`) are what the online ladder will use — the real pool is randomized and announced separately.

## Key types

- **Direction:** `NORTH, NORTHEAST, EAST, SOUTHEAST, SOUTH, SOUTHWEST, WEST, NORTHWEST, CENTRE`; `.delta()`, `.rotate_left()`, `.rotate_right()`, `.opposite()`, `.is_cardinal()`
- **Position:** `(x, y)` NamedTuple with `.add()`, `.distance_squared()`, `.direction_to()`, `.cardinal_direction_to()`
- **EntityType:** `BUILDER_BOT, CORE, GUNNER, SENTINEL, LAUNCHER, CONVEYOR, SPLITTER, HARVESTER, BARRIER`
- **Environment:** `EMPTY, WALL, ORE_TITANIUM`
- **Team:** `A, B`
- **GameConstants:** `MAX_TURNS=1000, STARTING_TITANIUM=500, MAX_TEAM_UNITS=50, STORE_SIZE=16`
