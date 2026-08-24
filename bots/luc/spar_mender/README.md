# spar_mender — a sparring fixture, not a ladder entry

`steward_hardened_reinforced@6b39ebbe3` rebuilt to sit still and mend. It exists
because the local panel could not produce the matchup that costs us the most
Elo on the live ladder.

## Why it exists

Pooled over every `steward_hardened_reinforced` build in the CI feed, our worst
live matchups are not the strongest teams — they are a cluster that counters our
style:

| opponent | ladder rank | our game win rate | series |
|---|---|---|---|
| Besvikomat | 11 | **0.242** | 10–66 |
| not adgato | 4 | 0.317 | 15–67 |
| The Flotte Experience | 8 | 0.377 | 21–49 |
| O(1) | 13 | 0.438 | 24–44 |
| Pantheon | **1** | 0.445 | 38–56 |
| sporks | **2** | 0.565 | 51–29 |
| Erebus | **5** | 0.568 | 47–29 |

We do better against the top three than against several teams rated below us.
Decoded replays say why: against Besvikomat and O(1) we deal two to three times
more Core damage than they do and still lose, because their Core is mended back
to full between our assaults and ours is not. On lighthouse we had their Core at
27 of 500 and it healed to 500 while ours bled out.

Nothing in our own lineage does that to us — our siege breaks our own bots — so
the whole local panel is blind to the failure mode.

## What it changes

Against the flagship: doctrine pinned to FORTIFY on every map, roles `(2, 0)` so
there is no attacker and two miners, three home turrets per doctrine that never
retire (`TURRET_QUIET_ROUNDS` raised out of reach), and the economy ceiling
lifted early (`ECON_BUILDER_ROUND` 200 → 80, `ECON_MAX_TOTAL_BUILDERS` 6 → 12).

It is deliberately not trying to be strong. It is trying to be *slow*, so that a
besieging opponent has something to fail against.

## Revision: every home Builder mends

The first cut kept the stock mend gate, which is `p.is_launcher_builder` only —
one mender, restoring 4 HP a round. That cannot hold a Core against a siege,
which is the entire property the fixture needs. So the gate is now "any Builder
within `MENDER_LEASH` of home", and the leash widened 10 → 14.

It also got its attacker back (`_ROLES` returned to `(1, 1)` from `(2, 0)`).
With no attacker at all the fixture was simply overrun before mending could
matter — it died on quarry at turn 126 and on hive at 112 — which made it a test
of nothing.

## How well it works — honestly, partially

It reproduces the shape on some maps — it now beats the flagship on aurora
(turn 140) and jackpot (turn 528), and an earlier build took jackpot to the
round-1000 titanium tiebreak, which is exactly how we lost jackpot to
Besvikomat. But it still dies to a straight rush on quarry (turn 90), vault
(94), twins (109) and hive (161), so it does **not** yet hold a Core the way
Besvikomat does. `steward_relent` scored 0.667 against the first cut, same as
the flagship — the two were indistinguishable, because the stall condition
still did not trip.

Treat its current numbers as a floor, not a measurement. Making it genuinely
un-killable — more dedicated menders rather than more miners — is the obvious
next step, and would turn it into a real regression test for the matchup that is
costing us the most rating.
