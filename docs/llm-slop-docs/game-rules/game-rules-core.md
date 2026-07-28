# Game Rules — Core

Source: https://game.code.florent.vc/docs/game-rules-core

## Overview

The **Core** is a large, stationary base unit. Each team begins the match with exactly one Core placed on the map. It cannot be moved or rebuilt — if it is destroyed, the match is immediately lost.

## Stats

| Property | Value |
|----------|-------|
| HP | 500 |
| Footprint | 2×2 tiles |
| Vision radius² | 36 |
| Spawn range² | 2 (adjacent ring, including diagonals) |

## Abilities

### Spawn Builder Bot

The Core can deploy a Builder Bot on any passable tile within its spawn range—meaning tiles orthogonally or diagonally adjacent to its 2×2 footprint, but not the footprint itself.

```python
if etype == EntityType.CORE:
    for pos in ct.get_nearby_tiles(dist_sq=2):
        if ct.can_spawn(pos):
            ct.spawn_builder(pos)
            break
```

Spawning costs titanium (see `ct.get_builder_bot_cost()`). The new bot becomes active in the same round it is spawned.

### Ammunition (correction — the Core does NOT convert ammo)

> **Correction vs. the official docs.** The published page claims the Core converts titanium into ammunition at a 1:1 rate via `ct.convert_ammo()` / `ct.can_convert_ammo()`, and that turrets draw from a shared team pool read with `ct.get_global_ammo()`. **None of these methods exist** in the installed `fcode` engine (verified in `fcode/_types.py` and the compiled engine). There is no titanium→ammo conversion mechanic at all.
>
> How ammo actually works: ammo **is titanium** stored **per-turret**, which you **deliver to each turret via conveyors** — there is no team-wide ammo balance and no separate conversion step. See [Turrets](game-rules-turrets.md) for the real mechanics and the per-turret methods `get_ammo_amount()` / `get_ammo_type()`.

The Core therefore has only one active ability: **spawning Builder Bots** (above). It plays no role in supplying ammo.

## Notes

- The Core **counts toward** the 50-unit cap, like every other unit.
- The Core lacks movement or attack actions; its only active ability is spawning Builder Bots.
- Passive income distributes 10 titanium every 4 rounds to each team independently.
