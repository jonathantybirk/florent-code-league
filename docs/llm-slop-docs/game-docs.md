# Florent Code League — Official Docs

Scraped from https://game.code.florent.vc/docs/* for offline reference (the platform's own documentation, not the tutorials — see `tutorials.md` for those).

## Contents

- [Florent Code League (intro)](#florent-code-league-intro)
- [Quick Start](#quick-start)
- [CLI: Installation](#cli-installation)
- [CLI: Your First Bot](#cli-your-first-bot)
- [CLI: Running Matches](#cli-running-matches)
- [CLI: Submitting](#cli-submitting)
- [CLI Reference](#cli-reference)
- [Game Rules: Overview](#game-rules-overview)
- [Game Rules: How Matches Work](#game-rules-how-matches-work)
- [Game Rules: Core](#game-rules-core)
- [Game Rules: Builder Bot](#game-rules-builder-bot)
- [Game Rules: Turrets](#game-rules-turrets)
- [Game Rules: Conveyors](#game-rules-conveyors)
- [Game Rules: Harvester](#game-rules-harvester)
- [Game Rules: Other Buildings](#game-rules-other-buildings)
- [Game Rules: Resources](#game-rules-resources)
- [Game Rules: Reference tables](#game-rules-reference-tables)
- [Controller API Reference](#controller-api-reference)
- [Types & Enums](#types--enums)
- [Global Communication Store](#global-communication-store)

Note: the platform also publishes an `AGENTS.md` page meant to be copied verbatim into a project as `AGENTS.md`/`CLAUDE.md` for AI coding assistants — that's saved separately at the repo root as [AGENTS.md](../AGENTS.md).

---

## Florent Code League (intro)

Competitive programming competition: write a Python bot that competes on 2D grid maps. Each bot controls a Core base, Builder Bots, and turrets; the objective is to destroy the opponent's Core.

**How it works:**
1. Write a `Player` class with a `run()` method that receives a `Controller`.
2. Test locally with the `fcode` CLI, view replays in the visualizer.
3. Submit via `fcode submit` for ladder entry.
4. Climb the leaderboard by winning matches and accumulating rating.

**The game:** rectangular grid maps, 1000-round max duration. Teams start with one stationary Core and spawn Builder Bots for construction, harvesting, and combat. Victory via Core destruction, or tiebreakers in order: titanium collected → harvester count → titanium stored → coin flip. Titanium is the sole resource — passive income every 4 rounds, plus Harvesters on ore tiles.

**Competition structure:** matches run as a **best-of-five series**. Submissions replace previous ladder entries; unlimited resubmission.

---

## Quick Start

Four steps to get running.

**Prerequisites:** Python 3.12 or 3.13 (3.14 unsupported), pip, a registered platform account.

```
pip install fcode
fcode --version
```

```
fcode login       # opens a browser window to link the CLI to your account
fcode starter     # scaffolds fcode.toml, maps/, and bots/starter/main.py
```

```
fcode run starter starter       # mirror match -> replay.replay26
fcode watch replay.replay26     # view in the browser visualizer
```

```
fcode submit bots/starter       # queues your bot for ladder matches
```

---

## CLI: Installation

The `fcode` CLI handles authentication, local match execution, replay viewing, and bot submissions.

```
python --version     # verify 3.12 or 3.13
pip install fcode
fcode --version
```

Recommended in a virtualenv:

```
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install fcode
```

**Auth:**

```
fcode login    # opens a browser window for approval; stores credentials locally
fcode logout   # clears them
```

**Updating** (do this before competitions to get the latest engine):

```
pip install --upgrade fcode
```

---

## CLI: Your First Bot

`fcode starter` scaffolds `fcode.toml`, `maps/`, and `bots/starter/main.py`:

```python
from fcode import Controller, Direction, EntityType

class Player:
    def __init__(self):
        pass  # initialise per-unit state here

    def run(self, ct: Controller) -> None:
        pass  # called once per round for each of your units
```

**How the engine calls your bot:** one `Player` instance is created *per unit* at match start. Every round, `run()` is called on each living unit **in the order it was spawned** — the Core always acts first, so its resource/store changes are visible to units that act later the same round.

A slightly fuller example (note: this doc's own sample restricts Builder Bot movement to cardinal directions, though other docs on this same site note diagonal movement is also legal for Builder Bots — see the Builder Bot rules page, which is the more authoritative page for movement mechanics):

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
        for pos in ct.get_nearby_tiles(dist_sq=2):
            if ct.can_spawn(pos):
                ct.spawn_builder(pos)
                return

    def _run_builder(self, ct: Controller) -> None:
        if ct.can_move(self.move_dir):
            ct.move(self.move_dir)
        else:
            self.move_dir = random.choice(
                [Direction.NORTH, Direction.SOUTH, Direction.EAST, Direction.WEST]
            )
```

`Controller` covers: sensing (map/units/terrain), acting (movement, construction, combat, repair, spawning), information (HP, position, team, match progress, resources), and debugging (visualizer annotations).

---

## CLI: Running Matches

**Local:**

```
fcode run starter starter
fcode run starter opponent
fcode run starter starter arena     # optional map name/path as 3rd arg
fcode run starter starter --map-random
```

Produces `replay.replay26` and prints results/final round to the terminal. Without a map argument, uses the first map in `maps/`.

**Watch:**

```
fcode watch replay.replay26
```

Full turn-by-turn playback with health bars, resource counters, and your indicator overlays.

**Remote test matches** (run on the actual ranked-match hardware, before submitting):

```
fcode match test starter opponent
```

Runs on the same AWS Graviton3 hardware as ranked ladder matches, so performance here is representative of real matches. **Rate limit: 5 per 10 minutes per account.**

**Unrated challenges** (doesn't affect ladder rating):

```
fcode match unrated <opponent-team-id>
```

Supports up to 5 `--map` flags. Results show on the Matches page. **Rate limit: 5 per 10 minutes per account.**

**Tips:**
- Watch `ct.get_cpu_time_elapsed()` — 10ms per-round CPU limit per unit.
- Use `--seed N` for deterministic/reproducible local matches.

---

## CLI: Submitting

```
fcode submit bot.py
```

Uploads, validates, and enters your bot into the ladder queue; prints a submission ID. Submit any time — each submission replaces your current ladder entry, no limit on resubmissions.

Manage submissions: `fcode submission list`, `fcode submission activate VERSION`, `fcode submission rename VERSION NAME`, `fcode submission download VERSION`.

**What happens after submission:**
1. The platform automatically pairs your bot against other submitted bots.
2. Each pairing runs as a **best-of-five series** on a randomly selected set of maps.
3. Results appear on the leaderboard within a few minutes of the series completing.

**Matches page shows:** match history round-by-round, downloadable replays per game in a series, win/loss record, and current ladder rating.

**Multi-file bots:**

```
zip bot.zip bot.py utils.py strategy.py
fcode submit bot.zip
```

The engine runs `bot.py` as the entry point; every file in the archive is importable at runtime. (For a directory-based submission — `fcode submit bots/starter` — the entry point is `main.py` inside that directory instead.)

**Troubleshooting:**

| Problem | Cause | Fix |
|---|---|---|
| `ValidationError: entry point not found` | No `bot.py` (or `main.py` for a directory) in the archive | Ensure the entry file sits at the archive root |
| `SyntaxError` on submission | Python version mismatch | Use Python 3.12 or 3.13 |
| Bot disqualified mid-match | CPU time exceeded 10ms | Profile with `ct.get_cpu_time_elapsed()` and optimize |

---

## CLI Reference

**Global flags:** `--version`, `--help`

**Auth:** `fcode login` (stores credentials in `~/.fcode/credentials.json`), `fcode logout`

**Setup:** `fcode starter` — scaffolds `fcode.toml`, `.gitignore`, `bots/`, `maps/`, and `bots/starter/main.py`

**`fcode run BOT_A BOT_B [MAP] [--replay FILE] [--seed N] [--watch] [--map-random] [--tle MS]`**

| Arg/flag | Default | Description |
|---|---|---|
| `BOT_A` / `BOT_B` | — | Bot path or name from `bots/`; same value twice = mirror match |
| `MAP` | first map found | Map name/path from `maps/` |
| `--replay FILE` | `replay.replay26` | Output replay path |
| `--seed N` | from config | Deterministic seed |
| `--watch` | off | Auto-open visualizer |
| `--map-random` | off | Pick a random map when none specified |
| `--tle MS` | `0` (disabled) | Per-turn CPU time limit in ms |

**`fcode watch REPLAY`** or **`fcode watch --match MATCH_ID [--game N]`** — open the visualizer.

**`fcode map-editor [--platform]`** — create/edit `.map26` files.

**`fcode submit PATH [--name NAME]`** — shorthand for `fcode submission upload`.

**`fcode submission`** subcommands: `upload PATH [--name NAME]`, `list`, `activate VERSION`, `rename VERSION NAME`, `download [VERSION] [--output FILE]`.

**`fcode match`** subcommands:
- `info MATCH_ID`
- `list [--type ladder|unrated] [--team TEAM] [--mine] [--limit N] [--cursor CURSOR]`
- `unrated OPPONENT_ID [--match SOURCE_MATCH_ID] [--map MAP_NAME]`
- `test BOT_A BOT_B [MAPS...]` (5 per 10 min limit)
- `replay MATCH_ID [--game N] [--output FILE]`
- `watch MATCH_ID [--game N]`
- `tests [--limit N]`

**`fcode team search QUERY`**, **`fcode team info TEAM_ID`**

**`fcode ladder [--limit N] [--around]`** — ladder rankings.

**`fcode status`** — your ladder rating, rank, active submission, recent match record.

---

## Game Rules: Overview

**Win condition:** destroy the opponent's Core. If neither Core falls by round 1000, tiebreakers apply in order: titanium collected → harvesters owned → titanium stored → coin flip.

**The map:** rectangular grid, 8×8 to 30×30 tiles. Tiles are `EMPTY` (traversable), `WALL` (impassable), or `ORE_TITANIUM` (harvestable). **Maps are symmetric and randomly selected from a competition pool** — the pool is announced before competitions begin and may be updated between rounds.

**Units vs. buildings:** Core and turrets count as both; Builder Bots are the only units that aren't buildings.

**Unit cap:** 50 living units per team max (includes the Core).

**Turn order:** every living unit runs `run()` in spawn order each round; the Core always goes first, so its effects (resource changes, store writes becoming readable) are visible to units acting later that same round — except store writes specifically, which have their own one-round buffer (see Global Communication Store below).

**CPU/round limits:** 10ms CPU per unit per round, plus a banked extra-time buffer of up to 5%. Match ends at 1000 rounds if no Core is destroyed.

---

## Game Rules: How Matches Work

**Series structure:** ladder competition = **best-of-five series**, winner is whoever wins 3+ of the 5 games. Ladder rating is based on the series outcome, not individual games. All 5 games always play to completion — no early series termination.

**Map selection:** maps are randomly chosen per series from the active competition pool; different games in the same series can use different maps. The pool is announced before competitions and may be updated between rounds.

**Infrastructure:** matches run on AWS Graviton3 instances — the same hardware for ranked and remote-test matches, so `fcode match test` timings are representative of real ladder performance. Local matches run on your own machine and may have different speed characteristics — profile CPU usage on a remote test before submitting.

**Replays:** every game produces a `.replay26` file on the Matches page — full round-by-round map state, unit HP, resource tallies, and indicator overlays. Open with `fcode watch --match <match-id>` or download locally.

**Scheduling:** an automatic scheduler runs every 10 minutes, pairing submitted bots — no manual match initiation needed. New submissions may take up to 10 minutes to appear in a match.

---

## Game Rules: Core

Immobile 2×2 base. One per team, can't be relocated or rebuilt; destruction = immediate loss.

| Property | Value |
|---|---|
| HP | 500 |
| Footprint | 2×2 |
| Vision radius² | 36 |
| Spawn range² | 2 (adjacent ring, incl. diagonals) |

**Spawn a Builder Bot** (costs titanium, unit acts immediately):

```python
if etype == EntityType.CORE:
    for pos in ct.get_nearby_tiles(dist_sq=2):
        if ct.can_spawn(pos):
            ct.spawn_builder(pos)
            break
```

**Convert ammo** (titanium → ammo, 1:1, shared team pool):

```python
if etype == EntityType.CORE:
    if ct.get_global_ammo() < 20 and ct.can_convert_ammo(10):
        ct.convert_ammo(10)
```

Constraints: max one conversion per team per turn; ammo available instantly; doesn't use the Core's action cooldown; teams start at 0 ammo with no passive income of it.

Notes: the Core counts toward the 50-unit cap; its only actions are spawning and ammo conversion; passive titanium income (10 / 4 rounds) is independent of anything the Core does.

---

## Game Rules: Builder Bot

"Your team's mobile workforce" — the only units that move freely, and the only ones that build/repair.

| Property | Value |
|---|---|
| HP | 40 |
| Cost | 30 Ti |
| Vision radius² | 20 |
| Action radius² | 2 (adjacent + diagonal) |
| Move cooldown | 1 round |
| Action cooldown | 1 round |

**Terrain:** can walk on empty tiles, ore deposits, and conveyor/splitter tiles. Cannot pass through walls, other Builder Bots, or most buildings (harvesters, barriers, cores, turrets).

**Movement:** this doc page, the Controller API reference, and `AGENTS.md` all say cardinal-only — but that's **wrong**. Verified directly against the actual engine (`fcode` binary, not docs): a Builder Bot's `ct.can_move(Direction.NORTHEAST)` returned `True` and `ct.move(Direction.NORTHEAST)` succeeded, moving it diagonally. `spec.md`'s claim that Builder Bots "may move to an adjacent (including diagonal) tile" is the one that's actually correct. Treat the doc site's movement claims as stale; `spec.md` and empirical testing win. `Position.direction_to()` (not `cardinal_direction_to()`) is the right helper for picking a move direction.

**Combat:** can only attack the building on its own current tile — good for sabotaging enemy logistics from within.

**Healing:** 4 HP to friendly units in action radius, 1 Ti per use.

**Self-destruct:** removes the unit, no area damage.

Counts toward the 50-unit cap; the Core can't spawn more until existing units are removed if the cap is hit.

---

## Game Rules: Turrets

Stationary combat buildings, built by Builder Bots. Each turret runs its own `Player` instance/`run()` call per round, same as any unit.

Gunners and Sentinels fire from the team's **global ammunition balance** (2 Ti-equivalent per Gunner shot, 10 per Sentinel shot) — turrets hold no ammo themselves and never need conveyor feeding. Ammo comes only from `convert_ammo()` at the Core; check the balance with `ct.get_global_ammo()`. Launchers use no ammo at all.

Gunners have a facing direction set at build time, adjustable later with `ct.rotate()`. Sentinels also face a fixed direction set at build time but can't rotate afterward. Launchers have no facing direction.

### Gunner

| Property | Value |
|---|---|
| HP | 40 |
| Cost | 10 Ti |
| Damage | 10 |
| Ammo/shot | 2 |
| Fire pattern | Forward ray, single tile width |
| Reload | 1 round |
| Vision / attack radius² | 13 |

Line stops at the first targetable tile (builder bot or building); empty tiles don't block it, walls do (and aren't targetable themselves). Cheap corridor control; the only turret that can rotate post-build.

### Sentinel

| Property | Value |
|---|---|
| HP | 30 |
| Cost | 30 Ti |
| Damage | 18 |
| Ammo/shot | 10 |
| Fire pattern | Any tile within 1 king-move (Chebyshev) of the facing line |
| Reload | 3 rounds |
| Vision / attack radius² | 32 |

A 3-tile-wide band along its facing direction (a thick line, not a cone). Expensive per shot but strong at chokepoints. Facing fixed at build time.

### Launcher

| Property | Value |
|---|---|
| HP | 30 |
| Cost | 20 Ti |
| Action | Picks up an adjacent (incl. diagonal) friendly Builder Bot, throws it to any bot-passable tile in range |
| Pickup radius² | 2 |
| Throw radius² | 26 (measured from the Launcher) |
| Reload | 1 round |

No direct damage, no ammo needed. Value is rapid repositioning — throw a bot up to √26 tiles in one action for surprise plays or fast expansion. No facing direction, can't rotate.

**Rotating (Gunner only):**

```python
if ct.can_rotate(Direction.WEST):
    ct.rotate(Direction.WEST)
```

Costs 10 Ti, sets a 1-round action cooldown. Sentinels/Launchers have no `rotate()`.

---

## Game Rules: Conveyors

Move resources automatically each round at no CPU cost. A stack is always 10 titanium, moving one stack per step per round.

### Basic Conveyor

Fixed single output direction; accepts from the other three cardinal sides.

| Property | Value |
|---|---|
| Base cost | 3 Ti (+1% scaling per conveyor built) |
| Direction | Set at build time |
| Capacity | 1 stack (10 Ti) |

```python
ct.build_conveyor(pos, Direction.EAST)
```

### Splitter

Three possible outputs — the facing direction plus its two adjacent directions. Accepts input only from the back; outputs round-robin to whichever direction was least recently used.

| Property | Value |
|---|---|
| Base cost | 6 Ti (+1% scaling per splitter built) |
| Accepts from | Back only |
| Outputs to | 3 directions, least-recently-used first |
| Capacity | 1 stack (10 Ti) |

```python
if ct.can_build_conveyor(pos, Direction.EAST):
    ct.build_conveyor(pos, Direction.EAST)
```

`ct.destroy()` removes a conveyor/splitter and returns any resource it's holding to your team's balance.

---

## Game Rules: Harvester

Passive-income building. Built on an `ORE_TITANIUM` tile; outputs automatically with no further bot action. Buildings, not units — don't count toward the 50-unit cap, no CPU cost.

| Property | Value |
|---|---|
| HP | 30 |
| Base cost | 20 Ti (+5% scaling per harvester built) |
| Output | 10 Ti every 4 rounds |
| Blocks movement | No |
| Blocks LOS | No |

Outputs to whichever of its 4 cardinal neighbors was used least recently (same round-robin rule as Splitters). First output happens immediately on construction, not after a full 4-round wait.

```python
if ct.get_tile_env(pos) == Environment.ORE_TITANIUM:
    if ct.can_build_harvester(pos):
        ct.build_harvester(pos)
```

No move/action cooldown of its own — its output timer runs independently of your bots' CPU budget. `ct.destroy()` removes it like a conveyor/splitter.

---

## Game Rules: Other Buildings

### Barrier

Blocks movement and LOS; used to create chokepoints and funnel enemies into fire zones.

| Property | Value |
|---|---|
| HP | 30 |
| Cost | 3 Ti |
| Effect | Makes tile impassable |
| Blocks LOS | Yes |

Cannot be placed on wall tiles. Enough enemy firepower destroys it — pair with turrets for real defense.

```python
if ct.can_build_barrier(pos):
    ct.build_barrier(pos)
```

---

## Game Rules: Resources

**Titanium** is the sole currency — one shared balance per team.

```python
titanium = ct.get_global_resources()
```

**Passive income:** 10 titanium every 4 rounds, regardless of anything built.

**Harvesters:** built on ore tiles for ongoing income; unlimited quantity, don't count toward the 50-unit cap. More ore control compounds your economy.

**Cost scaling:** cost grows with entity count, not time. Conveyors/splitters/barriers: +1% each. Harvesters: +5% each. Gunners/launchers: +10% each. Builder bots/sentinels: +20% each. Destroying an entity reduces the scale back.

```python
scale = ct.get_scale_percent()   # 1.0 with nothing built, rises only as you build
cost = ct.get_gunner_cost()      # always use cost getters, not hardcoded numbers
```

**Key takeaway:** "early expansion is disproportionately valuable" — units built early cost much less than the same units built later. Harvesters typically pay back their build cost within dozens of rounds at normal scale. Killing an enemy Harvester denies future income. Movement itself costs no titanium.

---

## Game Rules: Reference tables

### Units

| Entity | HP | Cost (Ti) | Vision r² | Action r² | Spawn r² | Move cooldown |
|---|---|---|---|---|---|---|
| Core | 500 | — | 36 | — | 2 (adjacent ring) | — |
| Builder Bot | 40 | 30 | 20 | 2 | — | 1 |

### Turrets

| Entity | HP | Cost (Ti) | Vision r² | Attack r² | Damage | Ammo/shot | Reload |
|---|---|---|---|---|---|---|---|
| Gunner | 40 | 10 | 13 | 13 | 10 | 2 | 1 |
| Sentinel | 30 | 30 | 32 | 32 | 18 | 10 | 3 |
| Launcher | 30 | 20 | 26 | 26 (throw) / 2 (pickup) | — | — | 1 |

### Infrastructure

| Entity | HP | Cost (Ti, base) | Blocks movement | Blocks LOS |
|---|---|---|---|---|
| Harvester | 30 | 20 | No | No |
| Barrier | 30 | 3 | Yes | Yes |
| Basic Conveyor | 20 | 3 | No | No |
| Splitter | 20 | 6 | No | No |

All costs above are **base** costs — effective cost scales with how much your team has built (see Resources above).

### Game constants

| Constant | Value |
|---|---|
| Round limit | 1000 |
| Unit cap (per team) | 50 (includes Core) |
| CPU time limit (per unit/round) | 10ms (+5% banked extra) |
| Passive titanium income | 10 Ti / 4 rounds |
| Communication store slots | 16 |
| Map size range | 8×8 – 30×30 |
| Series length | Best of 5 |

Cost formula: `effective_cost = base_cost × scale_factor`, scale starts at 1.0, rises only with construction (not time).

---

## Controller API Reference

### Movement

| Method | Returns | Notes |
|---|---|---|
| `ct.move(direction)` | `None` | Builder Bots only; cardinal-only, diagonal raises |
| `ct.can_move(direction)` | `bool` | Always `False` for a diagonal direction |

Compass convention: `(0, 0)` is the map's northwest corner; x increases east, y increases south — `NORTH` is `(0, -1)`.

### Building & construction

| Method | Returns |
|---|---|
| `ct.spawn_builder(pos)` / `ct.can_spawn(pos)` | `int` / `bool` — Core only |
| `ct.build_harvester(pos)` / `ct.can_build_harvester(pos)` | ore tiles only |
| `ct.build_conveyor(pos, direction)` / `ct.can_build_conveyor(...)` | |
| `ct.build_splitter(pos, direction)` / `ct.can_build_splitter(...)` | |
| `ct.build_gunner(pos, direction)` / `ct.can_build_gunner(...)` | |
| `ct.build_sentinel(pos, direction)` / `ct.can_build_sentinel(...)` | |
| `ct.build_launcher(pos)` / `ct.can_build_launcher(pos)` | no facing direction |
| `ct.build_barrier(pos)` / `ct.can_build_barrier(pos)` | |
| `ct.destroy(pos)` / `ct.can_destroy(pos)` | any allied building |
| `ct.build(entity_type, pos, extra=None)` / `ct.can_build(...)` | generic form |

### Combat

| Method | Returns | Notes |
|---|---|---|
| `ct.fire(target)` / `ct.can_fire(target)` | | Builder Bots: own tile only. Gunners/Sentinels: spend ammo (2/10) |
| `ct.get_attackable_tiles()` | `list[Position]` | Raw attack pattern, ignoring ammo/cooldown/occupancy |
| `ct.heal(pos)` / `ct.can_heal(pos)` | | 4 HP, 1 Ti, Builder Bot only |
| `ct.self_destruct()` | `None` | Zero damage, not a weapon |
| `ct.rotate(direction)` / `ct.can_rotate(direction)` | | Gunner only, 10 Ti + 1-round cooldown |
| `ct.can_launch(bot_pos, target)` / `ct.launch(bot_pos, target)` | | Launcher only |

### Vision & sensing

| Method | Returns |
|---|---|
| `ct.get_nearby_tiles(dist_sq=None)` | `list[Position]`, defaults to vision radius |
| `ct.get_nearby_entities/_buildings/_units(dist_sq=None)` | `list[int]` |
| `ct.is_in_vision(pos)` | `bool` |
| `ct.get_tile_env(pos)` | `Environment` |
| `ct.get_tile_building_id(pos)` | `int \| None` |
| `ct.is_tile_empty(pos)` / `ct.is_tile_passable(pos)` | `bool` |

### Unit information

`ct.get_position(id=None)`, `ct.get_entity_type(id=None)`, `ct.get_hp(id=None)`, `ct.get_max_hp(id=None)`, `ct.get_direction(id=None)` (turrets), `ct.get_id()`, `ct.get_team(id=None)`, `ct.get_vision_radius_sq(id=None)`, `ct.get_action_cooldown()`, `ct.get_move_cooldown()`, `ct.get_unit_count()`.

### Resources & economy

| Method | Returns |
|---|---|
| `ct.get_global_resources()` | `int` — team titanium |
| `ct.get_global_ammo()` | `int` — starts at 0, no passive income |
| `ct.convert_ammo(amount)` / `ct.can_convert_ammo(amount)` | Core only, once/turn, doesn't use action cooldown |
| `ct.get_scale_percent()` | `float` |
| `ct.get_*_cost()` | per-entity cost getters (builder_bot, harvester, gunner, sentinel, launcher, conveyor, splitter, barrier) |

### Map & match

`ct.get_map_width()`, `ct.get_map_height()`, `ct.get_current_round()`, `ct.get_cpu_time_elapsed()` (microseconds this turn).

### Debugging

`ct.draw_indicator_line(pos_a, pos_b, r, g, b)`, `ct.draw_indicator_dot(pos, r, g, b)`, `ct.resign(message=None)` — forfeits immediately.

---

## Types & Enums

- **`Team`** — `A`, `B`
- **`EntityType`** — `CORE`, `BUILDER_BOT`, `GUNNER`, `SENTINEL`, `LAUNCHER`, `HARVESTER`, `CONVEYOR`, `SPLITTER`, `BARRIER`
- **`Environment`** — `EMPTY`, `WALL`, `ORE_TITANIUM`
- **`Direction`** — `NORTH`, `SOUTH`, `EAST`, `WEST`, `NORTHEAST`, `NORTHWEST`, `SOUTHEAST`, `SOUTHWEST`, `CENTRE`; has `.delta()`, `.rotate_left()`, `.rotate_right()`, `.opposite()`, `.is_cardinal()`. Builder Bot movement is cardinal-only.
- **`Position`** — `(x, y)` NamedTuple with `.add(direction)`, `.distance_squared(other)`, `.direction_to(other)`, `.cardinal_direction_to(other)`
- **`GameError`** — raised for invalid actions; use `can_*()` checks first

---

## Global Communication Store

16 persistent integer slots per team (indices 0–15), all initialized to 0, private to your own team (opponent writes are invisible).

```python
ct.write_store(0, 42)
value = ct.read_store(0)
```

**Timing:** writes are buffered — committed at end of round, readable by all your units starting **next** round. This guarantees every unit reads a consistent snapshot for the whole round regardless of execution order (see also `SLOT_*` conventions in `bots/starter/main.py`).

**Uses:** scouting coordination (shared target-location slots), unit-population counters, boolean status flags.

**Best practices:** name slots as constants instead of magic numbers; design around the one-round lag; the buffered write is what gives you thread-safety for free.
