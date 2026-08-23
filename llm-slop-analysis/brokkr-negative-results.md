# brokkr: things that measured worse

Kept so they are not re-tried by accident. All figures are the 15-map pool,
both seats, `--tle 0`.

## Defensive Gunners built by menders (2026-08-23)

| | vs hildr | vs steward | our titanium |
|---|---|---|---|
| baseline | 27/30 | 7/30 | 2112 / 2305 |
| + up to 3 Gunners | **17/30** | **5/30** | **808 / 438** |

A Gunner was built by any mender standing near the Core once an enemy Builder
or turret entered the threat ring, facing the nearest threat.

Why it lost, in the order the effects matter:

1. **It spends the action that would have healed.** A mender heals 4 HP a
   round. Building costs it that round, and the next, and the trigger fired
   for every mender until the cap was reached.
2. **Ammunition competes with healing for the same titanium.** Converted
   titanium buys 1.8 HP of enemy damage per Ti through a Gunner and 4 HP of
   our own through a heal. For pure defence, healing strictly dominates -- the
   arithmetic in `defence.py` says so and the measurement agrees.
3. **+20% cost scale each**, which is why our own economy halved rather than
   merely stalling.

The concept is not disproved -- a turret that reliably kills the enemy Builder
before it plants a ring prevents damage rather than repairing it, which is
worth more than either number above. What is disproved is *this* trigger and
*this* placement: a one-tile-wide ray aimed from wherever a mender happened to
stand, at a Builder that moves every round.

Anything that revisits this should pay for itself as **prevention** and be
measured against 27/30 and 7/30, not against zero.

## Three economy changes that did not survive measurement (2026-08-23)

All measured against `e1cb2de` at 90 games a matchup (15 maps, both seats,
3 seats of seeds). The single-sweep numbers that first suggested each of these
were inside the noise band: 30 games is about +-9pp at one sigma, which is
wide enough to "confirm" almost anything. Decisions now use 90.

| | vs hildr | vs steward | total |
|---|---|---|---|
| baseline `e1cb2de` | 78/90 | **28/90** | **106/180** |
| + Builder-time in the deposit score, + rank deposits by Core distance | **81/90** | 22/90 | 103/180 |

**Idle Builders planting Harvesters on a claimed deposit** (measured
separately, 30 games): titanium collected at turn 50 fell 170 -> 136 and final
13949 -> 10456. Planting competes with exploring, and exploring is what finds
the deposit for the lane after this one. Restricting it to a six-tile walk
recovered the win rates but not the economy.

### What the replay actually showed, and why copying it did not work

Bean counters on midgard put two Harvesters down on **turn 3** and had 410
titanium collected by turn 50, against our 160. The mechanism is visible in
`analyze_bean_openings`: two Builders plant Harvesters at Core-distance 3
while two more lay belt outward from the Core, so each lane is worked from
both ends. Laying belt costs two rounds a tile and walking costs one, so a
lane built from both ends finishes in about half the rounds.

The reason our imitation failed is that Bean's deposits *were* at Core-
distance 3. Pairing Builders only pays on a lane short enough that the second
Builder's walk is shorter than the belt it saves. Our maps are the same maps,
so the deposits are there; what we lack is knowing about them early enough to
ring the Core with short lanes before anyone wanders. That points at ore
discovery, not at build order -- and the map-fingerprint idea would answer it
directly, since a known map means every deposit is known on round 0.

## Bean's two-ended lane, tried three ways, all worse (2026-08-23)

Laying belt costs two rounds a tile -- the engine makes moving and acting
mutually exclusive within a round -- while walking costs one. So one Builder
cannot beat `2k` rounds for a `k`-tile lane, and two Builders working from
opposite ends should approach `k`. Bean counters visibly do this: on midgard
two Builders planted Harvesters on turn 3 while two more laid belt outward
from the Core, reaching 410 titanium by turn 50 against our 160.

Economy at the checkpoints, uncontested over the 15-map pool:

| | t25 | t50 | t100 | t200 | final |
|---|---|---|---|---|---|
| baseline | 30 | 180 | 734 | 1956 | 11744 |
| idle Builders plant on a claimed deposit | 19 | 136 | ~ | ~ | 10456 |
| helper takes the far end once deposits run out | 26 | 141 | 526 | 1398 | 8456 |
| fixed pairs, 1 owns / 2 helps, 3 owns / 4 helps | 25 | 144 | 568 | 1334 | 8219 |

**Why it fails here and works for them.** `plan_lane` routes to the *nearest
sink*, and the sink set is "the Core plus every conveyor we own" -- so it
changes as the lane is built. Two Builders recomputing it independently do not
converge on one route; they converge on two, and lay both. The waste is
visible in the ratio: 53 conveyors for 8.7 Harvesters against the baseline's
even worse contested figure of 19-27 per Harvester, where the top ten run 5-6.

A working version needs the route itself shared, not re-derived. The 16-slot
store cannot carry a route cheaply, which is what the GCS module in
`bots/utils/GCS` exists for. That is the prerequisite, and it should be built
before this is attempted a fourth time.
