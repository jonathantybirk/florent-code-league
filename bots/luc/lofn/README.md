# Lofn — the second miner works once there is room to hold it

`freyja@6a8a5f7` plus a second opening miner. Neither half is new; the
combination is, and it is worth more than either.

## Why it failed before

`saga` added a second opening miner in iteration 51 and measured **0.567**
against `vili`'s 0.657. It looked like a clean refutation: more economy, fewer
wins.

It was not the miner that failed. `CLAIM_SLOTS` was `(1, 8)` — **two** — and a
Builder that cannot take a claim slot in `_pick` silently sets no task and
re-picks next round, forever. A second miner with nowhere to commit is a Builder
that walks, costs +20% cost scale, and mines nothing. `freyja` raised the cap to
four; this build then adds the miner that the cap was blocking.

## The evidence it was chasing

Decoded live replays of the four teams that beat us, 20 games:

| | builders | harvesters | conveyors | gunners |
|---|---|---|---|---|
| **us** | 4.6 | **2.7** | 24.3 | 22.7 |
| Pivot | 10.0 | 7.6 | 39.8 | 11.6 |
| Besvikomat | 13.4 | 6.8 | 59.4 | 82.4 |
| Big O | 13.6 | 6.0 | 34.2 | 3.6 |
| I Stone | 8.6 | 4.4 | 25.2 | 1.6 |

Their Gunner counts span 1.6 to 82.4, so turrets are not the shared factor.
Economy is.

## Numbers

Three map sets — 21 official, 21 generated oblong, 21 generated shape-matched —
both seats, 156 games a cell.

| vs | on-pool | off-pool | combined | |
|---|---|---|---|---|
| `vili` | 0.556 | 0.595 | **90/156 = 0.577 ±0.078** | +1.9 sd |
| `freyja` (parent) | 0.528 | 0.571 | **86/156 = 0.551 ±0.078** | +1.3 sd |
| `steward_hardened_reinforced` (live) | 0.688 | 0.414* | **45/77 = 0.584 ±0.110** | +1.5 sd |

*29 games only.

**It is stronger off-pool than on-pool**, which is the opposite of the pattern
that made every earlier "improvement" evaporate: the whole lineage spans
0.262-0.667 on the official maps and collapses into one interval on generated
ones, because the official pool is also the tuning pool.

Composition: Harvesters **1.50 → 2.02 (`freyja`) → 2.73**, conveyors 6.10 →
9.36 → 17.37, Builders 3.67 → 4.46. That is our live-measured 2.7 Harvesters
finally reproduced *internally*, and the first build of this line to reach it.

## Honest limits

2.73 is still under the 4.4-7.6 the teams above us run, so this does not close
the gap — it opens it by one miner. Three opponents at +1.3 to +1.9 sd is
suggestive rather than settled; no single cell clears 2 sd.

CPU: worst turn 4,232 us of 10,000, zero over. Deterministic across three runs.
