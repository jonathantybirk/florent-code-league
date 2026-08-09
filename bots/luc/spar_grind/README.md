# spar_grind — an attempt at a long-game fixture, which did not work

**Not a candidate.** A sparring partner, and a failed one. Do not queue it.

## What it was for

Iterations 164-167 kept running into the same wall: the mechanisms the ladder
decides on operate over hundreds of rounds, and local games end in about a
hundred. `idun`'s compounding economy could only be judged on 33 games,
the turret ceiling only bites past round 200, and turret retirement
(`TURRET_QUIET_ROUNDS = 60`) never fires at all — all four settings scored an
identical 196/300.

So the plan was a fixture that *survives* rather than one that wins: drop the
attacker (`_ROLES` to `(2, 0)`), eight home turrets instead of four, escalate
them three times sooner, never retire one, and four claim slots for a real
economy — with harvester theft and belt cutting off so it never goes hunting.

## It did not lengthen anything

60 maps, both seats, 120 games a cell.

| subject | vs `spar_grind` | median rounds | past 300 |
|---|---|---|---|
| `shr@f1f2bda` | 0.600 | 96 | 7% |
| `snotra_h` | 0.542 | 94 | 8% |
| `vidarr@bbfaa9c` | 0.533 | 101 | 8% |

Balanced — 0.533 against its own parent — and no longer than anything else in
the zoo, which runs 82 to 128 rounds median with 4-8% of games past 300.

## What the attempt established

The short games are not caused by the opponent, and not by the terrain either.
`maps/orerich` matches the live ladder on every dimension checked: ore 46.1 per
1000 tiles against 47.0, area 404 against 439, wall 12.0% against 11.9%, and
Chebyshev Core-to-Core distance **median 12.0 against 12.0**.

The resolution is that live game length is not uniform. Decoded, our own live
matches run **84 turns against Big O and 435 against Coreflood**. Our local
games at 82-105 rounds reproduce the Big O regime faithfully; it is the
*grinding* regime that is missing, and it needs an opponent that can both
survive our attack and out-economy us. Removing this fixture's attacker made it
passive but not durable — we still end it in 101 rounds.

A fixture that reaches round 400 against `vidarr` would have to be genuinely
stronger than anything we have, which is the same problem from the other side.
Kept as a record of the attempt and of the terrain comparison, which is the
part worth reusing.
