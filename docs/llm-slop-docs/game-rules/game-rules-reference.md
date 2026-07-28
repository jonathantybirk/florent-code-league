# Game Rules — Reference

Source: https://game.code.florent.vc/docs/game-rules-reference

## Entity Stats

### Units

| Entity | HP | Cost (Ti) | Vision radius² | Action radius² | Spawn radius² | Move cooldown |
|--------|----|-----------|----|----|----|---|
| Core | 500 | — | 36 | — | 2 (adjacent ring) | — |
| Builder Bot | 40 | 30 | 20 | Orthogonally adjacent only | — | 1 |

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

Base costs scale with team entity count (see Cost scaling section).

## Game Constants

| Constant | Value |
|----------|-------|
| Round limit | 1000 |
| Unit cap (per team) | 50 (includes the Core) |
| CPU time limit (per unit per round) | 10 ms (+5% banked extra time) |
| Passive titanium income | 10 Ti / 4 rounds |
| Global Communication Store slots | 16 |
| Map size range | 8×8 – 30×30 |
| Series length | Best of 5 |

## Cost Scaling

Building costs multiply by a scale factor: `effective_cost = base_cost × scale_factor`

Starting at 1.0, the factor increases additively per entity built: conveyors/splitters/barriers (+1%), harvesters (+5%), gunners/launchers (+10%), builder bots/sentinels (+20% each). Removals decrease the factor accordingly.
