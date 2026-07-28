# Engine Spec

Source: bundled with the `fcode` PyPI package (v2.2.0), at `fcode/data/docs/spec.md` inside the installed package — **not** scraped from the website. This is the closest thing to a primary source we've found: it ships with the compiled engine itself rather than being a separately-maintained doc page, so where it disagrees with the website, this file tends to be the one to trust. That said, it is not infallible — see the correction below, found by directly probing the running engine.

# Background

The year is 2076. Titan, Saturn's largest moon, has become the new frontier for autonomous resource extraction. At least six corporations have deployed robotic fleets to its surface, claiming deposits, building infrastructure, and contesting rival operations. None of this has been publicly disclosed.

Titan is lethal to humans: −179°C, a nitrogen-methane atmosphere, and a 76-minute communication delay to Earth. All operations are carried out by robots.

You are a programmer employed by **Meridian Industries** under the classified ASO (Autonomous Systems Operations) programme. Your job is to write the software that controls Meridian's fleet: mining ore, delivering resources, and outcompeting whoever else is out there.

# Objective

The objective of the game is to collect resources and destroy the enemy's core.
To do this, you must find ore deposits, build harvesters, deliver resources back to the core using conveyors, and expand your territory.

If both teams' cores are still alive after 1000 rounds, the winner is decided by the following tiebreakers, in order:

- Total amount of titanium delivered to the core
- Number of harvesters currently alive
- Total titanium currently stored
- Coinflip

# Map

The map is a rectangular grid whose size is between 8x8 and 30x30 inclusive.
The top left (northwest) corner of the map is position (0, 0).
It is guaranteed that the map is symmetric by either reflection or rotation.

Each grid cell is one of the following:

- Wall
- Titanium ore
- Empty

Walls prevent building anything on the tile they occupy.
Ores are tiles on which harvesters may be built to mine resources.

# Resources

## Titanium

Titanium is the primary resource used to construct most buildings in the game.
Each team starts with 500 global titanium.
Additionally, each team gains 10 passive titanium every 4 rounds.

# Communication

Each team has a **Global Communication Store**: 16 integer slots (indexed 0-15), readable and writable by every unit on that team via `read_store(index)` / `write_store(index, value)`. Each team's store is private -- the opposing team can neither read nor write it.

Writes are buffered: a write made during a round is not visible until the following round, not even to the unit that made it. This guarantees every unit sees a consistent snapshot of the store for the entire round, regardless of the order units act in.

There is no per-slot ownership, locking, or namespacing — it's just 16 raw shared integers per team. Nothing stops two different pieces of your bot's logic from silently colliding on the same slot; that's on you to manage by convention (fixed layout, named constants), not something the engine enforces.

# Units and Buildings

## Units

Units are game entities which run an independent instance of the code that you submit.
The core, builder bots, and turrets are units. Harvesters are **not** units.

Each round, units take their turns in the order they were spawned.
After all units have taken their turn, resources are distributed (see below).

Each team may have at most 50 living units at once, including its core.
Bots can query their current usage of this cap with `get_unit_count()` and compare it against `GameConstants.MAX_TEAM_UNITS`.

Units have a **vision radius** and an **action radius**.
The vision radius is the area in which the unit can sense its environment.
The action radius is the area in which the unit can perform actions, such as building or destroying buildings.
All units have an action radius of sqrt(2), except the core, which has an action radius of sqrt(8) (measured from its centre).
Turrets also have a **attack range** which is different from its action radius.

All units have action and move cooldowns which are nonnegative integers that decrease by 1 at the end of each round.
(The move cooldown is only used by the builder bot.)
Actions and movement can only be done when the respective cooldown is 0.

Units may self-destruct at any time.

## Buildings

Buildings are game entities which are immovable. All entities are buildings except builder bots.
In particular, the core and turrets are considered _both a unit and a building_.

## Note: cost scaling

The cost of a building or unit is floor(scale \* base cost) where scale starts at 1.0 and increases with each entity built:
conveyors, splitters, barriers add +1% each; harvesters add +5% each; gunners, launchers add +10% each; builder bots and sentinels add +20% each.
When an entity is destroyed, its contribution is removed. This is to encourage you to be efficient with what you build!

## Core

The core is each team's central building -- if your core is destroyed, you lose the game.
Each team starts with one core.

It has a 2x2 footprint and has a vision radius of 6 and an action radius of sqrt(8) (measured from the nearest tile of its footprint).
Resources must be transferred to the core (via conveyors) to be added to the global pool which is used for building.

