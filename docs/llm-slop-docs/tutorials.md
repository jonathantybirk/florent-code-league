# Florent Code League — Tutorials

Scraped from https://game.code.florent.vc/tutorials for offline reference. Five modules, 24 lessons total.

1. [Your First Bot: Movement & Sensing](#1-your-first-bot-movement--sensing)
2. [Harvesting Titanium](#2-harvesting-titanium)
3. [Logistics: Conveyors & Splitters](#3-logistics-conveyors--splitters)
4. [Building an Army: Turrets & Combat](#4-building-an-army-turrets--combat)
5. [Coordination & Strategy](#5-coordination--strategy)

---

## 1. Your First Bot: Movement & Sensing

### 1.1 Welcome & the run() loop

Every unit in Florent Code League runs a single Python class called `Player`. The game engine instantiates one `Player` per unit and invokes its `run()` method each round — this method is the complete logic for that unit's turn.

```python
from fcode import Controller, EntityType


class Player:
    def run(self, ct: Controller) -> None:
        etype = ct.get_entity_type()
        if etype == EntityType.CORE:
            pass
```

The controller object (`ct`) is "your only way to interact with the game — move, build, sense the map, read resources, all of it goes through `ct`." Since different unit types share the same `run()` method, code must check the entity type and branch accordingly.

**Try it:**

```
pip install fcode
fcode login
fcode starter
```

Replace `bots/starter/main.py` with the code above, then:

```
fcode run starter starter
fcode watch replay.replay26
```

**Expected outcome:** two stationary Cores sit on the map for all 1000 rounds; the match ends in a random tiebreak since neither side acts.

### 1.2 Spawning a Builder Bot

The Core is stationary — it can't move or attack. Its one job is spawning **Builder Bots**, your mobile workforce. Spawning costs titanium and only works on a tile within the Core's spawn range.

```python
from fcode import Controller, EntityType


class Player:
    def run(self, ct: Controller) -> None:
        etype = ct.get_entity_type()
        if etype == EntityType.CORE:
            for pos in ct.get_nearby_tiles(dist_sq=2):
                if ct.can_spawn(pos):
                    ct.spawn_builder(pos)
                    break
```

`ct.get_nearby_tiles(dist_sq=2)` returns every tile within squared-distance 2 of the Core (the ring of tiles orthogonally/diagonally adjacent to its 2×2 footprint). Each candidate is checked with `ct.can_spawn(pos)` before calling `ct.spawn_builder(pos)`, breaking after the first success so only one unit spawns per round.

This is the general pattern used throughout the API: **the `can_X()` / `X()` pairing — check first, then act.** `can_*` methods never throw; action methods (`spawn_builder`, `move`, `build_harvester`, etc.) raise a `GameError` if invoked illegally, so pre-checking avoids runtime failures.

**Try it:** replace `bots/starter/main.py`, run `fcode run starter starter` then `fcode watch replay.replay26`.

**Expected:** a Builder Bot appears next to each Core in round 1 and sits idle (no `run()` branch for it yet).

### 1.3 Moving your Builder Bot

Builder Bots can only move in the four cardinal directions: `Direction.NORTH`, `SOUTH`, `EAST`, `WEST`. The `Direction` enum includes all 8 compass points plus center, but diagonal movement is illegal — it raises `GameError` and `ct.can_move()` returns `False`.

```python
import random

from fcode import Controller, Direction, EntityType

CARDINALS = [Direction.NORTH, Direction.SOUTH, Direction.EAST, Direction.WEST]


class Player:
    def run(self, ct: Controller) -> None:
        etype = ct.get_entity_type()
        if etype == EntityType.CORE:
            for pos in ct.get_nearby_tiles(dist_sq=2):
                if ct.can_spawn(pos):
                    ct.spawn_builder(pos)
                    break
        elif etype == EntityType.BUILDER_BOT:
            direction = random.choice(CARDINALS)
            if ct.can_move(direction):
                ct.move(direction)
```

Movement triggers a 1-round cooldown, limiting bots to one move per round. This random strategy is intentionally inefficient — bots wander aimlessly.

### 1.4 Sensing the map

Every unit has a vision radius; use `ct.get_nearby_tiles()` plus `ct.get_tile_env()` to read terrain. Three environment states: `EMPTY` (traversable), `WALL` (impassable), `ORE_TITANIUM` (traversable and buildable deposit).

`pos.add(direction)` returns the position one step in that direction *without* moving, letting you peek at a tile's environment before committing to it.

Debugging tools:
- `print()` — captured per-round in the visualizer.
- `ct.draw_indicator_dot()` — marks map locations with colored dots in replay files.

Recommended practice as complexity grows: split logic into a `_run_builder()` helper method. The bot should prioritize moving toward open terrain while keeping fallback options to avoid getting stuck.

**Expected:** a green dot tracks the builder bot each round; console output shows directional decisions; the bot actively avoids walls instead of wandering blindly.

### 1.5 Recap & checkpoint

By this point your bot:
- Dispatches on `ct.get_entity_type()` to handle each unit type separately.
- Spawns a Builder Bot from the Core within its spawn range.
- Moves Builder Bots using directional commands and movement validation.
- Reads the map with `ct.get_tile_env()` to avoid walls and prefer open ground.
- Has debug features (prints, indicator dots).

The `run()` dispatch pattern, the `can_X()` / `X()` check-then-act convention, and vision-based sensing are the foundation for every subsequent system (turrets, harvesters, conveyors).

**Keep your current bot code** — the next module (Harvesting Titanium) builds directly on it rather than starting fresh.

---

## 2. Harvesting Titanium

### 2.1 The titanium economy

Titanium is the only resource in Florent Code League. It's a single shared balance per team, checked via `ct.get_global_resources()`.

**Passive income:** teams receive 10 titanium every 4 rounds, regardless of anything built — resources accumulate even without active play.

All spawning and construction draws from this one unified team balance; any unit can query it any time.

The starter example: a Core that checks resources every 50 rounds and tries to spawn Builder Bots; Builder Bots that move randomly across empty tiles.

### 2.2 Finding ore

Two key `Position` helper methods:
- **`pos.distance_squared(other)`** — used to pick the closest ore tile out of everything currently visible.
- **`pos.cardinal_direction_to(other)`** — converts "I want to go there" into a legal move, always one of the four cardinal directions.

```python
ore_tiles = [t for t in ct.get_nearby_tiles() if ct.get_tile_env(t) == Environment.ORE_TITANIUM]
```

Strategy — "greedy nearest": only consider currently visible ore, re-evaluate each turn. This can cause target-switching between similarly-distant patches; acceptable at this stage.

Decision priority:
1. Move toward visible ore if any exists.
2. Otherwise explore via open directions, avoiding walls.
3. Fall back to random movement among available options.

**Expected:** once a Builder Bot's vision touches an ore tile, it turns and beelines toward it instead of continuing to wander.

### 2.3 Building a Harvester

A Builder Bot can construct a Harvester on ore tiles with `ct.build_harvester(pos)`, when the ore tile is within action radius (squared-distance 2 — orthogonally/diagonally adjacent).

Bot logic: Core spawns Builder Bots on nearby empty tiles; each Builder Bot searches nearby tiles for ore within action radius; if found and buildable, build immediately; otherwise seek ore or explore.

**Important:** "Your Harvester is built and ready to output a stack every 4 rounds, but that titanium has nowhere to go." Harvesters only output to adjacent tiles — without routing infrastructure, extracted resources go nowhere. This sets up the conveyors tutorial.

### 2.4 Cost scaling & early expansion

Build costs increase as your team constructs more entities — **not** as rounds pass. The scale factor starts at 100% and rises incrementally per construction, falling if entities are destroyed. `ct.get_scale_percent()` retrieves the current factor; all cost methods (`get_harvester_cost()` etc.) already include scaling.

Key insight: "cost scaling isn't a clock ticking against you — it's a running tally of what your own team has already built." Deliberate sequencing matters more than rushing; building nothing early incurs no penalty later.

The example Core tracks scaling every 50 rounds while spawning Builder Bots and sending them to harvest — printed harvester cost climbs due to *accumulated construction*, not time passing.

### 2.5 Recap & checkpoint

Your bot can now:
- Access shared team resources via `ct.get_global_resources()`.
- Locate ore deposits via environment sensing + distance calculations.
- Construct Harvester units on detected ore.
- Understand cost scaling via the relevant API calls.

**The gap:** "a Harvester's income is physically stranded unless something routes it to a sink." Extracted titanium can't reach the team's balance without proper transport — motivating the next module: Logistics.

---

## 3. Logistics: Conveyors & Splitters

### 3.1 Why routing matters

A Harvester's output only reaches the 4 tiles directly next to it (N/E/S/W). If no neighboring tile can accept the resource stack, the harvester stalls rather than wasting materials — hence the previous tutorial's harvester never accumulated anything.

**Conveyors** transfer resources one tile per round in a single cardinal direction, enabling long-distance supply chains, using only the four cardinal directions (mirroring movement).

Finding the Core (its location never changes, so cache the result):

```python
core_tile = None
for tile in ct.get_nearby_tiles():
    bid = ct.get_tile_building_id(tile)
    if bid is not None and ct.get_entity_type(bid) == EntityType.CORE:
        core_tile = tile
        break
```

### 3.2 Building a conveyor chain

Full chain-building implementation: find ore, build a Harvester on it, then walk back toward the Core one tile at a time, laying conveyors that point toward the next tile.

```python
import random

from fcode import Controller, Direction, Environment, EntityType, Position

# Builder bots move only in the four cardinal directions.
CARDINALS = [Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST]


def in_bounds(ct: Controller, pos: Position) -> bool:
    return 0 <= pos.x < ct.get_map_width() and 0 <= pos.y < ct.get_map_height()


class Player:
    def __init__(self):
        self.core_tile: Position | None = None
        self.harvester_pos: Position | None = None
        self.chain_done = False

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
        if self.core_tile is None:
            for tile in ct.get_nearby_tiles():
                bid = ct.get_tile_building_id(tile)
                if bid is not None and ct.get_entity_type(bid) == EntityType.CORE:
                    self.core_tile = tile
                    break

        if self.harvester_pos is None:
            self._seek_and_harvest(ct, pos)
        elif not self.chain_done and self.core_tile is not None:
            self._lay_conveyor_toward_core(ct, pos)

    def _seek_and_harvest(self, ct: Controller, pos: Position) -> None:
        # Only cardinal ore tiles: a Harvester's output only reaches its 4
        # cardinal neighbours, so our chain has to start on one of those exactly.
        for d in CARDINALS:
            tile = pos.add(d)
            if not in_bounds(ct, tile):
                continue
            if ct.get_tile_env(tile) == Environment.ORE_TITANIUM and ct.can_build_harvester(tile):
                ct.build_harvester(tile)
                self.harvester_pos = tile
                return

        ore_tiles = [t for t in ct.get_nearby_tiles() if ct.get_tile_env(t) == Environment.ORE_TITANIUM]
        if ore_tiles:
            target = min(ore_tiles, key=lambda t: pos.distance_squared(t))
            direction = pos.cardinal_direction_to(target)
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

    def _pick_direction(self, ct: Controller, pos: Position) -> Direction | None:
        assert self.core_tile is not None
        dx = self.core_tile.x - pos.x
        dy = self.core_tile.y - pos.y
        if dx != 0:
            d = Direction.EAST if dx > 0 else Direction.WEST
            if ct.can_move(d):
                return d
        if dy != 0:
            d = Direction.SOUTH if dy > 0 else Direction.NORTH
            if ct.can_move(d):
                return d
        return None

    def _lay_conveyor_toward_core(self, ct: Controller, pos: Position) -> None:
        direction = self._pick_direction(ct, pos)
        if direction is None:
            self.chain_done = True
            return

        neighbor = pos.add(direction)
        facing_core = False
        if in_bounds(ct, neighbor):
            bid = ct.get_tile_building_id(neighbor)
            facing_core = bid is not None and ct.get_entity_type(bid) == EntityType.CORE

        if ct.can_build_conveyor(pos, direction):
            ct.build_conveyor(pos, direction)

        if facing_core:
            self.chain_done = True
            return

        ct.move(direction)
```

`_pick_direction` closes the horizontal gap to the Core first, then the vertical gap — a simple L-shaped route, sufficient without full pathfinding.

**Bug notice:** this code "works some of the time and silently fails the rest, ending one tile short of the Core with no error, no crash, nothing in the logs" — a reproducible bug explored in the next lesson.

### 3.3 The last mile

**The bug:** when a Builder Bot approaches the Core diagonally, both candidate movement directions can be blocked by the Core's 2×2 footprint simultaneously. The original code inferred "arrival" from `can_move()` returning false — but that just means "something's there" (Core, wall, or another bot); it can't tell you *which*.

**Fix:** query the environment directly instead of inferring from a side effect:

```python
def _lay_conveyor_toward_core(self, ct: Controller, pos: Position) -> None:
    for d in CARDINALS:
        neighbor = pos.add(d)
        if not in_bounds(ct, neighbor):
            continue
        bid = ct.get_tile_building_id(neighbor)
        if bid is not None and ct.get_entity_type(bid) == EntityType.CORE:
            if ct.can_build_conveyor(pos, d):
                ct.build_conveyor(pos, d)
            self.chain_done = True
            return

    direction = self._pick_direction(ct, pos)
    if direction is None:
        self.chain_done = True
        return

    if ct.can_build_conveyor(pos, direction):
        ct.build_conveyor(pos, direction)
    ct.move(direction)
```

**Lesson:** when you need to know "has something specific happened," query for it directly rather than inferring it from a side effect of a different action.

### 3.4 Splitting the flow

A **Splitter** differs from a Conveyor: a Conveyor has one output directly ahead, while a Splitter takes input from directly *behind* it and can output to any of the other three cardinal sides.

Distribution is a rotation, not simultaneous split: each delivery goes whole (10 Ti) to whichever connected side hasn't been used in the longest time — with multiple destinations wired up, they take turns receiving stacks.

Swap the final chain segment (into the Core) from a conveyor to a splitter:

```python
if bid is not None and ct.get_entity_type(bid) == EntityType.CORE:
    if ct.can_build_splitter(pos, d):
        ct.build_splitter(pos, d)
    self.chain_done = True
    return
```

Also replace `build_conveyor`/`can_build_conveyor` with `build_splitter`/`can_build_splitter` elsewhere as needed.

**Why:** "a Splitter at the last junction before your Core is a cheap way to keep your options open" for future expansion without reconstruction.

> Note (per the fcode spec.md and confirmed independently): Splitters have **1 input (back) / 3 outputs**; regular Conveyors have **3 inputs / 1 output** — opposite of each other. Keep this straight when wiring.

### 3.5 Recap & checkpoint

Your bot now:
- Locates its own Core precisely by scanning for a building of type `EntityType.CORE`, rather than estimating from spawn location.
- Builds conveyor chains via `ct.can_build_conveyor` / `ct.build_conveyor`.
- Navigates around obstacles with a two-axis (L-shaped) approach.
- Detects arrival by checking tile occupancy directly instead of inferring from `can_move()`.
- Uses Splitters to add extra output routing before the destination.

Titanium harvesting should now function visibly (match summary shows mined resources). Known limitations remain: independent bots can collide, routing isn't optimized. Still — "You have a working economy loop, which is the foundation everything else builds on."

---

## 4. Building an Army: Turrets & Combat

### 4.1 Meet the turrets

Three turret types — stationary buildings that attack automatically, no CPU needed for targeting/firing decisions:

| Turret | HP | Cost | Damage | Ammo/shot | Reload |
|---|---|---|---|---|---|
| Gunner | 40 | 10 Ti | 10 | 2 | 1 round |
| Sentinel | 30 | 30 Ti | 18 | 10 | 3 rounds |
| Launcher | 30 | 20 Ti | — | — | 1 round |

- **Gunner** — budget option, fires rapidly in a narrow beam along its facing direction; good for corridor defense.
- **Sentinel** — costly, high damage, wider coverage; an anchor, not something to spam.
- **Launcher** — deals no damage; "picks up a friendly Builder Bot within range and throws it to a target position" — a repositioning tool.

**Critical mechanic:** "Ammunition is a team-wide balance, not something a turret carries — and it starts at 0." New turrets can't fire until the Core generates ammunition by converting titanium (next lesson).

### 4.2 Building a Gunner

`ct.build_gunner(pos, direction)` — check with `can_build_gunner` first, as usual, then build while specifying facing direction.

Example: a self-contained combat cluster — Builder Bot finds ore, builds a Harvester to its north and a Gunner to its south (facing further south). The Gunner uses `ct.get_gunner_target()` to find enemies and attempts to fire when possible.

**The problem:** "the Gunner never fires, no matter what walks in front of it... our team never produced a single unit of ammunition." Ammo stays at zero the whole match — combat units are useless without a resource pipeline feeding them (next lesson).

### 4.3 The ammo gap

Ammunition isn't carried by individual turrets — it's a **team-wide balance**, like titanium, starting at 0.

Only the Core can generate it, via `ct.convert_ammo(amount)`, converting titanium to ammo at a 1:1 ratio. Conversion happens at most once per turn, and does **not** consume the Core's action cooldown.

Buffering pattern — keep ammo topped up around a threshold:

```python
if ct.get_global_ammo() < 20 and ct.can_convert_ammo(10):
    ct.convert_ammo(10)
```

`ct.can_convert_ammo(amount)` returns false if you're not the Core, lack sufficient titanium, or already converted this turn.

**Caution:** titanium spent on ammo can't be spent on builders/buildings, and there's no converting back — don't overcommit.

### 4.4 Healing and sabotage

**Healing:** `ct.heal(pos)` repairs friendly units/buildings within action radius, restoring 4 HP per use at a cost of 1 titanium; can heal both a building and a Builder Bot standing on the same tile simultaneously. Check with `ct.can_heal(pos)` first (range, cooldown, resources, and whether there's damage to repair).

```python
if ct.can_heal(pos):
    ct.heal(pos)
```

**Sabotage:** `ct.fire(pos)` — a Builder Bot can only target its **own current tile**, damaging the building beneath it. Useful for sabotage: stand on an enemy Conveyor/Splitter tile and damage it from within, at 2 titanium per strike.

```python
if ct.can_fire(pos):  # pos must equal ct.get_position()
    ct.fire(pos)
```

**Self-destruct:** `ct.self_destruct()` removes the unit with no area damage — useful for freeing unit capacity or retreating before elimination.

### 4.5 Recap & checkpoint

You can now:
- Distinguish turret variants: Gunner (cheap, fast), Sentinel (expensive, hard-hitting), Launcher (repositions, doesn't damage).
- Deploy turrets via `ct.build_gunner` and understand ammunition requirements.
- Convert titanium to ammo via `ct.convert_ammo`, and monitor it with `ct.get_global_ammo()`.
- Repair via `ct.heal()`.
- Use `ct.fire()` for Builder Bot sabotage.
- Treat `self_destruct()` as cleanup, not a weapon.

Putting it together: a Harvester for income, a Gunner guarding it, and a Core that keeps the ammunition balance topped up forms a functional competitive unit.

---

## 5. Coordination & Strategy

### 5.1 The Global Communication Store

Individual units have limited vision. The **Global Communication Store** is a shared blackboard with 16 integer slots (indexed 0–15), readable/writable by all team units.

```python
ct.write_store(0, 42)
value = ct.read_store(0)
```

**Critical timing rule:** writes are buffered — changes made during one round aren't visible until the *following* round. This applies even to the unit that wrote the value.

```python
# Core, round N:
ct.write_store(0, 42)
value = ct.read_store(0)  # still 0 -- this round's snapshot hasn't changed

# Any unit, round N+1:
value = ct.read_store(0)  # now 42
```

This delay guarantees every unit reads a consistent snapshot of the Store for the entire round, regardless of execution order.

**Best practice:** name your slots instead of hardcoding numbers:

```python
SLOT_ORE_X = 0
SLOT_ORE_Y = 1
```

### 5.2 Coordinating roles

Problem: multiple Builder Bots searching for ore independently duplicate effort instead of dividing the search space.

"Let's have any bot that spots an uncovered ore tile broadcast it, so bots with nothing in sight can head toward a real target instead of wandering randomly."

Two slots track a shared ore location:

```python
SLOT_ORE_X = 0
SLOT_ORE_Y = 1
```

`_share_ore()` runs every round for every Builder Bot: the moment any of them sees an ore tile with nothing built on it, its position goes into slots 0 and 1. Bots with no ore in sight instead read the shared slots; `(shared_x or shared_y)` distinguishes real coordinates from the "nothing shared yet" default of zero.

This is a deliberately simple protocol — one shared target, overwritten by whoever last saw ore, no negotiation about who should go there. Multiple bots may converge on the same tile; acceptable at this stage.

### 5.3 Putting it all together

Combines every mechanic: sense the map, harvest ore, route it to the Core with a conveyor chain ending in a Splitter, use the Splitter's spare side to feed a Gunner, and share ore locations over the Store.

State machine with a `Player` class managing three entity types:
- **Core** — spawns Builder Bots at nearby valid positions.
- **Builder Bot** — three-phase workflow: harvest → route → defend.
- **Gunner** — targets and fires at enemies when ammo is available.

Key instance attributes: `harvester_pos`, `chain_done`, `gunner_built`, `splitter_pos`, `gunner_side`.

Components:
- **Ore sharing** — Builder Bots write discovered ore coordinates to the global store.
- **Pathfinding** — `_pick_direction()` computes movement toward the Core via coordinate differences (same L-shaped approach as module 3).
- **Chain building** — conveyors extend toward the Core until it's reached, then a splitter is built with a side reserved for the Gunner.

**Acknowledged limitations:** not optimized, doesn't handle every map layout, and independent Builder Bots can still collide with each other's plans — but it's a fully functional integration of every mechanic covered so far.

### 5.4 Where to go from here

You've now touched every major system: movement/sensing, the titanium economy, conveyor logistics, turret combat, and team-wide coordination via the Global Communication Store. That's the whole rulebook — everything from here is strategy, not new mechanics.

The platform ships a more polished reference bot at `bots/starter_bot.py` (or `bots/starter/main.py` after `fcode starter`). Its own docstring is honest about what it doesn't do yet:

- Build full conveyor chains from distant Harvesters back to the Core.
- Tune the ammo buffer: convert more titanium when enemies are near, less when growing the economy.
- Add Sentinels or Launchers for stronger defense.
- Explore the map systematically instead of picking random targets.
- Use more Store slots to coordinate roles between Builder Bots.

Note: the ammo-buffer tuning problem was already solved in Tutorial 4 — the shipped starter bot doesn't do it. Not a coincidence; a genuinely open problem worth improving on.

**Concrete next steps, roughly in order of effort:**
1. Read the full [Controller API Reference](/docs/robot-api) — methods like `get_attackable_tiles`, `launch`, `can_fire_from` aren't covered in the tutorials.
2. Fix the "independent bots collide" problem — use Store slots to assign roles (harvester / router / defender) instead of every Builder Bot running identical logic.
3. Add real pathfinding — the two-axis walk from Tutorial 3 gets stuck on anything more complex than a simple wall.
4. Layer in Sentinels and Launchers — a Gunner-only defense is predictable and easy to counter.

When ready to test:

```
fcode submit bots/starter
```

Your bot gets queued for ladder matches automatically — check the **Matches** page for results and the **Ladder** page to see your rank.
