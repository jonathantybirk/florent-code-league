# Game Rules — Core

Source: https://game.code.florent.vc/docs/game-rules-core

## Overview

The Core is a large, stationary base unit. Each team begins the match with exactly one Core placed on the map. It cannot be moved or rebuilt — if it is destroyed, the match is immediately lost.

## Stats

| Property | Value |
|---|---|
| HP | 500 |
| Footprint | 2×2 tiles |
| Vision radius² | 36 |
| Spawn range² | 2 (adjacent ring, including diagonals) |

## Abilities

### Spawn Builder Bot

The Core can spawn a Builder Bot on any passable tile within its spawn range — a tile orthogonally or diagonally adjacent to its 2×2 footprint (not the footprint itself).

```python
if etype == EntityType.CORE:
    for pos in ct.get_nearby_tiles(dist_sq=2):
        if ct.can_spawn(pos):
            ct.spawn_builder(pos)
            break
```

Spawning costs titanium (see `ct.get_builder_bot_cost()`). The new bot becomes active in the same round it is spawned.

### Convert ammunition

> **Correction vs. the official docs.** The published page describes the Core converting team titanium into a shared ammunition pool via `convert_ammo()` / `can_convert_ammo()` / `get_global_ammo()`. **None of these methods exist** in the installed `fcode` engine (verified by enumerating the real `Controller` object at runtime — calling any of them raises `AttributeError`). There is no team-wide ammo balance and no Core conversion step. See [Turrets](game-rules-turrets.md) for how ammo actually works.

Gunners and Sentinels consume ammo (titanium) held **inside each individual turret**, delivered by conveyors. The Core has no special role in supplying it beyond being the start of your logistics chain, same as any other titanium expense. Check a turret's own supply with `ct.get_ammo_amount()` / `ct.get_ammo_type()`.

## Notes

- The Core counts toward the 50-unit cap, like every other unit.
- The Core has no movement or attack actions — its only active ability is spawning Builder Bots.
- Passive income (10 titanium every 4 rounds) is granted to each team directly and isn't tied to the Core or any other unit.
