# maps/longgame — the 15 maps that reliably produce long games

Selected empirically, not generated: every `maps/orerich` map with at least 20
recorded games and a **median length of 140 rounds or more**, taken from 36,240
games across iterations 156-174.

| set | median rounds | past 200 | past 300 |
|---|---|---|---|
| `maps/orerich` (all 150) | 96 | 13% | 8% |
| **`maps/longgame` (15)** | **177** | **42%** | **32%** |
| live ladder | 300-435 typical | — | — |

Measured in use: a `vanguard` duel on this set runs a median of **184 rounds
with 40% past 300**, against 96 and 8% on the full set.

## What it is for, and what it did not fix

Iteration 174 found six tuning constants that change **zero games** out of 120
— `SIEGE_STALL_ROUNDS`, `REPAIR_ATTEMPT_LIMIT`, `PATH_SAFETY_MARGIN`,
`HARVESTER_RECHECK_ROUNDS`, and near-zero for `MENDER_LEASH` and
`ECON_EXPAND_RESERVE`. The explanation offered there was game length: these
govern states a hundred-round game never reaches.

**That explanation is wrong.** Re-run on this set, at a 184-round median with
40% of games past 300, all six are *still* identical in 30 of 30 games. The
cause is opponent behaviour, not duration: `vanguard` never cuts our belts, so
`REPAIR_ATTEMPT_LIMIT` cannot fire; it never threatens our routes, so
`PATH_SAFETY_MARGIN` never binds; our siege never stalls, so
`SIEGE_STALL_ROUNDS` never trips. Testing those constants needs an opponent
that does those things, and no bot available does.

## The finding that survived

Our win rate against `vanguard` falls sharply with length — about **0.68 under
200 rounds and 0.52 past 300**, measured on 1,800 strictly paired cells. The
long game is where this lineage is weakest, which matches the ladder, where our
losses to Coreflood and Besvikomat run 392-435 rounds.

Use this set for anything meant to act late. Pair it with `maps/orerich` and
`maps/orerich2` rather than replacing them: it is deliberately a biased sample.
