# Game Rules — Overview

Source: https://game.code.florent.vc/docs/game-rules-overview

## Win Condition

To win, a team must **destroy the opponent's Core**. The Core serves as each team's single base unit, and losing it ends the match immediately as a loss.

If both Cores survive until round 1000, the winner is determined by tiebreakers in this order: most titanium collected, then most harvesters, then most titanium stored, then a coin flip.

## The Map

Matches take place on a rectangular grid ranging from **8×8 to 30×30 tiles**. Each tile has one of these environment types:

| Environment | Description |
|---|---|
| `EMPTY` | Traversable by Builder Bots and buildings. |
| `WALL` | Impassable — blocks all movement and line-of-sight. |
| `ORE_TITANIUM` | Ore tile; a Harvester built here generates extra titanium. |

Maps are symmetric and randomly selected from the competition map pool for each match.

## Units and Buildings

Every entity belongs to a Team (A or B) and has an EntityType. Two overlapping categories exist:

- **Units** — the Core, Builder Bots, and turrets (Gunner, Sentinel, Launcher). Each runs its own bot code instance and consumes CPU time per round.
- **Buildings** — all immovable entities: the Core, turrets, conveyors, splitters, harvesters, and barriers.

The Core and turrets function as both units and buildings. Builder Bots are the only units that aren't buildings, while conveyors, splitters, harvesters, and barriers are the only buildings that aren't units.

## Unit Cap

Each team may have at most **50 living units** at any time. Spawning attempts fail when this limit is reached.

## Turn Order

Each round, every living unit executes its `run()` method **in the order it was spawned**. The Core always acts first, before any subsequently-built units. Resource changes from one unit become visible immediately to the next acting unit.

## CPU Time Limit

Each unit has **10 ms of CPU time per round**, plus a banked extra-time buffer of up to 5% of that limit. Unused time accumulates; overuse debits from the bank. Exceeding available time interrupts execution, and the unit doesn't resume—`run()` restarts fresh next round. Use `ct.get_cpu_time_elapsed()` to monitor usage.

## Uncaught Exceptions

CPU-time interruption costs only one round; `run()` continues normally next round. However, an **uncaught exception** is not recoverable in the same way: if `run()` raises anything it doesn't catch, the engine logs the traceback to the replay and **permanently removes that unit from the match**. Wrap risky calls in `try`/`except` blocks if units should survive errors.

## Round Limit

Matches end after **1000 rounds** if neither Core has been destroyed.
