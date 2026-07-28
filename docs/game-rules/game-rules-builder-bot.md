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
| Action range | Build/Heal/Destroy: action radius²=2 (orthogonal + diagonal, not own tile). Attack: own tile only (r²=0) — see correction below |
| Move cooldown | 1 round |
| Action cooldown | 1 round |

## Passable terrain

Builder Bots can traverse:

- Any tile with no building on it, as long as it isn't a `WALL` — this includes `EMPTY` tiles and `ORE_TITANIUM` tiles, even before a Harvester is built there
- Tiles with a Conveyor or Splitter building, belonging to either team

Walls (`WALL`), tiles occupied by another Builder Bot, and tiles with any other building (Harvester, Barrier, a Core — including your own — or a turret) are impassable. The Core's 2×2 footprint is never bot-passable, even for its own team.

## Abilities

> **Correction vs. the official docs.** The published page says Build, Attack, Heal, and Destroy are all restricted to an orthogonally adjacent tile (never diagonal, never the Builder Bot's own tile). **Verified directly against the running engine and this is wrong for three of the four** — confirmed with a probe bot that builds a real target next to itself and checks each `can_*` call in every direction, including diagonals and its own tile:
> - **Build, Heal, and Destroy** all work within the Builder Bot's full action radius (r²=2) — **diagonal tiles are legal**, not just the four cardinal ones. Heal also works on the Builder Bot's own tile.
> - **Attack (`fire`) is the one that's actually more restrictive than documented**: it only ever works on the tile the Builder Bot is **currently standing on** (r²=0) — not an adjacent tile at all, diagonal or otherwise. To damage a building, you have to walk onto it (Conveyor/Splitter tiles are walkable by either team) and fire at your own position.
>
> This matches the engine's own bundled [engine spec](../engine-spec.md) (`ct.can_fire(pos)` where `pos == ct.get_position()`), which the public website's "orthogonally adjacent, never own tile" wording contradicts for Attack specifically — even that bundled spec isn't infallible elsewhere (see its own correction note), so this was checked directly against the running engine, not just against a second document.

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

Construct a building on any tile within action radius (r²≤2) of the Builder Bot's current position — all 8 surrounding directions, including diagonals — but never its own tile. Each build type has its own `can_build_*` check. Building triggers an action cooldown. A successful move or action blocks the other for the rest of that round — building on a tile and walking onto it now takes two separate rounds.

```python
for d in Direction:
    if d == Direction.CENTRE:
        continue
    target = ct.get_position().add(d)
    if ct.can_build_gunner(target, Direction.EAST):
        ct.build_gunner(target, Direction.EAST)
        break
```

### Attack

Builder Bots can attack the building on **the tile they are currently standing on** — not an adjacent tile at all, cardinal or diagonal. Since Builder Bots can walk onto Conveyor/Splitter tiles belonging to either team, this is how sabotage works in practice: walk onto an enemy's logistics chain and fire on your own position to damage whatever's under you. Costs 2 Ti per hit for 2 damage.

```python
pos = ct.get_position()
if ct.can_fire(pos):
    ct.fire(pos)
```

### Heal

Builder Bots can heal all friendly entities on any tile within action radius (r²≤2), including diagonals and their own tile (e.g. a Builder Bot standing on a damaged friendly Conveyor can heal itself and it in the same call). Heals 4 HP for 1 Ti.

```python
for d in Direction:
    target = ct.get_position().add(d)  # includes CENTRE (own tile) via add()
    if ct.can_heal(target):
        ct.heal(target)
        break
```

### Destroy

Builder Bots can destroy an allied building on any tile within action radius (r²≤2), including diagonals. Unlike Build, Attack, and Heal, Destroy costs no titanium and does not use the action cooldown — you can destroy any number of allied buildings this way in a single round.

```python
for d in Direction:
    if d == Direction.CENTRE:
        continue
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
