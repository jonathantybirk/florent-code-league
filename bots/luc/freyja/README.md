# Freyja — the economy was capped at two deposits

`vili@419bf08` with four deposit-claim slots instead of two.

## The defect

`_pick` commits a Builder to a deposit by taking a claim slot from
`CLAIM_SLOTS`. If every slot is occupied it falls out of the loop having set no
task at all, and the Builder re-picks next round, and the round after that.

`CLAIM_SLOTS = (1, 8)` — **two**. At most two deposits can be under
construction at any moment, however many Builders exist.

Instrumented on a build with the economy constants opened right up (expansion
from round 8 instead of 120, cooldown 4, Builder cap 14, late Builders mining):

    PICK calls by builder index:  idx=0: 2   idx=3: 44   idx=4: 3
    HARV built: 1, round 14

One expansion Builder called `_pick` forty-four times in a game that produced a
single Harvester. Builders rose from 3.6 to 5.76 and Harvesters stayed at 1.61.
The constants were never the binding constraint; the slots were.

This is the "2.3-Harvester ceiling" that three earlier builds failed to break
(`sif`, `saga`, `spar_macro`) — not an equilibrium, just two slots.

## Why it matters, from live replays

Decoded 20 games against the four teams that beat us on the ladder:

| | builders | harvesters | conveyors | gunners | launchers |
|---|---|---|---|---|---|
| **us** | 4.6 | **2.7** | 24.3 | 22.7 | **2.0** |
| Pivot | 10.0 | 7.6 | 39.8 | 11.6 | 0.0 |
| Besvikomat | 13.4 | 6.8 | 59.4 | 82.4 | 0.8 |
| Big O | 13.6 | 6.0 | 34.2 | 3.6 | 0.0 |
| I Stone | 8.6 | 4.4 | 25.2 | 1.6 | 0.0 |

Their Gunner counts span 1.6 to 82.4, so turrets are not what they share. Two
concurrent deposits cannot produce 4.4-7.6 Harvesters however many Builders we
spawn.

## The trade

All 16 store slots were allocated. This buys claim slots with launch-request
slots (`LAUNCH_REQUEST_SLOTS` 2..7 → 2..5), the ferry protocol — the one
mechanic on that table that **no team above us builds at all**. Four launch
slots remain against 3.6 Builders.

## Numbers, and they are honest

Harvesters **1.50 → 2.02**, conveyors 6.10 → 9.36. The mechanism does what it
says.

Head to head against `vili` over **198 games on four map sets** (21 official,
42 generated oblong, 21 generated shape-matched):

| | | |
|---|---|---|
| official + offpool | 59/114 | 0.518 |
| offpool2 + square | 42/84 | 0.500 |
| **total** | **101/198** | **0.510 ±0.070** |

**0.3 sd. That is not a measured improvement.** It is shipped on mechanism
rather than on margin: it removes a structural cap the live replays identify as
the single largest gap to the top of the ladder, it is non-negative on every
map set tried, and the ladder is the only held-out measurement this project
has.

It also does not finish the job. 2.02 Harvesters is still far below the
4.4-7.6 the teams above us run, so four slots are probably binding in turn.

CPU and determinism unchanged from `vili` (constants-only change).
