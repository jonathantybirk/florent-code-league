# Eir — match the mender radius to the reach, on a base that isolates it

`snotra_h@6951e03` with `BUILDER_PRIORITY_RADIUS_SQ` at 32 instead of 20. One
constant, one file. Measured level; kept for the measurement.

## The defect is real and was already documented

A Sentinel's first targeting rule prefers a Builder Bot over the Core, for the
reason `sentinel.py` states plainly: *"shooting a Core past a mender is 10
ammunition a shot spent to lose slowly, and shooting the mender ends it."*
That rule is gated at `r^2 <= 20`, but a Sentinel **reaches r^2 = 32**, and a
siege Sentinel is deliberately seated at the far end of its reach where the
Core's own defenders cannot answer it. The mender standing on the Core is
therefore at about 32 — outside the radius — so the rule is skipped and the
Sentinel shoots the Core, which is exactly the failure its own comment warns
about.

Two independent measurements agree:

- **Live replays** (recorded in `frigg`): two of five games lost to Pivot ended
  with our own Core untouched while we dealt **2828 and 4123 damage** to theirs
  without killing a 500-HP Core, both running the full 1000 rounds and both
  lost on the titanium tiebreak.
- **300 local games** against `spar_sentinel`: the games we *lose* are the ones
  where we deal **more** Core damage than the ones we win (1408 against 1290),
  their Core still ending at 322 of 500 — about **1230 HP healed back**, ~4.3 a
  round, one mender working uninterrupted.

`frigg` already carried this constant at 32, but on the `lofn` lineage, so it
came bundled with `RING_AFTER_ECONOMY` (independently -8.3 points) and
`saga`'s `(2, 1)` role table (independently null). This build is the constant
alone on a clean base.

## Numbers

150 generated maps, both seats, 300 games a cell.

| vs | `snotra_h` | `eir` | |
|---|---|---|---|
| `spar_sentinel` | 0.4300 | 0.4267 | -0.003 (-0.1 sd) |
| `undertow` | 0.6000 | 0.6000 | 0.000 |

Level. Core damage dealt 1358 -> 1347, their Core HP at end 218 -> 216: the
siege outcome does not move either.

## Why a correct change measures nothing

Because it almost never executes. Split by how many siege Sentinels the game
actually seated:

| siege Sentinels seated | win rate | games |
|---|---|---|
| 0 | 0.424 +-0.045 | **458** |
| 1 | 0.458 +-0.090 | 118 |
| 2 | 0.455 +-0.208 | 22 |
| 3+ | 0.000 | 2 |

**76% of games seat no siege Sentinel at all**, so in three games out of four
there is no Sentinel for this radius to govern. And where one does exist it is
worth about +3.4pp against a +-9pp interval — not nothing, not resolvable here.

That closes the siege line rather than opening it. Raising *permission* was
swept and measured null (`SIEGE_SENTINEL_TARGET` at 2, 3, 4 all 0.581 against
0.590 at one). Raising *delivery* by adding a second attacker measured -1.3 sd
(`tyr`), because each Builder levies +20% on every later price and both
attackers end up too poor to seat the 30 Ti turret. Fixing the *targeting* is
inert because the turret usually does not exist.

Keep the constant anyway if this base is ever built on: it is free when no
Builder is on the line, since the rule only fires on a target the Sentinel
could already shoot, and the live-replay evidence for the defect is sound.
Not queued.
