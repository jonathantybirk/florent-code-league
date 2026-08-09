# Saga — a fourth Builder, measured without the regression that hid it

`snotra_h@6951e03` with `lofn`'s Builder-count change and nothing else.

## Why this exists: an experiment I confounded myself

The live ladder says the top of the field runs a bigger Builder economy than we
do. Decoded from five losing matches, live Builder Bots averaged over the game:

| opponent | them | us | game length |
|---|---|---|---|
| Coreflood | 6.1 | 3.1 | 435 turns |
| O(1) | 5.0 | 3.0 | 300 |
| 0033 | 5.3 | 4.0 | 336 |
| Besvikomat | 5.2 | 3.8 | 392 |
| Big O | 3.6 | 3.7 | 84 |

That is live count, not cumulative builds, so it is not replacement churn. In
every long game we lose, the winner runs between 1.3x and 2.0x our workforce.

`lofn` already tested the obvious response — `_ROLES` from `(1, 1)` to
`(2, 1)`, a fourth opening Builder — and scored **0.494 live against
`snotra_h`'s 0.600**, which reads as a clear refutation. It is not one.
`lofn` descends from `vili`, which carries `RING_AFTER_ECONOMY = True`, and
that flag was later measured at **-8.3 points (+3.1 sd)** on its own. `lofn`
was the fourth Builder *plus* a known 8-point regression, so the Builder was
never measured clean.

This build is that measurement: the same doctrine change applied to
`snotra_h`, which does not have the constant at all.

## The change

`doctrine.py` moves `_ROLES` to `(2, 1)` for RUSH and FORTIFY and adds
`launcher_builder_index()` / `max_opening_builders()`, so the ring Builder's
index and the opening total follow the role table instead of being fixed in
`constants.py`. BLITZ keeps three — a Core six tiles away is decided before a
second miner returns anything. `core.py` and `builder.py` read the derived
values.

## The mechanism fires

Per game, from the suite's own composition metrics:

| | `snotra_h` | `saga` |
|---|---|---|
| Builders spawned | 3.7 | **4.6** |
| Conveyors built | 8.6 | **12.3** |
| Harvesters built | 1.04 | **1.16** |

So the workforce and the infrastructure it lays both move, and `saga` reaches
roughly the Builder count the ladder leaders run.

## Numbers

150 generated maps, both seats, 300 games a cell, baseline in the same run.

| vs | `snotra_h` | `saga` | |
|---|---|---|---|
| `spar_sentinel` (models the opponent class we lose to) | 0.4300 | **0.4367** | +0.007 (+0.2 sd) |
| `undertow` (the one local instrument that has predicted a live ordering) | 0.6000 | **0.5933** | -0.007 (-0.2 sd) |

**Level, on both.** Not queued.

## What it settles

Two things, both worth more than the build.

1. **`lofn`'s live deficit is not the fourth Builder.** With the Builder alone
   measuring within 0.2 sd of zero, the roughly 10 live points `lofn` gave up
   belong to `RING_AFTER_ECONOMY`, which is independently measured at -8.3.
   The confound was mine and it is now removed.
2. **Builder count is a correlate of winning here, not a cause.** We can match
   the leaders' workforce — 4.6 against their 5–6, up from 3.7 — and buy
   nothing with it. Whatever those bots do with five Builders, this
   architecture does not do with four.
