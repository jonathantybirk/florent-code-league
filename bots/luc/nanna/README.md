# Nanna — the rank-1 shape, as close as this codebase gets

`hlin@a72a7dc` (economy: four claim slots, two miners, claims that recycle) plus
a team-wide turret ceiling priced in cost scale.

## Why this shape

Decoded live replays, composition per game:

| | builders | harvesters | conveyors | gunners | sentinels | launchers |
|---|---|---|---|---|---|---|
| **`sporks` (rank 1, 2107)** | 8.8 | **9.9** | **75.0** | **3.8** | **4.7** | 0.0 |
| `Pivot` (rank 7) | 10.0 | 7.6 | 39.8 | 11.6 | 1.4 | 0.0 |
| **us (1688)** | 4.6 | **2.7** | 24.3 | **22.7** | **0.1** | **2.0** |

Rank 1 fields **8.5 turrets a game; we field 22.8**. At +20 cost scale each that
is 170 points of permanent tax against our 456, and the 286-point difference is
what pays for their 75 conveyors and 9.9 Harvesters.

Every turret cap in this bot is per-Builder, so the team total is the cap times
the Builder count and nothing caps the team. The comms store is full so a shared
headcount is impossible — but `get_scale_percent` is global, exact and free, and
it prices exactly the thing that matters. All ten turret-construction sites go
through the gate.

## Numbers

Three map sets, 156 games a cell:

| vs | on-pool | off-pool | combined | |
|---|---|---|---|---|
| `hlin` (parent) | 0.500 | 0.512 | **79/156 = 0.506 ±0.078** | +0.2 sd |
| `lofn` | 0.500 | 0.548 | 82/156 = 0.526 | +0.6 sd |
| `vili` | 0.625 | 0.652 | 45/71 = 0.634 | +2.3 sd |

Gunners 3.11 → 3.09. **Level with its parent, and it has to be**: a 350 ceiling
cannot bind in a game that builds three turrets. Our own bots never press us the
way the ladder does, so the 22.7-Gunner game exists only live.

## Why it is queued anyway

This is a live experiment with a local safety check, not a local improvement.
The local number exists to show it is not a regression. The mechanism is
supported by the two teams above us that have been decoded — rank 1 and rank 7
both field a third of our turret count — and it is the single largest divergence
between our composition and theirs.
