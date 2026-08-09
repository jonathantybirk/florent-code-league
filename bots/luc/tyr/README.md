# Tyr — a second attacker, and why "the ceiling is delivery" does not mean bodies

`snotra_h@6951e03` with `_ROLES` at `(1, 2)` — one miner, **two** attackers.
Measured worse than its parent. Kept for the reason, not the score.

## Why this looked right

300 games against `spar_sentinel` say the grind losses are a healing race we
cannot win by attrition. In the games we lose we deal **more** Core damage than
in the games we win (1408 against 1290) and their Core still ends at 322 of
500 — about **1230 HP healed back**, roughly 4.3 HP a round over a 284-round
game, which is one Builder standing on the Core healing continuously.

The economics are why attrition cannot close it:

| action | cost per point |
|---|---|
| Builder attack | 2 Ti -> 2 dmg = **1.00 Ti/dmg** |
| Gunner / Sentinel | ammo 1:1 -> **~0.57 Ti/dmg** |
| Builder heal | 1 Ti -> 4 HP = **0.25 Ti/HP** |

`constants.py` already knew the shape of the answer. `SIEGE_SENTINEL_TARGET`
was swept to 2, 3 and 4, all scoring 0.581 against a cap of one at 0.590, and
the note concluded: *"the attacker does not survive long enough, or stay
solvent enough, to seat a second one often enough to matter. The ceiling is
delivery, not permission."*

`p.siege_sentinels_built` is per-Builder state, so a second attacker is the one
change that raises **delivery** rather than permission — two bodies, two
counters, two chances to seat a siege Sentinel. `saga` had just tested the
other direction, `(2, 1)`, a second miner, and measured null. `(1, 2)` was the
untested cell.

## Numbers

150 generated maps, both seats, 300 games a cell, baseline re-run in the same
process.

| vs | `snotra_h` | `tyr` | |
|---|---|---|---|
| `spar_sentinel` | 0.4300 | **0.3967** | -0.033 (-0.8 sd) |
| `undertow` | 0.6000 | **0.5467** | -0.053 (-1.3 sd) |

Worse on both, and consistently so.

## What it actually shows

The diagnostic is better than the result. Siege Sentinels seated per game went
**down**, 0.28 to 0.16, with twice the attackers:

| | `snotra_h` | `tyr` |
|---|---|---|
| Builders spawned | 3.7 | 4.1 |
| Siege Sentinels seated | **0.28** | **0.16** |
| Enemy Core HP at end | 218 | 242 |
| Rounds | 385 | 400 |

So "delivery" was never a shortage of bodies. Every Builder levies **+20% on
every price the team pays afterwards** — the largest term in cost scaling — so
a second attacker makes *both* attackers poorer, and the 30 Ti Sentinel neither
can now afford is exactly the thing that was supposed to break the healing
equilibrium. Adding bodies moves the binding constraint the wrong way.

Read together with `saga`: the role table is at a local optimum in **both**
directions. `(2, 1)` is null, `(1, 2)` is -1.3 sd, `(1, 1)` ships.

Anyone returning to the siege problem should attack solvency directly — the
attacker's titanium at the moment it stands next to the enemy Core — and not
the headcount. Not queued.
