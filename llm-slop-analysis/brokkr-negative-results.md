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
