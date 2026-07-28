# Game Rules — Conveyors

Source: https://game.code.florent.vc/docs/game-rules-conveyors

## Overview

Conveyors function as infrastructure buildings that automatically transport resources across tiles each round without requiring CPU resources. They facilitate the creation of supply chains from ore locations to your Core.

Resources travel along a conveyor chain in **stacks of 10 titanium** per step per round.

## Conveyor Types

### Basic Conveyor

A basic conveyor moves resources one tile in a predetermined direction. It accepts a stack from any of its three non-output (cardinal) sides and sends it onward in the direction it's pointing.

| Property | Value |
|----------|-------|
| Base cost | 3 Ti (scales +1% per conveyor built) |
| Direction | Set at build time |
| Holds | 1 stack (10 Ti) at a time |

```python
ct.build_conveyor(pos, Direction.EAST)
```

### Splitter

A splitter offers three possible output directions—its facing direction plus two adjacent directions (all cardinal directions except directly behind). It has **exactly one input side**: it only **accepts** input from the back (the single tile opposite its facing direction). Feeding a splitter from any other side does nothing — resources must enter through the back.

Rather than dividing stacks, each round it sends its entire held stack (10 Ti) to whichever of its three outputs was used **least recently**, rotating through all three over time.

| Property | Value |
|----------|-------|
| Base cost | 6 Ti (scales +1% per splitter built) |
| Accepts from | Back only (single input side — the tile opposite its facing direction) |
| Outputs to | 3 directions (facing + two adjacent), least-recently-used first |
| Holds | 1 stack (10 Ti) at a time |

Splitters prove valuable for directing a single harvester chain along multiple return paths to your Core.

## Building Conveyors

```python
# Check and build a conveyor at pos pointing East
if ct.can_build_conveyor(pos, Direction.EAST):
    ct.build_conveyor(pos, Direction.EAST)
```

## Destroying Conveyors

Use `ct.destroy()` to remove unneeded conveyors. This action returns any resources currently in transit on that tile to your team's balance.

```python
if ct.can_destroy(pos):
    ct.destroy(pos)
```