The core can spawn up to one builder bot per turn on any tile immediately surrounding its footprint (orthogonally or diagonally adjacent, but not on the footprint itself), which costs one action cooldown.

> **Correction.** The "sqrt(8)" action-radius figures above (both the general one and this Core-specific one) don't match the running engine. Confirmed by enumerating every legal `can_spawn()` tile around a real Core on two different maps with a wide search radius: the actual legal area is exactly the 12-tile ring of squared distance ≤2 from the *nearest* footprint tile — i.e. the plain "orthogonally or diagonally adjacent to the footprint" description in the very next sentence, which is correct. `sqrt(8)` (dist²≤8) would admit a much larger area than what `can_spawn()` actually allows. Don't compute this via `distance_squared()` from a single anchor point either — see [AGENTS.md](agents/agents-md.md) for why that measurement is misleading even though the underlying rule is uniform.

HP: 500

## Builder bot

Builder bots are the only mobile unit -- they are responsible for constructing buildings.

Builder bots have a vision radius of sqrt(20) and an action radius of sqrt(2).

Builder bots can move onto any tile that does not contain another builder bot, provided it is not a wall and either has no building on it, or has a conveyor or splitter belonging to either team.
These are considered _walkable_ tiles.
The direction of the conveyor or splitter does not matter, and neither does the presence of resources on the tile.

A builder bot may move to an adjacent (including diagonal) tile if its move cooldown is 0, increasing it by 1.

If its action cooldown is 0, a builder bot may perform one of the following actions, increasing its action cooldown by 1:

**Build**: build any building or turret on a tile without a building within its action radius.
Only _walkable_ buildings (conveyors and splitters) may be built on a tile which contains a builder bot.

**Attack**: spend 2 Ti to deal 2 damage to the building on the tile it is standing on.

**Heal**: spend 1 Ti to heal all friendly entities on a tile within the builder bot's action radius by 4 HP.
If a friendly builder bot is standing on a friendly building there, both are healed.

Builder bots may also destroy any allied building within its action radius any number of times per turn.

Finally, self-destructing a builder bot deals no damage.

