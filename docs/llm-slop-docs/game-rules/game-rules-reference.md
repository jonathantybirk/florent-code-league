# Game Rules — Reference

Source: https://game.code.florent.vc/docs/game-rules-reference

## Entity stats

### Units

| Entity | HP | Cost (Ti) | Vision radius² | Action radius² | Spawn radius² | Move cooldown |
|--------|----|-----------|----|----|----|---|
| Core | 500 | — | 36 | — | 2 (adjacent ring) | — |
| Builder Bot | 40 | 30 | 20 | — (Build/Attack/Heal/Destroy are all orthogonally adjacent only) | — | 1 |

### Turrets

| Entity | HP | Cost (Ti) | Vision radius² | Attack radius² | Damage | Ammo/shot | Reload |
|--------|----|-----------|----|----|----|----|----|
| Gunner | 40 | 10 | 13 | 13 | 10 | 2 | 1 |
| Sentinel | 30 | 30 | 32 | 32 | 18 | 10 | 3 |
| Launcher | 30 | 20 | 26 | 26 (throw) / 2 (pickup) | — | — | 1 |

### Infrastructure

| Entity | HP | Cost (Ti) | Blocks movement | Blocks LOS |
|--------|----|-----------|----|---|
| Harvester | 30 | 20 (base) | No | No |
| Barrier | 30 | 3 (base) | Yes | Yes |
| Basic Conveyor | 20 | 3 (base) | No | No |
| Splitter | 20 | 6 (base) | No | No |

All costs above are base costs — the effective cost scales up with the number of entities your team has built (see [Cost scaling](game-rules-resources.md#cost-scaling)).

## Game constants

| Constant | Value |
|----------|-------|
| Round limit | 1000 |
| Unit cap (per team) | 50 (includes the Core) |
| CPU time limit (per unit per round) | 10 ms (+5% banked extra time) |
| Passive titanium income | 10 Ti / 4 rounds |
| Global Communication Store slots | 16 |
| Map size range | 8×8 – 30×30 |
| Series length | Best of 5 |

## Cost scaling

All build costs are multiplied by the current scale factor:

```
effective_cost = base_cost × scale_factor
```

The scale factor starts at 1.0 and increases additively as entities are built (conveyor/splitter/barrier +1%, harvester +5%, gunner/launcher +10%, builder bot/sentinel +20% each — removed again on destruction), not as a function of elapsed rounds. Use `ct.get_scale_percent()` to read the current value (as a percentage — see the [correction note](game-rules-resources.md#cost-scaling)). Use `ct.get_<entity>_cost()` methods to read the already-scaled current cost of any specific build action.
