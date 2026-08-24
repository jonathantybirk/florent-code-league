# Var — the right mechanism behind a detector that does not work

`nott` plus a `FAR_ORE` doctrine bit: two economy Builders instead of one when
the nearest ore the Core can see at round 0 is more than three tiles away.
**The mechanism is real and significant; the detector is not.** Not queued.

## The mechanism, which is solid

A second economy Builder is neither good nor bad in general — it depends on how
far the ore is:

| map set | nearest ore to a Core | second miner |
|---|---|---|
| `maps/orerich` (150) | median **2** tiles | **-1.2 sd** (`saga`) |
| `maps/longgame` (15) | median **4** tiles | **+2.2 sd** |

On the fifteen maps that reliably produce 200-400 round games, over **240
strictly paired cells against eight opponents**, the second miner takes the win
rate from 0.725 to **0.808** and Harvesters from 1.23 to 1.77. McNemar on the
discordant pairs: 34 cells won that the one-miner build loses against 14 the
other way, **z = +2.89**.

That regime matters. Long games are where this lineage is weakest — about 0.52
past 300 rounds against 0.68 under 200 — and it is where the ladder decides:
our live losses to Coreflood and Besvikomat run 435 and 392 rounds. And the
cause of the long games is the same distant ore: on those maps we build 1.23
Harvesters, and win rate by Harvester count is 0.298 / 0.561 / 0.770 / 0.761
for 0 / 1 / 2 / 3+.

## The detector, which is not

`FAR_ORE` is set when the nearest ore inside the Core's vision (r^2 = 36) is
more than `FAR_ORE_DISTANCE = 3` tiles away. Measured against the two regimes it
is barely better than a coin:

| threshold | fires on long-game sides | fires on `orerich` sides |
|---|---|---|
| > 2 | 80% | 42% |
| **> 3** | **57%** | **21%** |
| > 4 | 27% | 8% |

No cut separates them. So the conditional build inherits little of the benefit
and some of the cost:

| set | `nott` | `var` | `neco` (unconditional) |
|---|---|---|---|
| `maps/longgame`, 150 cells | 0.673 | 0.687 (+0.2 sd) | **0.767 (+1.8 sd)** |
| `maps/orerich`, 600 cells | 0.712 | 0.698 (-0.5 sd) | — |

`var` fires on only 57% of the maps where the extra miner pays and on 21% where
it costs, which is exactly what those two rows say.

## What to do with this

The finding is worth keeping and the implementation is worth keeping — the
`FAR_ORE` bit rides in the doctrine word, composes with all three openings,
excludes BLITZ, and the accessors are verified. What is missing is a round-0
signal that actually identifies the regime. Nearest-visible-ore distance is not
it. Candidates: ore *count* inside the Core's vision rather than distance,
walking distance rather than Chebyshev (walls are what make ore expensive), or
total ore within some larger radius.

Anyone picking this up should keep `maps/longgame` and `maps/orerich` as the
two regimes and require a detector that fires on most of the first and few of
the second before rebuilding the bot around it.