(This section's "Attack: ... the tile it is standing on" and "Heal/Build/Destroy: ... within its action radius" wording is the one place this spec and the public website disagree, and here the spec is right — the website's game-rules-builder-bot page claims all four are orthogonal-adjacent-only, which is wrong in both directions. See [Builder Bot](game-rules/game-rules-builder-bot.md#abilities) for the verified breakdown.)

HP: 40
Base cost: 30 Ti
Scaling contribution: 20%

## Note: resource distribution

Some buildings, such as conveyors, may store, accept and output resources.
Resources are always stored and moved in stacks of 10.

At the end of each round, resources are distributed. Buildings may accept resources, output resources, or both.
**Resources may be outputted to a building belonging to the opposing team.**

The details of resource distribution are given in the per-building descriptions below.

## Conveyors

All conveyors can hold one stack of any resource, and both accept input and produce output.
Basic conveyors and splitters point in one of the cardinal directions.

### Conveyor

Accepts resources from any of its three non-output directions.
Sends its contents in the direction it is pointing if that tile can accept a resource.

Base cost: 3 Ti
Scaling contribution: 1%
HP: 20

### Splitter

Alternates between outputting in three directions: the primary output direction and the two adjacent directions.
Only accepts input from the back.
Prioritises outputting in directions which were used the least recently.

Base cost: 6 Ti
Scaling contribution: 1%
HP: 20

## Harvester

Can be placed on an ore deposit. Outputs one stack of the corresponding resource to an adjacent building every 4 rounds.
The first resource will be outputted immediately on the round the harvester is built.

Prioritises outputting in directions which were used the least recently.

Base cost: 20 Ti
Scaling contribution: 5%
HP: 30

## Barrier

Cheap, takes up space and has high HP.

Base cost: 3 Ti
Scaling contribution: 1%
HP: 30

## Turrets

Every turret except the launcher faces in one of 8 directions.
Ammo must be fed to turrets via conveyors, from any direction apart except the direction the turret is facing.
Diagonal turrets can be fed from all four sides.
A turret can hold up to one stack of one type of resource and only accepts incoming resources when it is completely empty.
If a tile containing both a building and a builder bot is hit, only the builder bot takes damage.

### Gunner

Has a vision radius of sqrt(13). A gunner traces a straight line in the direction it is facing. Empty tiles do not block this line. Walls block the line but are not targetable. Builder bots and buildings are both targetable and blocking.
Gunners can also rotate to any other direction by calling `rotate(direction)`, spending 10 Ti and taking a 1-turn cooldown.

Base cost: 10 Ti
Scaling contribution: 10%
HP: 40
Damage: 10
Reload: 1
Resources per shot: 2

### Sentinel

High range, low damage support turret.
Vision range is sqrt(32). Can hit all tiles within 1 king move (chebyshev distance) of the straight line in the direction it's facing, within vision range.

Base cost: 30 Ti
Scaling contribution: 20%
HP: 30
Damage: 18
Reload: 3
Resources per shot: 10

### Launcher

Can pick up and throw adjacent (including diagonal) builder bots. The target tile must be bot-passable.

Vision range and attack range are both sqrt(26).

Base cost: 20 Ti
Scaling contribution: 10%
HP: 30
Reload: 1

# Reference table

| Entity      | HP  | Base cost | Scale % | Notes                                                            |
| ----------- | --- | --------- | ------- | ---------------------------------------------------------------- |
| Core        | 500 | —         | —       | 2×2 footprint; spawns builder bots                               |
| Builder bot | 40  | 30 Ti     | 20%     | Mobile; can build and heal in action radius, and attack own tile |
| Conveyor    | 20  | 3 Ti      | 1%      | Cardinal direction; 3 inputs, 1 output                           |
| Splitter    | 20  | 6 Ti      | 1%      | 1 input (back), 3 rotating outputs                               |
| Harvester   | 30  | 20 Ti     | 5%      | Outputs a stack of resources every 4 rounds                      |
| Barrier     | 30  | 3 Ti      | 1%      |                                                                  |
| Gunner      | 40  | 10 Ti     | 10%     | Targets occupied tiles in facing direction; can rotate for 10 Ti |
| Sentinel    | 30  | 30 Ti     | 20%     | Line AoE ±1                                                      |
| Launcher    | 30  | 20 Ti     | 10%     | Throws adjacent builder bots                                     |

## Unit stats

| Unit        | Vision r² | Action r²  | Attack r²     | Damage                   | Reload | Ammo/shot |
| ----------- | --------- | ---------- | ------------- | ------------------------ | ------ | --------- |
| Core        | 36        | 8          | —             | —                        | —      | —         |
| Builder bot | 20        | 2          | 0 (own tile)  | 2 (building on own tile) | 1      | 2 Ti      |
| Gunner      | 13        | 2          | 13 (= vision) | 10                       | 1      | 2         |
| Sentinel    | 32        | 2          | 32 (= vision) | 18                       | 3      | 10        |
| Launcher    | 26        | 2 (pickup) | 26 (throw)    | —                        | 1      | —         |

(Core's "Action r²: 8" in this table repeats the sqrt(8) figure corrected above — the real spawn range is the uniform 12-tile adjacency ring, not a distance-8 circle.)

# Appendix: implementation details

## Documentation

API methods are not all covered in this document.
Refer to the documentation for a comprehensive list of all available methods.

## Entity IDs

All entities (buildings and units) in the game have a unique integer ID.
All controller methods which deal with entities will accept and return entity IDs.
Properties of an entity can be queried with the appropriate getter function, for example, `get_hp(id)`.
This API design was chosen for performance reasons, as constructing Python objects to return is very slow.

Resources moving through storage and conveyors also have unique integer IDs.
These are resource stack IDs, not entity IDs, and can be queried with `get_stored_resource_id(id)`.

## Computation limit

Each unit is allocated 10 milliseconds of CPU time per turn.
If your code exceeds the time limit, execution will be interrupted, and the next turn the run() function will be called again.
**Your bot does not resume next turn where it left off.**

To mitigate variance in runtime, each unit has an **extra time buffer** that is 5% of the time limit.
If the bot takes longer than the normal time limit, then the difference is deducted from the extra time buffer.
Once the bot reaches (time limit + extra time) runtime, it is interrupted.
**If the bot takes less time than the time limit, then the difference is refunded to the extra time buffer.**
The extra time buffer is capped at 5% of the normal time limit.

### Testing against the time limit

The local runner will not check for the time limit, as execution time differs by machine.
Instead, we will provide execution servers for you to test your own bots against the time limit on the same machines that run ladder matches.

## Debugging

We provide several debugging utilities.

Printing to stdout (normal `print()`) is captured by the engine and saved to the replay.
You can then view your units' stdout output in the visualiser.
To print to the console, use stderr.

You can also use `draw_indicator_line()` and `draw_indicator_dot()` to draw debugging information on the map itself.
