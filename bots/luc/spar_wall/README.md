# spar_wall — the long-game fixture, built by inverting a loss

**Not a candidate.** A sparring partner. Do not queue it.

## Why it exists

Every mechanism that acts after round ~150 was untestable all session, because
local games end long before the ladder's do:

| fixture | median rounds | past 300 |
|---|---|---|
| `undertow`, `vanguard`, `spar_sentinel` | 82-105 | 4-8% |
| `spar_grind` (built for this, failed) | 101 | 8% |
| **`spar_wall`** | **138** | **20%** |
| live ladder grinders | 300-435 | — |

`spar_grind` failed because passive is not the same as durable — dropping the
attacker made it harmless, not hard to kill. `spar_wall` is built the other way
round, out of the one measurement that mattered most: an ablation prices
`_heal_core` at **18.8pp**, and widening the mender role to every non-attacker
costs *us* 1.7 sd because it pins miners. That is exactly what makes a bot
difficult to kill, so it is a bad build and a good wall.

## What it is

`nott` with:

- `_ROLES` `(2, 0)` — no attacker;
- **every non-attacker within the leash mends the Core**, the change measured at
  -1.7 sd on our own builds;
- `MENDER_LEASH` 10 -> 20, so more Builders qualify;
- `TURRET_QUIET_ROUNDS` effectively infinite — turrets never retire;
- four claim slots, and no harvester theft or belt cutting, so it never leaves
  home.

## It is also a fair opponent

| | vs `spar_wall` | median rounds |
|---|---|---|
| `nott` | 0.536 | 138 |
| `snotra_h` | 0.478 | 120 |

Balanced within a few points either way, which the previous long-game set
(`maps/longgame`) was not — and unlike that set this is an *opponent*, not a
map selection, so it carries none of the post-hoc selection problem that got
`sunna` withdrawn.

Use it alongside `vanguard` for anything meant to act late. It shares this
lineage's code, so it inherits the sibling-bias caveat: read it for game length
and for late-game mechanism testing, never as evidence about which lineage is
stronger.
