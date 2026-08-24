# Ran — the mender fix on the base that actually seats Sentinels

`vidarr@bbfaa9c` with `BUILDER_PRIORITY_RADIUS_SQ` at 32 instead of 20. One
constant, one file.

## Why this base, and not `snotra_h`

Because `snotra_h` is not our best build and never was. Live, on 2026-08-09:

| build | rated games | live elo |
|---|---|---|
| `vidarr@bbfaa9c` | 20 | **1777** |
| `steward_hardened_reinforced@f1f2bda` | 86 | 1776 |
| `steward@e55aab5` (holds the seat) | 169 | 1771 |
| `snotra_h@6951e03` | 0 | 1749 |

`vidarr` also has the composition that matches the meta the ladder is actually
winning with — most economy, fewest Gunners, most Sentinels:

| | builders | gunners | sentinels | harvesters | conveyors |
|---|---|---|---|---|---|
| `vidarr@bbfaa9c` | **4.70** | 2.28 | **0.83** | **3.45** | **20.28** |
| `snotra_h` | 4.23 | 3.25 | 0.43 | 3.00 | 13.79 |

## The change

A Sentinel's first targeting rule prefers a Builder over the Core — *"shooting
a Core past a mender is 10 ammunition a shot spent to lose slowly, and shooting
the mender ends it"* — but the rule is gated at `r^2 <= 20` while a Sentinel
reaches **32**, and a siege Sentinel is seated at the far end of that reach.
The mender on the Core therefore sits outside the radius and the Sentinel
shoots the Core instead.

Evidence for the defect is independent of any local panel: live replays show
two of five games lost to Pivot ending with our own Core untouched while we
dealt **2828 and 4123 damage** to theirs without killing a 500-HP Core, both
lost on the round-1000 tiebreak.

`eir` applied the same constant to `snotra_h` and measured inert, because that
base seats 0.32 Sentinels a game and three games in four have none at all.
This base seats 0.83 — more than twice the opportunity.

## Numbers

150 ore-realistic maps (`maps/orerich`), both seats, 300 games a cell, against
its own base.

| vs | `vidarr@bbfaa9c` | `ran` | | games identical |
|---|---|---|---|---|
| `undertow` (external code) | 0.6533 | 0.6500 | -0.003 (-0.1 sd) | 278/300 |
| `spar_sentinel` | 0.4333 | 0.4300 | -0.003 (-0.1 sd) | 294/300 |

**Level.** Twice the Sentinels was still not enough: the fix alters 22 games in
300 against `undertow` and 6 against `spar_sentinel`, and nets zero. Together
with `eir` that is the same constant measured inert on two different lineages,
which is as close to settled as this gets locally.

## Why it is queued anyway

Not because it beat anything — it did not, and the log says so. Two reasons
that do not depend on the local panel:

1. `vidarr@bbfaa9c` is our **highest live estimate on the thinnest sample** —
   1777 over 45 games, against `e55aab5`'s 1771 over 289. That difference is
   noise and the only way to resolve it is live games on that composition.
   `vidarr@bbfaa9c` cannot be re-queued (the farm dedupes on `name@commit`,
   ignoring the round count, and it has been consumed), so a new commit is the
   only route to more sample on this build.
2. The defect this fixes was found in live replays, and local panels have just
   been shown to rank *lineages* backwards — `spar_sentinel` puts the live
   flagship 6.7 sd last. A local null on a cross-cutting mechanism is weak
   evidence.

If it lands below `vidarr`'s own live number, the constant is dead and the
composition question is still answered.
