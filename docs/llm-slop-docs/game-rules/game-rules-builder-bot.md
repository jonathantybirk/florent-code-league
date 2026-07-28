# Game Rules — Builder Bot

Source: https://game.code.florent.vc/docs/game-rules-builder-bot

## Overview

Builder Bots are your team's mobile workforce. They are the only entities that can move freely across the map, and they are responsible for constructing and repairing all buildings.

## Stats

| Property | Value |
|---|---|
| HP | 40 |
| Cost | 30 Ti |
| Vision radius² | 20 |
| Action range | Orthogonally adjacent tile only (Build, Attack, Heal, Destroy — no radius) |
| Move cooldown | 1 round |
| Action cooldown | 1 round |

## Passable terrain

Builder Bots can traverse:

- Any tile with no building on it, as long as it isn't a `WALL` — this includes `EMPTY` tiles and `ORE_TITANIUM` tiles, even before a Harvester is built there
- Tiles with a Conveyor or Splitter building, belonging to either team

Walls (`WALL`), tiles occupied by another Builder Bot, and tiles with any other building (Harvester, Barrier, a Core — including your own — or a turret) are impassable. The Core's 2×2 footprint is never bot-passable, even for its own team.

## Abilities

### Move

Move one tile in one of the 4 cardinal directions — NORTH, SOUTH, EAST, or WEST. Builder Bots cannot move diagonally: `can_move(<diagonal>)` returns `False`, and calling `move(<diagonal>)` raises a `GameError` ("Cannot move diagonally: builder bots move only in cardinal directions (N/E/S/W)"). Moving triggers a move cooldown. A successful move or action blocks the other for the rest of that round — building on a tile and walking onto it now takes two separate rounds.

(This restricts only Builder Bot movement; diagonal directions are still valid for turret facing and building orientation. Vision radius still includes diagonal tiles — Build, Attack, Heal, and Destroy do not, see below.)

> **Correction vs. the official docs.** The published page recommends `Position.cardinal_direction_to(target)` and `Direction.is_cardinal()` for picking a legal move. **Neither method exists** in the installed `fcode` engine — calling either raises `AttributeError` (confirmed by enumerating the real `Position`/`Direction` objects and by direct calls at runtime). `Position` only has `add`, `distance_squared`, and `direction_to`; `Direction` has no `is_cardinal`. Use `direction_to()` (which may return a diagonal) and fall back manually, e.g. try `d, d.rotate_left(), d.rotate_right()` in turn and take the first one `ct.can_move()` allows, or just check membership in `(Direction.NORTH, Direction.SOUTH, Direction.EAST, Direction.WEST)`.

```python
desired = ct.get_position().direction_to(goal)
for d in (desired, desired.rotate_left(), desired.rotate_right()):
    if ct.can_move(d):
        ct.move(d)
        break
```

### Build

Construct a building on any orthogonally adjacent tile — NORTH, SOUTH, EAST, or WEST of the Builder Bot's current position. Diagonal tiles and its own tile are not valid build targets. Each build type has its own `can_build_*` check. Building triggers an action cooldown. A successful move or action blocks the other for the rest of that round — building on a tile and walking onto it now takes two separate rounds.

```python
for d in (Direction.NORTH, Direction.SOUTH, Direction.EAST, Direction.WEST):
    target = ct.get_position().add(d)
    if ct.can_build_gunner(target, Direction.EAST):
        ct.build_gunner(target, Direction.EAST)
        break
```

### Attack

Builder Bots can attack the building on any orthogonally adjacent tile — NORTH, SOUTH, EAST, or WEST of their current position. Diagonal tiles and their own tile are not valid targets. This is mainly useful for sabotage: since Builder Bots can walk onto enemy Conveyor/Splitter tiles, you can walk up next to (or onto, then fire at a neighboring tile of) an enemy's logistics chain and damage it. Costs 2 Ti per hit for 2 damage.

```python
for d in (Direction.NORTH, Direction.SOUTH, Direction.EAST, Direction.WEST):
    target = ct.get_position().add(d)
    if ct.can_fire(target):
        ct.fire(target)
        break
```

### Heal

Builder Bots can heal all friendly entities on any orthogonally adjacent tile — NORTH, SOUTH, EAST, or WEST of their current position. Diagonal tiles and their own tile are not valid targets. Heals 4 HP for 1 Ti — if a friendly Builder Bot is standing on a friendly building on the target tile, both are healed in the same call.

```python
for d in (Direction.NORTH, Direction.SOUTH, Direction.EAST, Direction.WEST):
    target = ct.get_position().add(d)
    if ct.can_heal(target):
        ct.heal(target)
        break
```

### Destroy

Builder Bots can destroy an allied building on any orthogonally adjacent tile — NORTH, SOUTH, EAST, or WEST of their current position. Diagonal tiles and their own tile are not valid targets. Unlike Build, Attack, and Heal, Destroy costs no titanium and does not use the action cooldown — you can destroy any number of allied buildings this way in a single round.

```python
for d in (Direction.NORTH, Direction.SOUTH, Direction.EAST, Direction.WEST):
    target = ct.get_position().add(d)
    if ct.can_destroy(target):
        ct.destroy(target)
        break
```

### Self-destruct

Destroy this Builder Bot. Self-destructing deals zero damage to anything nearby — it's not a weapon, just a way to free up your unit cap or retreat a doomed bot before it can be destroyed.

```python
ct.self_destruct()
```

## Unit cap

Builder Bots count toward the 50-unit team cap. When the cap is reached, the Core cannot spawn additional bots until an existing one is destroyed or self-destructs.
