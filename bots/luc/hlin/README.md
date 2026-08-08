# Hlin — the claim slots leaked

`lofn@86287ec` plus four lines: a Builder that can see a finished Harvester on a
claimed tile clears the claim.

## The defect

A claim slot is released by `_done` and `_abandon_task`, and both match on the
**holder's own** `p.task`. A Builder that dies holding a claim leaks it
permanently, and no other Builder can ever take that deposit again.

Instrumented over three games:

    _pick succeeded            22 times
    _pick "no free slot"      228 times
    slots held when blocked   [177, 58, 410, 249] -- identical every time

Four values, frozen for the rest of every game. Meanwhile the miners sat in
`scout`: a phase histogram of miner turns is **43% goto, 38% scout, 19%
prelay** — better than a third of all miner time spent asking for work that
could not be granted.

That is the real ceiling, and it explains why raising the count did not fix it.
`freyja` went 2 slots → 4 and bought exactly two more Harvesters before the
permanent lock (1.50 → 2.02 → 2.73); the slots still leaked, just later.

After the fix: **228 failures → 5, 22 successes → 34.**

## Numbers

Three map sets, 156 games a cell:

| vs | on-pool | off-pool | combined | |
|---|---|---|---|---|
| `lofn` (parent) | 0.500 | 0.548 | **82/156 = 0.526 ±0.078** | +0.6 sd |
| `vili` | 0.569 | 0.595 | 91/156 = 0.583 | +2.1 sd |
| `steward_hardened_reinforced` | 0.678 | 0.415 | 57/100 = 0.570 | +1.4 sd |

## What it does not do

**Harvesters do not move: 2.75, against `lofn`'s 2.73.** Picks went up by half
and production did not follow, so the bottleneck simply moved one step later —
34 granted tasks produce 2.75 Harvesters, a conversion rate of about one in
twelve. The miners now get work and abandon it before it is built.

So this is shipped as a bug fix with a positive direction on both pools, not as
an economy gain. The economy gain is still waiting behind whatever discards
eleven of every twelve granted tasks, and that is the next thing to instrument.
