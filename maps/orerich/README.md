# maps/orerich — 150 generated maps matching the live ladder's ore profile

Selected from 9,000 draws of `tools/generate_maps.py --seed 5150` by decoding
each one and keeping those inside the live ladder's terrain profile:

    40 <= ore per 1000 tiles <= 56
    350 <= area <= 520
    5% <= wall fraction <= 20%

| | maps | w x h | area | ore | ore/1k | wall |
|---|---|---|---|---|---|---|
| live ladder (from replays) | 13 | 21 x 20 | 439 | 20.6 | **47.0** | 11.9% |
| **maps/orerich** | 150 | 20 x 21 | 404 | 18.6 | **46.1** | 12.0% |
| maps/offpool_long | 152 | 20 x 20 | 405 | 7.7 | **19.0** | 12.6% |
| maps/ root pool | 36 | 20 x 19 | 398 | 15.7 | 39.4 | 11.5% |

## Why this exists

`maps/offpool_long`, which iterations 156-158 were measured on, carries **40%
of the live ladder's ore density**. That is not a cosmetic difference: on those
maps this bot builds **0.8 Harvesters and 8.6 conveyors** a game, against
**2.0-4.2 Harvesters and 12-29 conveyors** in live games of the same length.
Every mechanism worth testing costs titanium, and they were being tested in a
world with none.

Terrain stats come from `tools/mapstat.py`, which reads `.map26` with the same
protobuf schema `tools/generate_maps.py` writes. Live figures come from replay
grids, which embed the full map.

## What changed when the maps were fixed

The economy lands in the live range (2.4-3.0 Harvesters, 10.4-13.8 conveyors)
and the bot scores better in absolute terms — `snotra_h` goes 0.4300 -> 0.4933
against `spar_sentinel` and 0.6000 -> 0.6767 against `undertow`.

Candidate *orderings* did not reverse. They sharpened, and one changed sign:

| | ore-poor | ore-realistic |
|---|---|---|
| `eir` | -0.1 sd | -0.1 sd |
| `saga` | -0.2 sd (read as null) | **-1.2 / -1.4 sd** |
| `tyr` | -0.8 / -1.3 sd | **-3.1 / -1.3 sd** |

So the hypothesis that these mechanisms measured null because they were starved
of titanium is **refuted**: given a live-realistic economy the extra-Builder
builds get worse, not better. `saga`'s fourth Builder is a real regression that
the poor maps were hiding at zero.

Use this set, not `offpool_long`, for anything whose cost is paid in titanium.
