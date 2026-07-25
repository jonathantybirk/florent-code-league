# Game Rules — Harvester

Source: https://game.code.florent.vc/docs/game-rules-harvester

## Overview

Harvesters are buildings that generate passive titanium income. A Builder Bot constructs these structures on `ORE_TITANIUM` tiles, after which they automatically produce titanium to adjacent buildings without further bot involvement. These facilities don't count toward unit caps and require no CPU resources.

## Stats

| Property | Value |
|----------|-------|
| HP | 30 |
| Base cost | 20 Ti (scales +5% per Harvester built) |
| Output | 10 Ti every 4 rounds |
| Blocks movement | No |
| Blocks LOS | No |

## Output Behavior

Every 4 rounds, a Harvester outputs one stack (10 Ti) to an adjacent building, prioritizing whichever of its 4 cardinal output directions was used least recently. This follows the same round-robin distribution pattern as Splitters. Production begins immediately upon construction rather than after a full 4-round delay.

## Building

Harvesters can only be placed on `ORE_TITANIUM` tiles:

```python
if ct.get_tile_env(pos) == Environment.ORE_TITANIUM:
    if ct.can_build_harvester(pos):
        ct.build_harvester(pos)
```

## Notes

- These structures don't count toward unit capacity limits.
- Output operates independently from bot CPU budgets.
- Use `ct.destroy()` to remove Harvesters no longer needed.
